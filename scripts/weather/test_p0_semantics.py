"""Hand-written P0 fixtures for settlement time, bucket, and PIT semantics."""
from __future__ import annotations

import contextlib
import csv
import io
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

import asof_forecasts
import build_bucket_probabilities as bbp
from pit import available_asof
from settlement_semantics import (
    GaussianTemperatureDistribution,
    TemperatureBucket,
    normal_bucket_probabilities,
    settlement_standard_time_window,
)

MARKET_FIELDS = [
    "market_ticker", "event_ticker", "series_ticker", "city", "temp_type",
    "outcome_local_date", "status", "result", "bucket_floor_f", "bucket_ceil_f",
]
FORECAST_FIELDS = [
    "event_ticker", "decision_time_utc", "mean_f", "stddev_f",
    "forecast_issue_time", "source_receipt_time", "model_name", "model_version",
]
FORECAST_READY = {
    "decision_time_utc": "2026-07-03T00:00:00Z",
    "mean_f": "102", "stddev_f": "1.5",
    "forecast_issue_time": "2026-07-02T12:00:00Z",
    "source_receipt_time": "2026-07-02T12:05:00Z",
    "model_name": "mock-ensemble", "model_version": "0.0.1",
}
PHX_BUCKETS = [
    {"market_ticker": "KXHIGHTPHX-26JUL03-L", "event_ticker": "KXHIGHTPHX-26JUL03",
     "series_ticker": "KXHIGHTPHX", "city": "phx", "temp_type": "high",
     "outcome_local_date": "2026-07-03", "status": "unopened", "result": "",
     "bucket_floor_f": "", "bucket_ceil_f": "100"},
    {"market_ticker": "KXHIGHTPHX-26JUL03-M", "event_ticker": "KXHIGHTPHX-26JUL03",
     "series_ticker": "KXHIGHTPHX", "city": "phx", "temp_type": "high",
     "outcome_local_date": "2026-07-03", "status": "unopened", "result": "",
     "bucket_floor_f": "101", "bucket_ceil_f": "103"},
    {"market_ticker": "KXHIGHTPHX-26JUL03-H", "event_ticker": "KXHIGHTPHX-26JUL03",
     "series_ticker": "KXHIGHTPHX", "city": "phx", "temp_type": "high",
     "outcome_local_date": "2026-07-03", "status": "unopened", "result": "",
     "bucket_floor_f": "104", "bucket_ceil_f": ""},
]
LV_BUCKETS = [
    {"market_ticker": "KXHIGHTLV-26JUL01-L", "event_ticker": "KXHIGHTLV-26JUL01",
     "series_ticker": "KXHIGHTLV", "city": "lv", "temp_type": "high",
     "outcome_local_date": "2026-07-01", "status": "unopened", "result": "",
     "bucket_floor_f": "", "bucket_ceil_f": "88"},
    {"market_ticker": "KXHIGHTLV-26JUL01-M", "event_ticker": "KXHIGHTLV-26JUL01",
     "series_ticker": "KXHIGHTLV", "city": "lv", "temp_type": "high",
     "outcome_local_date": "2026-07-01", "status": "unopened", "result": "",
     "bucket_floor_f": "89", "bucket_ceil_f": "91"},
    {"market_ticker": "KXHIGHTLV-26JUL01-H", "event_ticker": "KXHIGHTLV-26JUL01",
     "series_ticker": "KXHIGHTLV", "city": "lv", "temp_type": "high",
     "outcome_local_date": "2026-07-01", "status": "unopened", "result": "",
     "bucket_floor_f": "92", "bucket_ceil_f": ""},
]


def write_csv(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    with path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


class SettlementSemanticsTest(unittest.TestCase):
    def test_phx_standard_time_window(self):
        window = settlement_standard_time_window("phx", "2026-07-01")
        self.assertEqual(window.start_utc.isoformat(), "2026-07-01T07:00:00+00:00")
        self.assertEqual(window.end_utc - window.start_utc, timedelta(days=1))
        self.assertEqual(window.standard_utc_offset_hours, -7)

    def test_las_summer_uses_pst_clock(self):
        window = settlement_standard_time_window("lv", "2026-07-01")
        self.assertEqual(window.start_utc.isoformat(), "2026-07-01T08:00:00+00:00")
        self.assertEqual(window.end_utc.isoformat(), "2026-07-02T08:00:00+00:00")
        self.assertEqual(window.standard_utc_offset_hours, -8)

    def test_las_winter_uses_same_utc_clock(self):
        window = settlement_standard_time_window("lv", "2026-01-01")
        self.assertEqual(window.start_utc.isoformat(), "2026-01-01T08:00:00+00:00")
        self.assertEqual(window.end_utc - window.start_utc, timedelta(days=1))

    def test_las_dst_transitions_keep_24h_standard_window(self):
        for day in ("2026-03-08", "2026-11-01"):
            window = settlement_standard_time_window("lv", day)
            self.assertEqual(window.start_utc.isoformat(), f"{day}T08:00:00+00:00")
            self.assertEqual(window.end_utc - window.start_utc, timedelta(days=1))

    def test_unknown_city_is_rejected(self):
        with self.assertRaises(ValueError):
            settlement_standard_time_window("nyc", "2026-07-01")

    def test_bucket_probabilities_are_coherent(self):
        buckets = [
            TemperatureBucket("low", None, 79),
            TemperatureBucket("middle", 80, 81),
            TemperatureBucket("high", 82, None),
        ]
        probabilities = normal_bucket_probabilities(buckets, mean_f=81, stddev_f=1)
        self.assertAlmostEqual(sum(probabilities.values()), 1.0, places=12)
        self.assertGreater(probabilities["middle"], probabilities["low"])
        self.assertGreater(probabilities["middle"], probabilities["high"])

    def test_partition_gap_is_rejected(self):
        with self.assertRaises(ValueError):
            normal_bucket_probabilities([
                TemperatureBucket("low", None, 79),
                TemperatureBucket("high", 81, None),
            ], mean_f=80, stddev_f=1)

    def test_partition_overlap_is_rejected(self):
        with self.assertRaises(ValueError):
            normal_bucket_probabilities([
                TemperatureBucket("low", None, 80),
                TemperatureBucket("middle", 80, 82),
                TemperatureBucket("high", 81, None),
            ], mean_f=80, stddev_f=1)

    def test_partition_rejects_duplicate_ticker(self):
        with self.assertRaises(ValueError):
            normal_bucket_probabilities([
                TemperatureBucket("same", None, 80),
                TemperatureBucket("same", 81, 82),
                TemperatureBucket("high", 83, None),
            ], mean_f=80, stddev_f=1)


class PointInTimeTest(unittest.TestCase):
    def test_receipt_time_is_a_hard_gate(self):
        row = {"initialization_time_utc": "2026-07-01T00:00:00Z",
               "ingested_at_utc": "2026-07-01T02:00:00Z"}
        self.assertFalse(available_asof(row, "2026-07-01T01:00:00Z"))
        self.assertTrue(available_asof(row, datetime(2026, 7, 1, 2, tzinfo=timezone.utc)))

    def test_missing_receipt_time_fails_closed(self):
        row = {"initialization_time_utc": "2026-07-01T00:00:00Z"}
        with self.assertRaises(ValueError):
            available_asof(row, "2026-07-01T02:00:00Z")

    def test_missing_issue_time_fails_closed(self):
        row = {"source_receipt_time": "2026-07-01T00:00:00Z"}
        with self.assertRaises(ValueError):
            available_asof(row, "2026-07-01T02:00:00Z")

    def test_missing_decision_time_fails_closed(self):
        row = {"initialization_time_utc": "2026-07-01T00:00:00Z",
               "source_receipt_time": "2026-07-01T01:00:00Z"}
        with self.assertRaises(ValueError):
            available_asof(row, None)


class AsofForecastsTest(unittest.TestCase):
    def test_known_forecasts_keeps_future_valid_time(self):
        row = {"initialization_time_utc": "2026-07-02T12:00:00Z",
               "source_receipt_time": "2026-07-02T12:05:00Z",
               "valid_time_utc": "2026-07-03T23:59:00Z"}
        self.assertEqual(asof_forecasts.known_forecasts([row], "2026-07-03T00:00:00Z"), [row])

    def test_known_forecasts_rejects_receipt_after_decision(self):
        row = {"initialization_time_utc": "2026-07-02T12:00:00Z",
               "source_receipt_time": "2026-07-03T01:00:00Z"}
        self.assertEqual(asof_forecasts.known_forecasts([row], "2026-07-03T00:00:00Z"), [])

    def test_missing_receipt_fails_closed(self):
        row = {"initialization_time_utc": "2026-07-02T12:00:00Z"}
        with self.assertRaises(ValueError):
            asof_forecasts.known_forecasts([row], "2026-07-03T00:00:00Z")

    def test_naive_decision_datetime_is_utc(self):
        row = {"initialization_time_utc": "2026-07-02T12:00:00Z",
               "source_receipt_time": "2026-07-02T12:05:00Z",
               "valid_time_utc": "2026-07-02T23:59:00Z"}
        out = asof_forecasts.valid_forecasts_asof([row], datetime(2026, 7, 3))
        self.assertEqual(out, [row])

    def test_valid_forecasts_excludes_future_valid_time(self):
        row = {"initialization_time_utc": "2026-07-02T12:00:00Z",
               "source_receipt_time": "2026-07-02T12:05:00Z",
               "valid_time_utc": "2026-07-03T23:59:00Z"}
        self.assertEqual(asof_forecasts.valid_forecasts_asof([row], "2026-07-03T00:00:00Z"), [])

    def test_valid_forecasts_keeps_valid_before_decision(self):
        row = {"initialization_time_utc": "2026-07-02T12:00:00Z",
               "source_receipt_time": "2026-07-02T12:05:00Z",
               "valid_time_utc": "2026-07-02T23:59:00Z"}
        self.assertEqual(asof_forecasts.valid_forecasts_asof([row], "2026-07-03T00:00:00Z"), [row])

    def test_valid_forecasts_missing_valid_time_fails_closed(self):
        row = {"initialization_time_utc": "2026-07-02T12:00:00Z",
               "source_receipt_time": "2026-07-02T12:05:00Z"}
        with self.assertRaises(ValueError):
            asof_forecasts.valid_forecasts_asof([row], "2026-07-03T00:00:00Z")


class BuildBucketProbabilitiesCliTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.forecasts = {**FORECAST_READY,
                          "event_ticker": "KXHIGHTPHX-26JUL03"}
        self.forecasts_lv = {**self.forecasts,
                             "event_ticker": "KXHIGHTLV-26JUL01",
                             "decision_time_utc": "2026-07-01T00:00:00Z",
                             "forecast_issue_time": "2026-06-30T12:00:00Z",
                             "source_receipt_time": "2026-06-30T12:05:00Z",
                             "mean_f": "90"}

    def _markets(self, rows: list[dict]) -> Path:
        path = Path(self.tmp.name) / "markets.csv"
        write_csv(path, MARKET_FIELDS, rows)
        return path

    def _forecasts(self, rows: list[dict]) -> Path:
        path = Path(self.tmp.name) / "forecasts.csv"
        write_csv(path, FORECAST_FIELDS, rows)
        return path

    def _run_cli(self, markets: Path, forecasts: Path) -> tuple[Path, list[dict]]:
        out = Path(self.tmp.name) / "bucket_probabilities.csv"
        argv = ["build_bucket_probabilities", "--markets", str(markets),
                "--forecasts", str(forecasts), "--output", str(out)]
        buf = io.StringIO()
        with mock.patch.object(sys, "argv", argv), contextlib.redirect_stdout(buf):
            bbp.main()
        self.assertIn(str(out), buf.getvalue())
        with out.open(newline="") as fh:
            return out, list(csv.DictReader(fh))

    def test_cli_output_has_bitemporal_fields(self):
        mk = self._markets([*PHX_BUCKETS, *LV_BUCKETS])
        fc = self._forecasts([self.forecasts, self.forecasts_lv])
        out, rows = self._run_cli(mk, fc)
        self.assertEqual(len(rows), 6)
        by_event: dict[str, list[dict]] = {}
        for row in rows:
            self.assertIn("target_standard_time_window_start_utc", row)
            self.assertIn("target_standard_time_window_end_utc", row)
            self.assertIn("forecast_issue_time", row)
            self.assertIn("source_receipt_time", row)
            self.assertIn("decision_time_utc", row)
            self.assertIn("model_name", row)
            by_event.setdefault(row["event_ticker"], []).append(row)
        self.assertEqual(len(by_event), 2)
        for rows_in_event in by_event.values():
            self.assertAlmostEqual(
                sum(float(r["bucket_probability"]) for r in rows_in_event), 1.0, places=6)

        phx = {r["market_ticker"]: r for r in by_event["KXHIGHTPHX-26JUL03"]}
        self.assertEqual(phx["KXHIGHTPHX-26JUL03-M"]["target_standard_time_window_start_utc"],
                         "2026-07-03T07:00:00Z")
        self.assertEqual(phx["KXHIGHTPHX-26JUL03-M"]["target_standard_time_window_end_utc"],
                         "2026-07-04T07:00:00Z")
        self.assertEqual(phx["KXHIGHTPHX-26JUL03-M"]["source_receipt_time"],
                         "2026-07-02T12:05:00Z")
        self.assertEqual(phx["KXHIGHTPHX-26JUL03-M"]["forecast_issue_time"],
                         "2026-07-02T12:00:00Z")
        self.assertEqual(phx["KXHIGHTPHX-26JUL03-M"]["model_name"], "mock-ensemble")
        self.assertGreater(float(phx["KXHIGHTPHX-26JUL03-M"]["bucket_probability"]), 0.6)

        lv = {r["market_ticker"]: r for r in by_event["KXHIGHTLV-26JUL01"]}
        self.assertEqual(lv["KXHIGHTLV-26JUL01-M"]["target_standard_time_window_start_utc"],
                         "2026-07-01T08:00:00Z")
        self.assertEqual(lv["KXHIGHTLV-26JUL01-M"]["target_standard_time_window_end_utc"],
                         "2026-07-02T08:00:00Z")
        self.assertEqual(lv["KXHIGHTLV-26JUL01-M"]["city"], "lv")

    def test_cli_rejects_overlapping_partition(self):
        overlapping = [
            *PHX_BUCKETS[:2],
            {**PHX_BUCKETS[2], "bucket_floor_f": "102"},
        ]
        mk = self._markets(overlapping)
        fc = self._forecasts([self.forecasts])
        with self.assertRaises(ValueError):
            self._run_cli(mk, fc)

    def test_cli_rejects_missing_receipt_time(self):
        mk = self._markets(PHX_BUCKETS)
        fc = self._forecasts([{**self.forecasts, "source_receipt_time": ""}])
        with self.assertRaises(ValueError):
            self._run_cli(mk, fc)

    def test_cli_rejects_missing_issue_time(self):
        mk = self._markets(PHX_BUCKETS)
        fc = self._forecasts([{**self.forecasts, "forecast_issue_time": ""}])
        with self.assertRaises(ValueError):
            self._run_cli(mk, fc)

    def test_cli_rejects_receipt_after_decision(self):
        mk = self._markets(PHX_BUCKETS)
        fc = self._forecasts([{**self.forecasts, "source_receipt_time": "2026-07-03T01:00:00Z"}])
        with self.assertRaises(ValueError):
            self._run_cli(mk, fc)

    def test_render_returns_row_count(self):
        mk = self._markets(PHX_BUCKETS)
        fc = self._forecasts([self.forecasts])
        out = Path(self.tmp.name) / "out.csv"
        written = bbp.render(mk, fc, out)
        self.assertEqual(written, 3)

class DistributionApiTests(unittest.TestCase):
    def test_cdf_probability_and_quantile_are_coherent(self):
        distribution = GaussianTemperatureDistribution(70.0, 2.0)
        self.assertAlmostEqual(distribution.cdf(70.0), 0.5, places=12)
        self.assertAlmostEqual(distribution.prob_above(70.0), 0.5, places=12)
        self.assertAlmostEqual(distribution.quantile(0.5), 70.0, places=8)
        self.assertLess(distribution.cdf(69.0), distribution.cdf(71.0))

    def test_invalid_distribution_and_quantile_fail_closed(self):
        with self.assertRaises(ValueError): GaussianTemperatureDistribution(70.0, 0.0)
        with self.assertRaises(ValueError): GaussianTemperatureDistribution(70.0, 2.0).quantile(1.1)


if __name__ == "__main__":
    unittest.main()

import hashlib
import json
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from collect_historical_nyc_quotes import _fetch_market, _markets, _merge_rows, _write_immutable_raw, collect


class HistoricalQuoteRawTests(unittest.TestCase):
    def test_series_parameter_rejects_non_temperature_products(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                collect(Path(directory), limit=0, series_ticker="CLINYC")

    def test_fetch_failure_is_returned_as_explicit_market_rejection(self):
        market = {"ticker": "M", "open_time": "2026-01-01T00:00:00Z", "close_time": "2026-01-01T01:00:00Z"}
        with tempfile.TemporaryDirectory() as directory, patch("collect_historical_nyc_quotes.http_get_json", side_effect=RuntimeError("429")):
            candles, trades, raw, failure = _fetch_market(market, Path(directory), "2026-01-01T02:00:00Z")
            self.assertEqual((candles, trades, raw), ([], [], []))
            self.assertEqual(failure["market_ticker"], "M")
            self.assertIn("candle_fetch_failed", failure["reason"])

    def test_trade_cursor_pages_are_all_retained(self):
        market = {"ticker": "M", "open_time": "2026-01-01T00:00:00Z", "close_time": "2026-01-01T01:00:00Z"}
        payloads = [{"candlesticks": []}, {"trades": [{"trade_id": "1"}], "cursor": "next"}, {"trades": [{"trade_id": "2"}], "cursor": ""}]
        with tempfile.TemporaryDirectory() as directory, patch("collect_historical_nyc_quotes.http_get_json", side_effect=payloads):
            candles, trades, raw, failure = _fetch_market(market, Path(directory), "2026-01-01T02:00:00Z")
            self.assertIsNone(failure)
            self.assertEqual([row["trade_id"] for row in trades], ["1", "2"])
            self.assertEqual(len(raw), 3)

    def test_append_merge_deduplicates_stable_keys(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "candles.csv"
            path.write_text("market_ticker,end_period_ts,value\nA,1,old\n")
            merged = _merge_rows(path, [{"market_ticker": "A", "end_period_ts": "1", "value": "new"}, {"market_ticker": "B", "end_period_ts": "2", "value": "x"}], ("market_ticker", "end_period_ts"), True)
            self.assertEqual({(row["market_ticker"], row["end_period_ts"]): row["value"] for row in merged}, {("A", "1"): "new", ("B", "2"): "x"})

    def test_raw_payload_is_content_addressed_and_not_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            raw = Path(directory)
            records = []
            first_path, first_hash = _write_immutable_raw(
                raw, "ticker_candles", {"candlesticks": []},
                "2026-09-13T12:00:00Z", "/historical/candles", records)
            second_path, second_hash = _write_immutable_raw(
                raw, "ticker_candles", {"candlesticks": [{"x": 1}]},
                "2026-09-13T12:01:00Z", "/historical/candles", records)
            self.assertNotEqual(first_path, second_path)
            self.assertNotEqual(first_hash, second_hash)
            self.assertEqual(len(records), 2)
            self.assertEqual(
                hashlib.sha256(Path(first_path).read_bytes()).hexdigest(),
                hashlib.sha256(json.dumps({"candlesticks": []}, sort_keys=True, separators=(",", ":")).encode() + b"\n").hexdigest(),
            )
            self.assertTrue(Path(first_path).exists())
            self.assertTrue(Path(second_path).exists())

    def test_market_cursor_can_archive_raw_page_payload(self):
        payload = {"markets": [{"ticker": "M", "event_ticker": "E"}], "cursor": ""}
        with tempfile.TemporaryDirectory() as directory:
            records = []
            with patch("collect_historical_nyc_quotes.http_get_json", return_value=payload):
                rows = _markets("KXTEMPNYCH", 1, raw_dir=Path(directory),
                                receipt="2026-09-13T12:00:00Z", raw_records=records)
            self.assertEqual(rows[0]["ticker"], "M")
            self.assertEqual(len(records), 1)
            self.assertTrue(Path(records[0]["raw_path"]).exists())


if __name__ == "__main__":
    unittest.main()

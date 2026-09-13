import csv
import tempfile
import unittest
from pathlib import Path

from build_nyc_edge_dataset import build


class EdgeDatasetTests(unittest.TestCase):
    def test_accepts_only_featured_settled_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            def write(name, fields, rows):
                path = root / name
                with path.open("w", newline="") as handle:
                    writer = csv.DictWriter(handle, fieldnames=fields); writer.writeheader(); writer.writerows(rows)
                return path
            contracts = write("contracts.csv", ["market_ticker", "event_ticker", "target_time_utc", "settlement_station_method"], [{"market_ticker": "A", "event_ticker": "E", "target_time_utc": "2026-01-01T00:00:00Z", "settlement_station_method": "verified"}, {"market_ticker": "B", "event_ticker": "E", "target_time_utc": "2026-01-01T01:00:00Z", "settlement_station_method": "verified"}])
            labels = write("labels.csv", ["market_ticker", "kalshi_result", "source_valid_utc", "label_available_ts", "source_temperature_f"], [{"market_ticker": "A", "kalshi_result": "yes", "source_valid_utc": "2026-01-01T00:00:00Z", "label_available_ts": "2026-01-01T00:30:00Z", "source_temperature_f": "40"}, {"market_ticker": "B", "kalshi_result": "no", "source_valid_utc": "", "label_available_ts": "", "source_temperature_f": ""}])
            features = write("features.csv", ["market_ticker", "decision_ts", "features_json", "source_run_ids", "observation_ids"], [{"market_ticker": "A", "decision_ts": "2025-12-31T23:00:00Z", "features_json": "{}", "source_run_ids": "", "observation_ids": ""}])
            rejects = write("rejects.csv", ["market_ticker", "reason", "reason_codes"], [{"market_ticker": "B", "reason": "late_source", "reason_codes": "late_source"}])
            accepted, rejected = build(contracts, labels, features, rejects)
            self.assertEqual([row["market_ticker"] for row in accepted], ["A"])
            self.assertEqual(rejected, [{"market_ticker": "B", "reason": "late_source", "reason_codes": "late_source;missing_label_availability;invalid_exact_settlement_time"}])

    def test_late_final_label_is_allowed_when_features_are_pit_valid(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            def write(name, fields, rows):
                path = root / name
                with path.open("w", newline="") as handle:
                    writer = csv.DictWriter(handle, fieldnames=fields); writer.writeheader(); writer.writerows(rows)
                return path
            contracts = write("contracts.csv", ["market_ticker", "event_ticker", "target_time_utc", "settlement_station_method"], [{"market_ticker": "A", "event_ticker": "E", "target_time_utc": "2026-01-01T00:00:00Z", "settlement_station_method": "verified"}])
            labels = write("labels.csv", ["market_ticker", "kalshi_result", "source_valid_utc", "label_available_ts"], [{"market_ticker": "A", "kalshi_result": "yes", "source_valid_utc": "2026-01-01T00:00:00Z", "label_available_ts": "2026-01-01T00:01:00Z"}])
            features = write("features.csv", ["market_ticker", "decision_ts", "features_json", "source_run_ids", "observation_ids"], [{"market_ticker": "A", "decision_ts": "2026-01-01T00:00:00Z", "features_json": "{}", "source_run_ids": "", "observation_ids": ""}])
            rejects = write("rejects.csv", ["market_ticker", "reason", "reason_codes"], [])
            accepted, rejected = build(contracts, labels, features, rejects)
            self.assertEqual([row["market_ticker"] for row in accepted], ["A"])
            self.assertEqual(accepted[0]["label_available_ts"], "2026-01-01T00:01:00Z")
            self.assertFalse(rejected)

    def test_pre_target_label_clock_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            def write(name, fields, rows):
                path = root / name
                with path.open("w", newline="") as handle:
                    writer = csv.DictWriter(handle, fieldnames=fields); writer.writeheader(); writer.writerows(rows)
                return path
            contracts = write("contracts.csv", ["market_ticker", "event_ticker", "target_time_utc", "settlement_station_method"], [{"market_ticker": "A", "event_ticker": "E", "target_time_utc": "2026-01-01T00:00:00Z", "settlement_station_method": "verified"}])
            labels = write("labels.csv", ["market_ticker", "kalshi_result", "source_valid_utc", "label_available_ts"], [{"market_ticker": "A", "kalshi_result": "yes", "source_valid_utc": "2026-01-01T00:00:00Z", "label_available_ts": "2025-12-31T23:59:00Z"}])
            features = write("features.csv", ["market_ticker", "decision_ts", "features_json"], [{"market_ticker": "A", "decision_ts": "2025-12-31T23:00:00Z", "features_json": "{}"}])
            rejects = write("rejects.csv", ["market_ticker", "reason", "reason_codes"], [])
            accepted, rejected = build(contracts, labels, features, rejects)
            self.assertFalse(accepted)
            self.assertIn("label_available_before_target", rejected[0]["reason_codes"])


if __name__ == "__main__":
    unittest.main()

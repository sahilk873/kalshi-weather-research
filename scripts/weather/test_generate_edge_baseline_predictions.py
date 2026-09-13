import csv
import tempfile
import unittest
from pathlib import Path

from generate_edge_baseline_predictions import _probability, generate


class EdgeBaselineTests(unittest.TestCase):
    def test_probability_rejects_unknown_comparison_and_nonfinite_temperature(self):
        self.assertIsNone(_probability({"threshold_f": "70", "comparison": "equal", "features_json": '{"temperature_f": 68}'}))
        self.assertIsNone(_probability({"threshold_f": "70", "comparison": "above", "features_json": '{"temperature_f": "NaN"}'}))

    def test_empty_dataset_emits_no_predictions_or_manifests(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); dataset = root / "dataset.csv"; dataset.write_text("market_ticker\n")
            contracts = root / "contracts.csv"; contracts.write_text("market_ticker\n")
            result = generate(dataset, contracts, root / "predictions.csv", root / "manifests")
            self.assertFalse(result["pass"]); self.assertEqual(result["prediction_rows"], 0); self.assertEqual(result["manifest_rows"], 0)

    def test_missing_contract_is_rejected_explicitly(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dataset = root / "dataset.csv"
            dataset.write_text("market_ticker,comparison,threshold_f,features_json,source_run_ids,observation_ids\nM,above,70,\"{\\\"temperature_f\\\":68}\",x,y\n")
            contracts = root / "contracts.csv"
            contracts.write_text("market_ticker\n")
            result = generate(dataset, contracts, root / "predictions.csv", root / "manifests")
            self.assertEqual(result["rejections"][0]["reason"], "missing_contract_terms")
            self.assertEqual(result["prediction_rows"], 0)

    def test_missing_provenance_indexes_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dataset = root / "dataset.csv"
            with dataset.open("w", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["market_ticker", "target_time_utc", "decision_ts", "comparison", "threshold_f", "features_json", "source_run_ids", "observation_ids", "settlement_station_method", "rules_hash"])
                writer.writeheader()
                writer.writerow({"market_ticker": "M", "target_time_utc": "2026-09-14T00:00:00Z", "decision_ts": "2026-09-13T12:00:00Z", "comparison": "above", "threshold_f": "70", "features_json": '{"temperature_f":68}', "source_run_ids": '["run"]', "observation_ids": '["obs"]', "settlement_station_method": "verified", "rules_hash": "r"})
            contracts = root / "contracts.csv"
            contracts.write_text("market_ticker,target_time_utc,rules_hash\nM,2026-09-14T00:00:00Z,r\n")
            result = generate(dataset, contracts, root / "predictions.csv", root / "manifests")
            self.assertEqual(result["rejections"][0]["reason"], "missing_provenance_index")


if __name__ == "__main__": unittest.main()

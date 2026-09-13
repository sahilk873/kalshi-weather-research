import csv
import tempfile
import unittest
from pathlib import Path

from evaluate_edge_first import evaluate


class EdgeEvaluationTests(unittest.TestCase):
    def test_empty_dataset_never_emits_metrics(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "dataset.csv"
            path.write_text("market_ticker,target_time_utc,decision_ts,kalshi_result,features_json\n")
            result = evaluate(path)
            self.assertEqual(result["status"], "not_evaluable")
            self.assertIsNone(result["metrics"])
            self.assertFalse(result["pass"])

    def test_nonempty_dataset_without_quote_clock_is_not_ready(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "dataset.csv"
            path.write_text("market_ticker,target_time_utc,decision_ts,kalshi_result,features_json\nM,2026-09-14T00:00:00Z,2026-09-13T12:00:00Z,yes,{}\n")
            result = evaluate(path)
            self.assertEqual(result["reason"], "missing_executable_quote_availability_clock")
            self.assertIsNone(result["metrics"])

    def test_late_quote_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "dataset.csv"
            path.write_text("market_ticker,target_time_utc,decision_ts,kalshi_result,features_json,quote_available_ts\nM,2026-09-14T00:00:00Z,2026-09-13T12:00:00Z,yes,{},2026-09-13T12:01:00Z\n")
            result = evaluate(path)
            self.assertTrue(result["reason"].startswith("late_or_invalid_quote_clock"))

    def test_valid_oos_rows_emit_forecast_and_economic_metrics(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "dataset.csv"
            path.write_text("market_ticker,target_time_utc,decision_ts,kalshi_result,features_json,quote_available_ts,predicted_probability,oos_fold,model_fit_end_ts,yes_ask,fee,slippage\n"
                            "A,2026-01-02T00:00:00Z,2026-01-01T12:00:00Z,yes,{},2026-01-01T11:00:00Z,0.8,0,2026-01-01T10:00:00Z,0.5,0.01,0.01\n"
                            "B,2026-01-03T00:00:00Z,2026-01-02T12:00:00Z,no,{},2026-01-02T11:00:00Z,0.2,1,2026-01-02T10:00:00Z,0.5,0.01,0.01\n")
            result = evaluate(path)
            self.assertEqual(result["status"], "evaluated")
            self.assertEqual(result["metrics"]["rows"], 2)
            self.assertIn("brier_score", result["metrics"])
            self.assertIn("reliability_bins", result["metrics"])
            self.assertIn("max_bin_calibration_error", result["metrics"])
            self.assertEqual(result["metrics"]["signals"], 1)
            self.assertAlmostEqual(result["metrics"]["net_pnl"], 0.48)


if __name__ == "__main__":
    unittest.main()

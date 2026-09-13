import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from evaluate_postprocessor_walk_forward import evaluate


class PostprocessorWalkForwardTest(unittest.TestCase):
    def test_bias_fold_evaluation_has_no_rejections(self):
        forecasts, labels = [], []
        for day in range(1, 8):
            date = f"2025-01-{day:02d}"
            forecasts.append({"event_ticker": f"E{day}", "decision_time_utc": f"2024-12-{day:02d}T00:00:00Z", "forecast_issue_time": f"2024-12-{day:02d}T00:00:00Z", "source_receipt_time": f"2024-12-{day:02d}T00:00:00Z", "mean_f": "70", "stddev_f": "2", "model_name": "m", "model_version": "v", "lead_hours": "24", "city": "nyc", "temp_type": "high", "outcome_local_date": date})
            labels.append({"event_ticker": f"E{day}", "label_available_ts": f"2025-01-{day:02d}T12:00:00Z", "observed_f": "70"})
        rows, rejected = evaluate(forecasts, labels, "bias", train_days=3, test_days=2)
        self.assertFalse(rejected); self.assertTrue(rows)


if __name__ == "__main__": unittest.main()

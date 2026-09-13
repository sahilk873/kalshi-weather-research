import csv
import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from evaluate_blend_walk_forward import evaluate


class BlendWalkForwardTest(unittest.TestCase):
    def test_outer_fold_writes_rows(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            forecasts = []
            labels = []
            for i in range(12):
                day = f"2025-01-{i + 2:02d}"
                decision = f"2025-01-{i + 1:02d}T12:00:00Z"
                labels.append({"event_ticker": f"E{i}", "label_available_ts": f"2025-01-{i + 2:02d}T12:00:00Z", "observed_f": "80"})
                for model, value in (("a", "79"), ("b", "81")):
                    forecasts.append({"event_ticker": f"E{i}", "decision_time_utc": decision,
                        "forecast_issue_time": decision, "source_receipt_time": decision,
                        "model_name": model, "model_version": "v", "city": "nyc",
                        "temp_type": "high", "outcome_local_date": day,
                        "lead_hours": "24", "mean_f": value, "stddev_f": "2"})
            fp, lp = root / "f.csv", root / "l.csv"
            with fp.open("w", newline="") as fh:
                w = csv.DictWriter(fh, fieldnames=forecasts[0]); w.writeheader(); w.writerows(forecasts)
            with lp.open("w", newline="") as fh:
                w = csv.DictWriter(fh, fieldnames=labels[0]); w.writeheader(); w.writerows(labels)
            out = root / "o.csv"
            folds, predictions = evaluate([fp], lp, out, train_days=3, test_days=3)
            self.assertGreater(folds, 0); self.assertGreater(predictions, 0)


if __name__ == "__main__": unittest.main()

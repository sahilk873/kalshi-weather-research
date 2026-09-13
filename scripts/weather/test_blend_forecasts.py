import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from blend_forecasts import apply_blend, fit_weights


class BlendTests(unittest.TestCase):
    def test_weights_favor_lower_error_model_and_mix_variance(self):
        forecasts, labels = [], []
        for i in range(1, 4):
            for model, error in (("good", 1), ("bad", 4)):
                ticker = f"e{i}-{model}"
                forecasts.append({"event_ticker": ticker, "decision_time_utc": f"2025-07-{i+1:02d}T12:00:00Z", "model_name": model, "model_version": "v", "city": "nyc", "temp_type": "high", "outcome_local_date": f"2025-07-{i:02d}", "mean_f": str(80 + error), "stddev_f": "2"})
                labels.append({"event_ticker": ticker, "label_available_ts": f"2025-07-{i:02d}T11:00:00Z", "observed_f": "80"})
        weights = fit_weights(forecasts, labels)
        self.assertGreater(weights["good"], weights["bad"])
        current = [{"event_ticker": "current", "model_name": "good", "mean_f": "81", "stddev_f": "2", "city": "nyc", "temp_type": "high", "outcome_local_date": "2026-07-01"}, {"event_ticker": "current", "model_name": "bad", "mean_f": "84", "stddev_f": "2", "city": "nyc", "temp_type": "high", "outcome_local_date": "2026-07-01"}]
        row = apply_blend(current, weights)[0]
        self.assertEqual(row["model_name"], "convex_blend")
        self.assertEqual(row["blend_member_count"], "2")

    def test_no_eligible_weights_yields_no_blend(self):
        self.assertEqual(fit_weights([], []), {})


if __name__ == "__main__": unittest.main()

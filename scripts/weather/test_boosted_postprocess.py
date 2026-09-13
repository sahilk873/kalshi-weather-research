import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from boosted_postprocess import apply_boosted, fit_boosted


class BoostedTest(unittest.TestCase):
    def test_fit_and_apply_quantiles(self):
        forecasts, labels = [], []
        for i in range(40):
            day = i % 28 + 1; ticker = f"E{i}"
            forecasts.append({"event_ticker": ticker, "decision_time_utc": f"2025-02-{day:02d}T00:00:00Z", "city": "nyc", "temp_type": "high", "outcome_local_date": f"2025-02-{day:02d}", "lead_hours": "24", "mean_f": str(70 + i % 5), "stddev_f": "2"})
            labels.append({"event_ticker": ticker, "label_available_ts": f"2025-02-{day:02d}T12:00:00Z", "observed_f": str(72 + i % 7)})
        fitted = fit_boosted(forecasts, labels, as_of=__import__("datetime").datetime(2025, 3, 1, tzinfo=__import__("datetime").timezone.utc), min_training=10)
        self.assertIsNotNone(fitted)
        row = apply_boosted([dict(forecasts[0], event_ticker="new", outcome_local_date="2025-03-02", decision_time_utc="2025-03-01T00:00:00Z")], fitted)[0]
        self.assertGreater(float(row["p90_f"]), float(row["p10_f"]))


if __name__ == "__main__": unittest.main()

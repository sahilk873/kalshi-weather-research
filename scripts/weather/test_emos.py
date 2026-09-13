import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from emos import apply_emos, fit_emos


class EmosTests(unittest.TestCase):
    def test_affine_mean_and_spread_are_fit(self):
        forecasts, labels = [], []
        for i, mean in enumerate((70, 72, 74, 76, 78), start=1):
            ticker = f"old_{i}"
            forecasts.append({"event_ticker": ticker, "decision_time_utc": f"2025-07-{i+1:02d}T12:00:00Z", "model_name": "gefs", "model_version": "v1", "city": "nyc", "temp_type": "high", "outcome_local_date": f"2025-07-{i:02d}", "lead_hours": "24", "mean_f": str(mean), "stddev_f": "2"})
            labels.append({"event_ticker": ticker, "label_available_ts": f"2025-07-{i:02d}T11:00:00Z", "observed_f": str(2 * mean + 1)})
        fitted = fit_emos(forecasts, labels, min_training=5)
        current = dict(forecasts[0], event_ticker="current", decision_time_utc="2026-07-02T12:00:00Z", outcome_local_date="2026-07-03", mean_f="80", stddev_f="2")
        row = apply_emos([current], fitted)[0]
        self.assertEqual(row["mean_f"], "161.000000")
        self.assertEqual(row["emos_training_rows"], "5")

    def test_future_labels_do_not_fit(self):
        forecast = {"event_ticker": "x", "decision_time_utc": "2025-07-01T12:00:00Z", "model_name": "m", "model_version": "v", "city": "la", "temp_type": "low", "outcome_local_date": "2025-07-01", "lead_hours": "24", "mean_f": "60", "stddev_f": "2"}
        labels = [{"event_ticker": "x", "label_available_ts": "2025-07-01T13:00:00Z", "observed_f": "55"}]
        self.assertEqual(fit_emos([forecast], labels), {})

    def test_day_ahead_target_can_train_when_label_is_available(self):
        forecast = {"event_ticker": "x", "decision_time_utc": "2025-07-01T12:00:00Z", "model_name": "m", "model_version": "v", "city": "la", "temp_type": "low", "outcome_local_date": "2025-07-02", "lead_hours": "24", "mean_f": "60", "stddev_f": "2"}
        labels = [{"event_ticker": "x", "label_available_ts": "2025-07-01T11:00:00Z", "observed_f": "55"}]
        self.assertTrue(fit_emos([forecast], labels, min_training=1))


if __name__ == "__main__": unittest.main()

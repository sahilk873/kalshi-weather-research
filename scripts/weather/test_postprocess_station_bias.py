import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from postprocess_station_bias import apply_bias, fit_bias


class BiasTests(unittest.TestCase):
    def test_earlier_available_labels_drive_correction(self):
        forecasts = []
        labels = []
        for i, observed in enumerate((82.0, 84.0, 86.0, 88.0, 90.0), start=1):
            ticker = f"old_{i}"
            forecasts.append({"event_ticker": ticker, "decision_time_utc": f"2025-07-{i+1:02d}T12:00:00Z", "model_name": "gefs", "model_version": "v1", "city": "nyc", "temp_type": "high", "outcome_local_date": f"2025-07-{i:02d}", "lead_hours": "24", "mean_f": str(observed - 2)})
            labels.append({"event_ticker": ticker, "label_available_ts": f"2025-07-{i:02d}T11:00:00Z", "observed_f": str(observed)})
        fitted = fit_bias(forecasts, labels, min_training=5)
        current = dict(forecasts[0], event_ticker="current", decision_time_utc="2026-07-01T12:00:00Z", outcome_local_date="2026-07-02", mean_f="80")
        corrected = apply_bias([current], fitted)[0]
        self.assertEqual(corrected["mean_f"], "82.000000")
        self.assertEqual(corrected["bias_training_rows"], "5")

    def test_target_or_future_label_does_not_train(self):
        row = {"event_ticker": "x", "decision_time_utc": "2025-07-01T12:00:00Z", "model_name": "gefs", "model_version": "v1", "city": "nyc", "temp_type": "high", "outcome_local_date": "2025-07-01", "lead_hours": "24", "mean_f": "80"}
        labels = [{"event_ticker": "x", "label_available_ts": "2025-07-01T13:00:00Z", "observed_f": "90"}]
        self.assertEqual(fit_bias([row], labels), {})

    def test_day_ahead_target_can_train_when_label_is_available(self):
        row = {"event_ticker": "x", "decision_time_utc": "2025-07-01T12:00:00Z", "model_name": "gefs", "model_version": "v1", "city": "nyc", "temp_type": "high", "outcome_local_date": "2025-07-02", "lead_hours": "24", "mean_f": "80"}
        labels = [{"event_ticker": "x", "label_available_ts": "2025-07-01T11:00:00Z", "observed_f": "90"}]
        self.assertTrue(fit_bias([row], labels, min_training=1))


if __name__ == "__main__":
    unittest.main()

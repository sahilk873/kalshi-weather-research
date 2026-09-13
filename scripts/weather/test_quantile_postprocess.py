import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from quantile_postprocess import apply_quantiles, fit_quantiles


class QuantileTests(unittest.TestCase):
    def test_residual_quantiles_produce_distribution(self):
        forecasts, labels = [], []
        for i, residual in enumerate((-2, -1, 0, 1, 2), start=1):
            ticker = f"old_{i}"
            forecasts.append({"event_ticker": ticker, "decision_time_utc": f"2025-07-{i+1:02d}T12:00:00Z", "model_name": "m", "model_version": "v", "city": "nyc", "temp_type": "high", "outcome_local_date": f"2025-07-{i:02d}", "lead_hours": "24", "mean_f": "80"})
            labels.append({"event_ticker": ticker, "label_available_ts": f"2025-07-{i:02d}T11:00:00Z", "observed_f": str(80 + residual)})
        fitted = fit_quantiles(forecasts, labels, min_training=5)
        row = apply_quantiles([dict(forecasts[0], event_ticker="current", decision_time_utc="2026-07-02T12:00:00Z", outcome_local_date="2026-07-03")], fitted)[0]
        self.assertEqual(row["p50_f"], "80.000000")
        self.assertGreater(float(row["p90_f"]), float(row["p10_f"]))
        self.assertEqual(row["quantile_training_rows"], "5")

    def test_future_label_is_not_training_data(self):
        forecast = {"event_ticker": "x", "decision_time_utc": "2025-07-01T12:00:00Z", "model_name": "m", "model_version": "v", "city": "la", "temp_type": "low", "outcome_local_date": "2025-07-01", "lead_hours": "24", "mean_f": "60"}
        labels = [{"event_ticker": "x", "label_available_ts": "2025-07-01T13:00:00Z", "observed_f": "55"}]
        self.assertEqual(fit_quantiles([forecast], labels), {})

    def test_day_ahead_target_can_train_when_label_is_available(self):
        forecast = {"event_ticker": "x", "decision_time_utc": "2025-07-01T12:00:00Z", "model_name": "m", "model_version": "v", "city": "la", "temp_type": "low", "outcome_local_date": "2025-07-02", "lead_hours": "24", "mean_f": "60"}
        labels = [{"event_ticker": "x", "label_available_ts": "2025-07-01T11:00:00Z", "observed_f": "55"}]
        self.assertTrue(fit_quantiles([forecast], labels, min_training=1))


if __name__ == "__main__": unittest.main()

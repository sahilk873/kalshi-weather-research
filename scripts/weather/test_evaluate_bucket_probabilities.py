import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from evaluate_bucket_probabilities import evaluate


class BucketEvaluationTests(unittest.TestCase):
    def test_brier_and_log_loss_use_future_settlement_label(self):
        base = {"event_ticker": "e", "decision_time_utc": "2025-07-01T12:00:00Z", "forecast_issue_time": "2025-07-01T10:00:00Z", "source_receipt_time": "2025-07-01T11:00:00Z", "model_name": "m", "model_version": "v", "city": "nyc", "temp_type": "high"}
        probabilities = [dict(base, market_ticker="e-a", bucket_probability="0.25"), dict(base, market_ticker="e-b", bucket_probability="0.75")]
        labels = [{"event_ticker": "e", "label_available_ts": "2025-07-02T12:00:00Z", "settled_market_ticker": "e-b"}]
        summary, rejected = evaluate(probabilities, labels)
        self.assertEqual(rejected, [])
        self.assertEqual(summary[0]["events"], 1)
        self.assertEqual(summary[0]["brier"], "0.125000000000")
        self.assertEqual(summary[0]["log_loss"], "0.287682072452")

    def test_late_forecast_is_rejected(self):
        base = {"event_ticker": "e", "decision_time_utc": "2025-07-01T12:00:00Z", "forecast_issue_time": "2025-07-01T13:00:00Z", "source_receipt_time": "2025-07-01T13:00:00Z", "model_name": "m", "model_version": "v", "city": "la", "temp_type": "low"}
        summary, rejected = evaluate([dict(base, market_ticker="e-a", bucket_probability="1.0")], [{"event_ticker": "e", "label_available_ts": "2025-07-02T12:00:00Z", "settled_market_ticker": "e-a"}])
        self.assertEqual(summary, [])
        self.assertEqual(rejected[0]["reason"], "invalid_partition")


if __name__ == "__main__": unittest.main()

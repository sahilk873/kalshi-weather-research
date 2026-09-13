import unittest
from join_kalshi_twc_labels import join

class TWCLabelJoinTests(unittest.TestCase):
    def test_requires_exact_target_and_keeps_receipt(self):
        contracts = [{"market_ticker": "M", "event_ticker": "E", "target_time_utc": "2026-09-10T14:00:00Z", "threshold_f": "70.99", "comparison": "above", "result": "yes"}, {"market_ticker": "MISS", "event_ticker": "E", "target_time_utc": "2026-09-10T15:00:00Z", "threshold_f": "70", "comparison": "above", "result": "no"}]
        observations = [{"station": "KNYC", "valid_utc": "2026-09-10T14:00:00Z", "temperature_f": "71.0", "status": "settled", "retrieved_at_utc": "2026-09-10T15:20:00Z", "raw_sha256": "h", "raw_path": "raw"}]
        rows = join(contracts, observations); self.assertEqual(rows[0]["source_observed_yes"], "true"); self.assertEqual(rows[0]["label_available_ts"], "2026-09-10T15:20:00Z"); self.assertEqual(rows[1]["source_valid_utc"], ""); self.assertEqual(rows[1]["kalshi_result"], "no"); self.assertEqual(rows[1]["source_temperature_f"], "")

    def test_uses_whole_degree_bucket_boundary(self):
        contracts = [{"market_ticker": "M", "event_ticker": "E", "target_time_utc": "2026-09-10T14:00:00Z", "threshold_f": "73.99", "bucket_floor_f": "74", "comparison": "above", "result": "yes"}]
        observations = [{"station": "KNYC", "valid_utc": "2026-09-10T14:00:00.000Z", "temperature_f": "73.9", "retrieved_at_utc": "2026-09-10T15:20:00Z"}]
        self.assertEqual(join(contracts, observations)[0]["source_observed_yes"], "true")

if __name__ == "__main__": unittest.main()

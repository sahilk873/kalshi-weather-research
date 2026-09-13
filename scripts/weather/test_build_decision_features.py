import json
import unittest
from build_decision_features import build


class DecisionFeatureTests(unittest.TestCase):
    def test_joins_only_receipts_available_by_decision(self):
        contracts = [{"market_ticker": "M", "decision_ts": "2026-01-01T10:00:00Z", "target_time_utc": "2026-01-01T11:00:00Z", "latitude": "40.7", "longitude": "-74.0"}]
        observations = [{"station": "KNYC", "valid_utc": "2026-01-01T11:00:00Z", "receipt_utc": "2026-01-01T09:00:00Z", "temperature_c": "20", "raw_sha256": "h"}]
        rows, rejected = build(contracts, observations, [])
        self.assertEqual(len(rows), 1); self.assertFalse(rejected)
        self.assertEqual(rows[0]["horizon_minutes"], 60)

    def test_late_sources_are_rejected(self):
        contracts = [{"market_ticker": "M", "decision_ts": "2026-01-01T10:00:00Z", "target_time_utc": "2026-01-01T11:00:00Z", "latitude": "40.7", "longitude": "-74.0"}]
        observations = [{"station": "KNYC", "valid_utc": "2026-01-01T11:00:00Z", "receipt_utc": "2026-01-01T10:01:00Z"}]
        rows, rejected = build(contracts, observations, [])
        self.assertFalse(rows); self.assertEqual(rejected[0]["reason"], "late_observations")

    def test_derived_temporal_and_distribution_features_are_emitted(self):
        contracts = [{"market_ticker": "M", "decision_ts": "2026-01-01T10:00:00Z", "target_time_utc": "2026-01-01T11:00:00Z", "latitude": "40.7", "longitude": "-74.0"}]
        observations = [
            {"station": "KNYC", "valid_utc": "2026-01-01T10:00:00Z", "receipt_utc": "2026-01-01T09:00:00Z", "temperature_f": "40", "raw_sha256": "a"},
            {"station": "KLGA", "valid_utc": "2026-01-01T11:00:00Z", "receipt_utc": "2026-01-01T09:00:00Z", "temperature_f": "45", "raw_sha256": "b"},
        ]
        forecasts = [{"valid_time_utc": "2026-01-01T11:00:00Z", "source_receipt_time": "2026-01-01T09:00:00Z", "value": str(value)} for value in (44, 46, 48)]
        rows, rejected = build(contracts, observations, forecasts)
        self.assertFalse(rejected)
        features = json.loads(rows[0]["features_json"])
        self.assertEqual(features["forecast_member_count"], 3)
        self.assertIn("running_max_temperature", features)
        self.assertIn("spatial_temperature_gradient_range", features)
        self.assertIn("solar_elevation_deg", features)

    def test_exact_settlement_station_cannot_be_replaced_by_nearby_station(self):
        contracts = [{"market_ticker": "M", "settlement_station": "KNYC", "decision_ts": "2026-01-01T10:00:00Z", "target_time_utc": "2026-01-01T11:00:00Z"}]
        observations = [{"station": "KLGA", "valid_utc": "2026-01-01T10:00:00Z", "receipt_utc": "2026-01-01T09:00:00Z", "temperature_f": "45", "raw_sha256": "b"}]
        rows, rejected = build(contracts, observations, [])
        self.assertFalse(rows)
        self.assertEqual(rejected[0]["reason"], "missing_exact_settlement_station_observations")


if __name__ == "__main__": unittest.main()

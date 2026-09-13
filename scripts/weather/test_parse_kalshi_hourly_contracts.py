import unittest
from parse_kalshi_hourly_contracts import parse

class HourlyContractParseTests(unittest.TestCase):
    def test_parses_target_threshold_source_and_rules_hash(self):
        rows = parse([{"event_ticker": "KXTEMPNYCH-26SEP1010", "strike_date": "2026-09-10T14:00:00Z", "sub_title": "On Sep 10, 2026 at 10am EDT"}], [{"event_ticker": "KXTEMPNYCH-26SEP1010", "ticker": "KXTEMPNYCH-26SEP1010-T70.99", "title": "Will the temp be above 70.99°?", "yes_sub_title": "71° or above", "status": "finalized", "result": "yes"}], {"settlement_sources": [{"name": "The Weather Company", "url": "https://weather.com/kalshi"}], "contract_terms_url": "terms", "last_updated_ts": "2026-09-09T00:00:00Z"})
        self.assertEqual(len(rows), 1); self.assertEqual(rows[0]["target_time_utc"], "2026-09-10T14:00:00Z"); self.assertEqual(rows[0]["threshold_f"], 70.99); self.assertEqual(rows[0]["comparison"], "above"); self.assertEqual(rows[0]["bucket_floor_f"], 71.0); self.assertTrue(len(rows[0]["rules_hash"]) == 64)
        self.assertEqual(rows[0]["settlement_station"], "KNYC")
        self.assertEqual(rows[0]["settlement_station_method"], "user_supplied_listing_coordinate_registry")

    def test_event_settlement_source_overrides_series_source(self):
        rows = parse([{"event_ticker": "E", "strike_date": "2026-09-10T14:00:00Z", "settlement_sources": [{"name": "AccuWeather", "url": "https://kalshi.com/weather/central-park"}]}], [{"event_ticker": "E", "ticker": "E-T70", "title": "above 70", "yes_sub_title": "71° or above"}], {"settlement_sources": [{"name": "The Weather Company", "url": "https://weather.com/kalshi"}]})
        self.assertEqual(rows[0]["settlement_source_name"], "AccuWeather")
        self.assertEqual(rows[0]["settlement_source_url"], "https://kalshi.com/weather/central-park")

if __name__ == "__main__": unittest.main()

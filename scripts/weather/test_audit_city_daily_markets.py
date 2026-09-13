import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from audit_city_daily_markets import audit


class CityDailyAuditTest(unittest.TestCase):
    def test_sources_and_unresolved_rows_are_explicit(self):
        report = audit([
            {"series_ticker": "KXHIGHNY", "event_ticker": "KXHIGHNY-26SEP12-T80", "result": "yes", "settlement_sources": "{'name': 'The Weather Company', 'url': 'https://weather.com/kalshi'}"},
            {"series_ticker": "KXHIGHNY", "event_ticker": "KXHIGHNY-26SEP13-T80", "result": "", "settlement_sources": "{'name': 'The Weather Company', 'url': 'https://weather.com/kalshi'}"},
        ])
        row = report["series"]["KXHIGHNY"]
        self.assertEqual(row["event_rows"], 2)
        self.assertEqual(row["resolved_market_rows"], 1)
        self.assertEqual(row["settlement_source_names"], ["The Weather Company"])
        self.assertFalse(row["rules_reproduced"])


if __name__ == "__main__":
    unittest.main()

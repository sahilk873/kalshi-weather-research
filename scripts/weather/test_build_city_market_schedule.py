import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_city_market_schedule import build_labels, build_schedule


class CityScheduleTest(unittest.TestCase):
    def test_groups_markets_and_joins_proxy_label(self):
        markets = [
            {"series_ticker": "KXHIGHNY", "event_ticker": "KXHIGHNY-26SEP12", "open_time": "2026-09-11T14:00:00Z"},
            {"series_ticker": "KXHIGHNY", "event_ticker": "KXHIGHNY-26SEP12", "open_time": "2026-09-11T15:00:00Z"},
        ]
        schedule, rejected = build_schedule(markets)
        self.assertFalse(rejected); self.assertEqual(len(schedule), 1)
        labels, rejected = build_labels(schedule, [{"city": "nyc", "date": "2026-09-12", "tmax_f": "80", "tmin_f": "60", "label_available_ts": "2026-09-14T00:00:00Z"}])
        self.assertFalse(rejected); self.assertEqual(labels[0]["observed_f"], "80")


if __name__ == "__main__": unittest.main()

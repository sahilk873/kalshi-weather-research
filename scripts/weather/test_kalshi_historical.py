import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from kalshi_historical import event_date, SERIES


class HistoricalTickerTests(unittest.TestCase):
    def test_daily_and_hourly_event_tickers_parse(self):
        self.assertEqual(event_date({"event_ticker": "KXHIGHTPHX-26SEP12"}), "2026-09-12")
        self.assertEqual(event_date({"event_ticker": "KXTEMPNYCH-26SEP1200"}), "2026-09-12")
        self.assertEqual(event_date({"event_ticker": "not-a-date"}), "")

    def test_auxiliary_daily_series_are_explicit(self):
        self.assertEqual(SERIES["KXHIGHNY"], ("nyc", "high"))
        self.assertEqual(SERIES["KXLOWTLAX"], ("la", "low"))
        self.assertEqual(SERIES["KXHIGHAUS"], ("austin", "high"))


if __name__ == "__main__":
    unittest.main()

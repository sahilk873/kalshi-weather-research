import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from kalshi_meta import is_temperature_series, series_context
from stations import KALSHI_SERIES_CATALOG


class TemperatureSeriesCatalogTests(unittest.TestCase):
    def test_seed_contains_current_and_historical_hourly_families(self):
        for ticker in (
            "KXTEMPNYCHS", "KXTEMPLAXHS", "KXTEMPCHIHS", "KXTEMPMIAH",
            "KXTEMPNYCH", "KXTEMPLAXH", "KXTEMPCHIH", "KXTEMPAUSH",
            "KXTEMPDCH",
        ):
            self.assertIn(ticker, KALSHI_SERIES_CATALOG)

    def test_seed_contains_daily_newark_and_broad_cities(self):
        self.assertEqual(KALSHI_SERIES_CATALOG["KXHIGHTEWR"],
                         ("newark", "high", "daily"))
        self.assertEqual(KALSHI_SERIES_CATALOG["KXLOWTCHI"],
                         ("chicago", "low", "daily"))

    def test_unknown_temperature_series_gets_safe_context(self):
        context = series_context("KXTEMPNEWCITYH")
        self.assertEqual(context.key, "unknown")
        self.assertEqual(context.tz_name, "UTC")

    def test_discovery_filter_requires_climate_temperature(self):
        self.assertTrue(is_temperature_series({
            "ticker": "KXHIGHTNEW", "title": "Highest temperature in New City",
            "category": "Climate and Weather",
        }))
        self.assertFalse(is_temperature_series({
            "ticker": "KXHIGHSPORT", "title": "Highest score",
            "category": "Sports",
        }))


if __name__ == "__main__":
    unittest.main()

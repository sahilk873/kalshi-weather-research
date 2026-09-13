import unittest

from compare_ghcnh_ghcn_daily import compare


class CompareDailyTests(unittest.TestCase):
    def test_overlap_and_error_metrics(self):
        result = compare(
            [{"station": "USW00094728", "local_date": "2024-01-01", "tmax_f": "40", "tmin_f": "30"}],
            [{"city": "nyc", "date": "2024-01-01", "tmax_f": "38", "tmin_f": "31"}],
        )
        self.assertEqual(result["overlap_station_days"], 1)
        self.assertEqual(result["comparisons"][0]["overlap_days"], 1)
        self.assertEqual(result["comparisons"][0]["mae_f"], 2.0)


if __name__ == "__main__":
    unittest.main()

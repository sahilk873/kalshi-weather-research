import unittest

from build_ghcnh_daily_extrema import build


class GHCNhDailyExtremaTests(unittest.TestCase):
    def test_uses_local_date_and_preserves_provenance(self):
        rows = [
            {"station": "USW00094728", "valid_utc": "2024-01-02T05:30:00Z", "temperature_f": "40", "raw_path": "a", "sha256": "ha"},
            {"station": "USW00094728", "valid_utc": "2024-01-02T06:30:00Z", "temperature_f": "35", "raw_path": "b", "sha256": "hb"},
        ]
        result = build(rows)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["local_date"], "2024-01-02")
        self.assertEqual(result[0]["tmax_f"], "40.000")
        self.assertEqual(result[0]["tmin_f"], "35.000")
        self.assertEqual(result[0]["raw_hashes"], "ha|hb")


if __name__ == "__main__":
    unittest.main()

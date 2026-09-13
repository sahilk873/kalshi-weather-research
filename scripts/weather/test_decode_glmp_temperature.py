import unittest
from decode_glmp_temperature import CITY_COORDS, _utc_from_grib


class GLMPDecodeTests(unittest.TestCase):
    def test_grib_time_conversion_and_city_registry(self):
        self.assertEqual(_utc_from_grib(20260912, 1930), "2026-09-12T19:30:00Z")
        self.assertIn("nyc", CITY_COORDS)


if __name__ == "__main__": unittest.main()

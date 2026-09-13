import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from decode_point_forecasts import convert_value


class DecodeTests(unittest.TestCase):
    def test_temperature_kelvin_to_fahrenheit(self):
        value, source, output = convert_value("2t", 273.15)
        self.assertAlmostEqual(value, 32.0, places=6)
        self.assertEqual((source, output), ("K", "F"))

    def test_unknown_field_is_not_synthesized(self):
        self.assertIsNone(convert_value("unknown", 1.0))

    def test_physical_fields_are_decoded_with_units(self):
        value, source, output = convert_value("prmsl", 100000.0)
        self.assertAlmostEqual(value, 1000.0)
        self.assertEqual((source, output), ("Pa", "hPa"))


if __name__ == "__main__":
    unittest.main()

import unittest
from decode_rtma_point import KEEP, STATIONS


class RtmaDecoderTest(unittest.TestCase):
    def test_registered_fields_and_stations(self):
        self.assertIn("2t", KEEP)
        self.assertEqual(len(STATIONS), 5)

    def test_longitude_convention(self):
        self.assertLess(STATIONS["phx"][1], 0)


if __name__ == "__main__":
    unittest.main()

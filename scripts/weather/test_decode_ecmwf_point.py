import unittest
from decode_ecmwf_point import POINTS

class EcmwfDecodeTest(unittest.TestCase):
    def test_registered_points(self):
        self.assertEqual(set(POINTS), {"phx","lv","nyc","la","austin"})

if __name__ == "__main__": unittest.main()

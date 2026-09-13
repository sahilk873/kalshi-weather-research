import unittest
from extract_goes_cloud import _pixel

class GoesExtractTest(unittest.TestCase):
    def test_projection_returns_finite_coordinates(self):
        class P:
            attrs = {"longitude_of_projection_origin": -137, "semi_major_axis": 6378137, "semi_minor_axis": 6356752.31414, "perspective_point_height": 35786023}
        x, y = _pixel(33.4, -112.0, P())
        self.assertTrue(abs(x) < 1 and abs(y) < 1)

if __name__ == "__main__": unittest.main()

import sys
import unittest
from datetime import date
from pathlib import Path
from urllib.parse import unquote

sys.path.insert(0, str(Path(__file__).resolve().parent))
from probe_goes_cloud import listing_url


class GoesProbeTest(unittest.TestCase):
    def test_listing_url_contains_product_date_and_hour_prefix(self):
        url = listing_url("G16", "ABI-L2-MCMIPF", date(2025, 1, 2), 3)
        self.assertIn("ABI-L2-MCMIPF/2025/002/03/", unquote(url))
        self.assertIn("noaa-goes16.s3.amazonaws.com", url)


if __name__ == "__main__": unittest.main()

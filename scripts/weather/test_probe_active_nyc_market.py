import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from probe_active_nyc_market import probe


class ActiveMarketProbeTests(unittest.TestCase):
    def test_archives_empty_active_response_without_fabrication(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch("probe_active_nyc_market.http_get_json", side_effect=[{"markets": [], "cursor": ""}, {"events": [], "cursor": ""}]):
                result = probe(Path(directory))
            self.assertEqual(result["active_market_count"], 0)
            self.assertFalse(result["pass"])
            self.assertTrue(Path(result["raw_path"]).exists())


if __name__ == "__main__": unittest.main()

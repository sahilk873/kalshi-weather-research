import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from collect_ghcnh_year import fetch_year


class Response:
    def __enter__(self): return self
    def __exit__(self, *args): return None
    def read(self): return b"STATION|DATE\nUSW0001|202401010000\n"


class CollectGHCNhYearTests(unittest.TestCase):
    def test_fetch_writes_hash_and_complete_marker(self):
        with tempfile.TemporaryDirectory() as td, patch("collect_ghcnh_year.urllib.request.urlopen", return_value=Response()):
            row = fetch_year("nyc", "USW00094728", 2024, Path(td))
            self.assertTrue(row["complete_year_file"])
            self.assertEqual(row["bytes"], 34)
            self.assertTrue(Path(row["raw_path"]).exists())


if __name__ == "__main__":
    unittest.main()

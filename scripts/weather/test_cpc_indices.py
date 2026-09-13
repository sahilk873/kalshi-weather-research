import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cpc_indices import fetch


class CpcIndicesTest(unittest.TestCase):
    def test_normalizes_index(self):
        class Response:
            def read(self): return b" SEAS  YR   TOTAL   ANOM\n  DJF 2020  27.10  0.50\n"
        with tempfile.TemporaryDirectory() as d, patch("cpc_indices.urlopen", return_value=Response()):
            root = Path(d); n = fetch(root / "raw.txt", root / "oni.csv")
            self.assertEqual(n, 1); self.assertIn("nino34_3mo_mean_c", root.joinpath("oni.csv").read_text())


if __name__ == "__main__": unittest.main()

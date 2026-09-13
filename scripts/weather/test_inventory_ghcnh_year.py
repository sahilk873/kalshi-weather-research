import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from inventory_ghcnh_year import inventory


class GhcnhYearInventoryTest(unittest.TestCase):
    def test_hashes_year_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "GHCNh_USW00023183_2026.psv"
            path.write_bytes(b"STATION|TIME\nUSW00023183|2026\n")
            result = inventory(root, 2026, ["phx"])
            self.assertTrue(result["rows"][0]["complete_year_file"])
            self.assertEqual(result["rows"][0]["sha256"], hashlib.sha256(path.read_bytes()).hexdigest())


if __name__ == "__main__":
    unittest.main()

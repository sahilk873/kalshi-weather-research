import tempfile
import unittest
from pathlib import Path

from parse_ghcnh_year import parse_file


HEADER = "STATION|Station_name|DATE|Year|Month|Day|Hour|Minute|LATITUDE|LONGITUDE|ELEVATION|temperature|dew_point_temperature|temperature_Quality_Code|temperature_Report_Type\n"


class GhcnhParseTest(unittest.TestCase):
    def test_converts_celsius_and_keeps_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "GHCNh_USW00023183_2026.psv"
            path.write_text(HEADER + "USW00023183|PHX|2026-01-01T00:00:00|-|-|-|-|-|33|-112|339.2|0| -5|1|FM15\n".replace("| -5", "|-5"))
            rows, rejected = parse_file(path, "2026-01-01T00:05:00Z")
            self.assertEqual(rejected, 0)
            self.assertAlmostEqual(rows[0]["temperature_f"], 32.0)
            self.assertAlmostEqual(rows[0]["dewpoint_f"], 23.0)
            self.assertEqual(len(rows[0]["sha256"]), 64)
            self.assertEqual(rows[0]["source_receipt_time"], "2026-01-01T00:05:00Z")


if __name__ == "__main__":
    unittest.main()

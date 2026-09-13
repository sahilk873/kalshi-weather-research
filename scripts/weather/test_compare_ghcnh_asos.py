import json, tempfile, unittest
from pathlib import Path
from compare_ghcnh_asos import compare


class CompareGhcnhAsosTest(unittest.TestCase):
    def test_exact_timestamp_delta(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "gh.csv").write_text("station,valid_utc,temperature_f\nX,2026-01-01T00:00:00Z,50\n")
            (root / "as.csv").write_text("station,valid_utc,tmpf\nX,2026-01-01T00:00:00Z,49\n")
            result = compare(root / "gh.csv", root / "as.csv")
            self.assertEqual(result["numeric_matches"], 1)
            self.assertEqual(result["mean_delta_f"], 1.0)


if __name__ == "__main__": unittest.main()

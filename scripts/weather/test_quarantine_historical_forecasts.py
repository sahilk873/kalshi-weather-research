import csv, json, tempfile, unittest
from pathlib import Path
from quarantine_historical_forecasts import build


class QuarantineTests(unittest.TestCase):
    def test_only_empty_payloads_are_quarantined_with_hash(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); raw = root / "x.json"; raw.write_text(json.dumps({"hourly": {"time": ["2026-01-01"], "temperature_2m": [None]}}))
            manifest = root / "manifest.csv"; manifest.write_text(f"raw_path\n{raw.relative_to(root)}\n")
            rows = build(manifest, root)
            self.assertEqual(len(rows), 1); self.assertEqual(rows[0]["reviewed"], "true"); self.assertTrue(rows[0]["sha256"])


if __name__ == "__main__": unittest.main()

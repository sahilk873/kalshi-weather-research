import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from canonicalize_city_asos import canonicalize


class CanonicalAsosTest(unittest.TestCase):
    def test_richer_redelivery_is_retained_and_both_decisions_recorded(self):
        rows = [
            {"station": "AUS", "valid_utc": "2026-01-01T00:00:00Z", "tmpf": "", "raw_metar": "KAUS AUTO"},
            {"station": "AUS", "valid_utc": "2026-01-01T00:00:00Z", "tmpf": "70", "raw_metar": "KAUS AO2"},
        ]
        canonical, decisions = canonicalize(rows)
        self.assertEqual(len(canonical), 1)
        self.assertEqual(canonical[0]["tmpf"], "70")
        self.assertEqual([r["decision"] for r in decisions], ["retained", "superseded"])


if __name__ == "__main__":
    unittest.main()

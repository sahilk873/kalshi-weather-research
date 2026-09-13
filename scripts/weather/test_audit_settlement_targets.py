import tempfile
import unittest
from pathlib import Path
from audit_settlement_targets import audit


class SettlementTargetAuditTests(unittest.TestCase):
    def test_unverified_coordinates_are_counted_without_failing_source_integrity(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "contracts.csv"
            path.write_text("target_time_utc,settlement_source_name,settlement_station_method,rules_hash\n2026-01-01T00:00:00Z,TWC,series_registry_mapping_unverified_coordinates,abc\n")
            result = audit(path)
            self.assertTrue(result["pass"])
            self.assertEqual(result["unverified_or_unresolved_station"], 1)


if __name__ == "__main__": unittest.main()

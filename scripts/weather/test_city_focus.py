"""Tests for the active auxiliary city registry and read-only audit."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from city_focus import CITIES, audit_inputs


class CityFocusTest(unittest.TestCase):
    def test_registry_has_active_cities_and_sources(self):
        self.assertEqual(set(CITIES), {"nyc", "la", "austin"})
        self.assertEqual(CITIES["nyc"].ghcn_station, "USW00094728")
        self.assertEqual(CITIES["la"].cli_product, "CLILAX")
        self.assertEqual(CITIES["austin"].settlement_station, "KAUS")

    def test_missing_root_is_read_only_empty_audit(self):
        with tempfile.TemporaryDirectory() as temp:
            report = audit_inputs(Path(temp))
        self.assertEqual(set(report["cities"]), set(CITIES))
        self.assertTrue(all(row["label_rows"] == 0 for row in report["cities"].values()))


if __name__ == "__main__":
    unittest.main()

import unittest
from gefs_ensemble import parse_response


class GefsEnsembleTests(unittest.TestCase):
    def test_supported_convective_inhibition_is_normalized_to_cin(self):
        payload = {"hourly": {"time": ["2026-09-12T00:00"], "convective_inhibition_member00": [1.5]}}
        rows = parse_response(payload, "nyc", "ncep_gefs025", "2026-09-12T00:00:00Z")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["variable"], "cin")


if __name__ == "__main__": unittest.main()

import unittest
from join_goes_cloud_state import build

class JoinGoesTest(unittest.TestCase):
    def test_future_cloud_is_not_joined(self):
        asos = [{"station": "PHX", "valid_utc": "2025-01-01T12:00:00Z", "local_date": "2025-01-01", "tmpf": "70"}]
        cloud = [{"station": "phx", "time_coverage_start": "2025-01-01T12:01:00Z", "source_file": "x", "source_sha256": "h", "ir_brightness_temperature_k_mean": "290", "dqf_clear_fraction": "1"}]
        rows, _ = build(asos, cloud); self.assertFalse(rows)

if __name__ == "__main__": unittest.main()

import unittest
from build_settlement_window_extrema import build

class SettlementWindowTests(unittest.TestCase):
    def test_phx_window_and_provenance(self):
        rows=[{"station":"USW00023183","valid_utc":"2026-01-01T07:00:00Z","temperature_f":"40","sha256":"h"},{"station":"USW00023183","valid_utc":"2026-01-02T06:00:00Z","temperature_f":"30","sha256":"h"}]
        out=build(rows); self.assertEqual(len(out),1); self.assertEqual(out[0]["city"],"phx"); self.assertEqual(out[0]["observation_count"],"2")

    def test_lv_summer_window_uses_pst_offset(self):
        rows=[{"station":"USW00023169","valid_utc":"2026-07-01T08:00:00Z","temperature_f":"90","sha256":"h"}]
        out=build(rows)
        self.assertEqual(out[0]["window_start_utc"], "2026-07-01T08:00:00Z")
        self.assertEqual(out[0]["window_end_utc"], "2026-07-02T08:00:00Z")

if __name__ == "__main__": unittest.main()

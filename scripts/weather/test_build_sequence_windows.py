import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_sequence_windows import build


class SequenceWindowTest(unittest.TestCase):
    def test_window_is_fixed_length_and_label_is_after_end(self):
        state = [{"city": "nyc", "local_date": "2025-01-01", "feature_asof_utc": f"2025-01-01T{h:02d}:00:00Z", "current_temperature_f": str(h)} for h in range(4)]
        labels = [{"city": "nyc", "date": "2025-01-01", "tmax_f": "80", "tmin_f": "60", "label_available_ts": "2025-01-02T12:00:00Z"}]
        rows, rejected = build(state, labels, window=3)
        self.assertFalse(rejected); self.assertEqual(len(rows), 4); self.assertEqual(len(json.loads(rows[0]["sequence_json"])), 3); self.assertLess(rows[0]["window_end_utc"], rows[0]["label_available_ts"])

    def test_gap_gate_and_datetime_availability(self):
        state = [{"city": "nyc", "local_date": "2025-01-01", "feature_asof_utc": t, "current_temperature_f": "1"} for t in ("2025-01-01T00:00:00Z", "2025-01-01T01:00:00Z", "2025-01-01T04:00:00Z")]
        labels = [{"city": "nyc", "date": "2025-01-01", "tmax_f": "80", "tmin_f": "60", "label_available_ts": "2025-01-02T12:00:00.000000Z"}]
        rows, rejected = build(state, labels, window=3, max_gap_minutes=90)
        self.assertFalse(rows)
        self.assertTrue(any(r["reason"] == "sequence_gap" for r in rejected))


if __name__ == "__main__": unittest.main()

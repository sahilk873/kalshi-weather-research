import csv
import tempfile
import unittest
from pathlib import Path

from evaluate_goes_incremental import evaluate


class GoesIncrementalTest(unittest.TestCase):
    def test_asof_and_summary(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            cloud = root / "cloud.csv"
            labels = root / "labels.csv"
            cloud.write_text("station,city,valid_utc,local_date,observed_high_so_far_f,observed_low_so_far_f,cloud_time_utc,cloud_age_minutes,ir_brightness_temperature_k_mean,dqf_clear_fraction\nPHX,phx,2026-01-01T12:00:00Z,2026-01-01,60,40,2026-01-01T11:00:00Z,60,273.15,1\n")
            labels.write_text("city,date,tmax_f,tmin_f,label_available_ts\nphx,2026-01-01,70,35,2026-01-02T12:00:00Z\n")
            out, rej = root / "rows.csv", root / "reject.csv"
            accepted, rejected = evaluate(cloud, labels, out, rej)
            self.assertEqual((accepted, rejected), (2, 0))
            self.assertTrue((root / "rows_summary.csv").exists())

    def test_late_cloud_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "cloud.csv").write_text("station,city,valid_utc,local_date,observed_high_so_far_f,observed_low_so_far_f,cloud_time_utc,cloud_age_minutes,ir_brightness_temperature_k_mean,dqf_clear_fraction\nPHX,phx,2026-01-01T12:00:00Z,2026-01-01,60,40,2026-01-01T13:00:00Z,60,273.15,1\n")
            (root / "labels.csv").write_text("city,date,tmax_f,tmin_f,label_available_ts\nphx,2026-01-01,70,35,2026-01-02T12:00:00Z\n")
            accepted, rejected = evaluate(root / "cloud.csv", root / "labels.csv", root / "rows.csv", root / "reject.csv")
            self.assertEqual((accepted, rejected), (0, 1))


if __name__ == "__main__":
    unittest.main()

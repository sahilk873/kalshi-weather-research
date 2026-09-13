import json, tempfile, unittest
from pathlib import Path
from live_schedule import schedule, validate

class LiveScheduleTest(unittest.TestCase):
    def test_manifest_contains_report_jobs_and_is_valid(self):
        value = schedule(); self.assertEqual(validate(value), []); names = {r["job"] for r in value["jobs"]}
        self.assertTrue({"awc_metar", "intraday_market_capture", "gefs_run_detector", "daily_data_qc", "challenger_retrain"} <= names)
    def test_continuous_jobs_have_zero_cadence(self):
        for row in schedule()["jobs"]: self.assertEqual(row["continuous"], row["cadence_seconds"] == 0)
    def test_invalid_duplicate_and_negative_cadence(self):
        value = {"jobs": [{"job":"x", "cadence_seconds":-1, "continuous":False}, {"job":"x", "cadence_seconds":1, "continuous":False}]}
        self.assertTrue(validate(value))
    def test_cli_writes_json(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "schedule.json"; import subprocess, sys
            r = subprocess.run([sys.executable, str(Path(__file__).with_name("live_schedule.py")), "--output", str(out)], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr); self.assertEqual(validate(json.loads(out.read_text())), [])

if __name__ == "__main__": unittest.main()

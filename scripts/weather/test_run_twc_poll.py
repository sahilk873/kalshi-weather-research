import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from run_twc_poll import run


class TWCPollTests(unittest.TestCase):
    def test_bounded_runner_uses_deterministic_dates_and_sleeps(self):
        with tempfile.TemporaryDirectory() as d, patch("run_twc_poll.collect", side_effect=[(1, 2), (3, 4)]) as mocked:
            sleeps = []
            result = run(Path(d), stations=["KNYC"], iterations=2, interval_seconds=9,
                         today=lambda: date(2026, 9, 13), sleep=sleeps.append)
        self.assertEqual(result, [(1, 2), (3, 4)])
        self.assertEqual(mocked.call_count, 2)
        self.assertEqual(mocked.call_args_list[0].args[1:3], ("2026-09-07", "2026-09-13"))
        self.assertEqual(sleeps, [9])

    def test_invalid_cadence_and_empty_station_list_fail_closed(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):
                run(Path(d), interval_seconds=0)
            with self.assertRaises(ValueError):
                run(Path(d), stations=[], iterations=1)


if __name__ == "__main__":
    unittest.main()

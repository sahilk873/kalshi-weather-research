import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from run_awc_poll import run


class AWCPollTests(unittest.TestCase):
    def test_bounded_runner_polls_and_sleeps_between_pulls(self):
        with tempfile.TemporaryDirectory() as d, patch("run_awc_poll.collect", side_effect=[{"rows": 1}, {"rows": 2}]) as mocked:
            sleeps = []
            result = run(["KJFK"], Path(d), iterations=2, interval_seconds=7, sleep=sleeps.append)
        self.assertEqual(result, [{"rows": 1}, {"rows": 2}])
        self.assertEqual(mocked.call_count, 2)
        self.assertEqual(sleeps, [7])

    def test_invalid_cadence_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):
                run(["KJFK"], Path(d), interval_seconds=0)


if __name__ == "__main__":
    unittest.main()

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from run_intraday_capture import capture


class IntradayCaptureTests(unittest.TestCase):
    def test_daily_only_probe_does_not_request_books(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            active = {"open_tickers": ["KXHIGHNY-26SEP13-T80"], "hourly_open_count": 0}
            with patch("run_intraday_capture.probe", return_value=active), \
                 patch("run_intraday_capture.run_awc", return_value=[{}]), \
                 patch("run_intraday_capture.run_twc", return_value=[{}]), \
                 patch("run_intraday_capture.collect_rest_orderbooks") as books:
                result = capture(root)
            books.assert_not_called()
            self.assertFalse(result["pass"])
            self.assertEqual(result["reason"], "no_hourly_markets_open")

    def test_open_hourly_without_credential_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            active = {"open_tickers": ["KXTEMPNYCH-26SEP13-T80"]}
            with patch("run_intraday_capture.probe", return_value=active), \
                 patch("run_intraday_capture.run_awc", return_value=[{}]), \
                 patch("run_intraday_capture.run_twc", return_value=[{}]), \
                 patch("run_intraday_capture.collect_rest_orderbooks") as books:
                result = capture(root, credential_file=None)
            books.assert_not_called()
            self.assertEqual(result["reason"], "hourly_markets_open_but_credential_file_not_supplied")
            self.assertFalse(result["pass"])


if __name__ == "__main__":
    unittest.main()

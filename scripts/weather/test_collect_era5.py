import os, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
from collect_era5 import collect, request_spec


class Era5Test(unittest.TestCase):
    def test_request_spec_is_explicit(self):
        spec=request_spec("2026-01-02",["2m_temperature"],[42,-118,29,-70])
        self.assertEqual(spec["year"],"2026"); self.assertEqual(len(spec["time"]),24)

    @patch.dict(os.environ, {}, clear=True)
    def test_missing_credentials_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(RuntimeError,"CDS_API_KEY"):
                collect("2026-01-02",["2m_temperature"],[42,-118,29,-70],Path(d)/"x.nc")


if __name__ == "__main__": unittest.main()

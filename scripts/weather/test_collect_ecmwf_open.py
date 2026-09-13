import tempfile, unittest
from pathlib import Path
from unittest.mock import patch
from collect_ecmwf_open import collect


class _Client:
    def retrieve(self, **kwargs): Path(kwargs["target"]).write_bytes(b"grib")


class EcmwfTest(unittest.TestCase):
    @patch.dict("sys.modules", {"ecmwf": object(), "ecmwf.opendata": type("M", (), {"Client": lambda **_: _Client()})})
    def test_manifest_fields_and_hash(self):
        with tempfile.TemporaryDirectory() as d:
            row=collect("20260912",0,Path(d)/"x.grib2")
            self.assertEqual(row["parameter"],"2t"); self.assertFalse(row["decoded"]); self.assertEqual(row["bytes"],4)


if __name__ == "__main__": unittest.main()

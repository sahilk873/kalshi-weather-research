import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from collect_glmp_temperature import collect


class GLMPTests(unittest.TestCase):
    def test_discovers_temperature_product_and_preserves_manifest(self):
        responses = {
            "https://nomads.ncep.noaa.gov/pub/data/nccf/com/glmp/prod/": b'<a href="glmp.20260912/">x</a>',
            "https://nomads.ncep.noaa.gov/pub/data/nccf/com/glmp/prod/glmp.20260912/": b'<a href="glmp.t1930z.fcsts_t.g.co.grib2">x</a>',
            "https://nomads.ncep.noaa.gov/pub/data/nccf/com/glmp/prod/glmp.20260912/glmp.t1930z.fcsts_t.g.co.grib2": b'GRIB test payload',
        }
        with tempfile.TemporaryDirectory() as directory, patch("collect_glmp_temperature._get", side_effect=lambda url: responses[url]):
            result = collect(Path(directory)); manifest = __import__("json").loads((Path(directory) / "manifest.json").read_text())
            self.assertEqual(result["cycle_file"], "glmp.t1930z.fcsts_t.g.co.grib2")
            self.assertEqual(result["initialization_time_utc"], "2026-09-12T19:30:00Z")
            self.assertEqual(len(manifest["snapshots"]), 1)

    def test_rejects_non_grib_payload(self):
        with tempfile.TemporaryDirectory() as directory:
            responses = {
                "https://nomads.ncep.noaa.gov/pub/data/nccf/com/glmp/prod/": b'<a href="glmp.20260912/">x</a>',
                "https://nomads.ncep.noaa.gov/pub/data/nccf/com/glmp/prod/glmp.20260912/": b'<a href="glmp.t1930z.fcsts_t.g.co.grib2">x</a>',
                "https://nomads.ncep.noaa.gov/pub/data/nccf/com/glmp/prod/glmp.20260912/glmp.t1930z.fcsts_t.g.co.grib2": b'not grib',
            }
            with patch("collect_glmp_temperature._get", side_effect=lambda url: responses[url]):
                with self.assertRaises(RuntimeError): collect(Path(directory))


if __name__ == "__main__": unittest.main()

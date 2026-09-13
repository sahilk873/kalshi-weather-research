import json, tempfile, unittest
from pathlib import Path
from parse_homr import parse


class ParseHomrTest(unittest.TestCase):
    def test_extracts_identifiers_and_relocations(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"x.json"; path.write_text(json.dumps({"stationCollection":{"stations":[{"identifiers":[{"idType":"GHCND","id":"X","date":{"beginDate":"2000","endDate":"Present"}}],"relocations":[{"relocation":"1 mi N","date":"2010"}],"location":{"elevations":[{"elevationMeters":"123.4","date":{"beginDate":"2000","endDate":"Present"}}]}}]}}))
            rows=parse(path,"phx","X")
            self.assertEqual({r["record_type"] for r in rows},{"identifier","relocation","elevation"})
            self.assertEqual(next(r["detail"] for r in rows if r["record_type"] == "elevation"), "123.4")


if __name__ == "__main__": unittest.main()

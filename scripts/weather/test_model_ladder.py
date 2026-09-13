import tempfile, unittest
from pathlib import Path
from model_ladder import audit

class ModelLadderTests(unittest.TestCase):
    def test_missing_inputs_are_explicit_and_ladder_not_complete(self):
        with tempfile.TemporaryDirectory() as d:
            result = audit(Path(d)); self.assertFalse(result["complete"]); self.assertEqual(len(result["models"]), 14); self.assertEqual(result["models"][0]["status"], "data_missing")
    def test_rows_make_candidate_eligible(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"ghcn_city"; p.mkdir(); (p/"labels_daily.csv").write_text("x\nvalue\n")
            result=audit(Path(d)); self.assertEqual(result["models"][0]["status"], "eligible_for_run")
            self.assertFalse(result["models"][0]["trained"])
            self.assertFalse(result["models"][0]["promotion_eligible"])

    def test_deep_challengers_are_explicitly_deferred(self):
        with tempfile.TemporaryDirectory() as d:
            result = audit(Path(d))
            self.assertEqual(result["models"][-1]["status"], "deferred_optional")
            self.assertFalse(result["complete"])

    def test_aviation_only_lamp_rows_do_not_count_as_temperature_guidance(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "lamp"; path.mkdir()
            (path / "station_forecasts.csv").write_text("field,value\nCIG,6\nVIS,7\n")
            result = audit(Path(d))
            self.assertEqual(result["counts"]["lamp"], 0)
            self.assertEqual(result["models"][4]["status"], "data_missing")
if __name__ == "__main__": unittest.main()

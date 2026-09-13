"""P1 evaluator tests."""
from __future__ import annotations
import csv,tempfile,unittest
from pathlib import Path
import evaluate_forecast_skill as ev
def f(**x):
    r={"event_ticker":"KXHIGHTPHX-26JUL01","decision_time_utc":"2026-06-30T18:00:00Z","forecast_issue_time":"2026-06-30T12:00:00Z","source_receipt_time":"2026-06-30T12:05:00Z","mean_f":"100","stddev_f":"2","model_name":"m","model_version":"1","lead_hours":"18","city":"phx","temp_type":"high","outcome_local_date":"2026-07-01"};r.update(x);return r
def l(**x):
    r={"event_ticker":"KXHIGHTPHX-26JUL01","label_available_ts":"2026-07-02T08:00:00Z","observed_f":"101"};r.update(x);return r
class SkillTest(unittest.TestCase):
    def test_valid_lead_month_and_crps(self):
        good,bad=ev.build_rows([f()],[l()]);self.assertEqual(len(good),1);self.assertFalse(bad);self.assertEqual(ev.summarize(good,bad)[0]["lead_hours"],"18");self.assertEqual(ev.summarize(good,bad)[0]["target_month"],"2026-07");self.assertGreater(good[0]["crps_f"],0)
    def test_lead_and_month_are_distinct_groups(self):
        second=f(event_ticker="KXHIGHTLV-26AUG01",city="lv",lead_hours="24",outcome_local_date="2026-08-01")
        second_label=l(event_ticker="KXHIGHTLV-26AUG01",label_available_ts="2026-08-02T08:00:00Z")
        good,bad=ev.build_rows([f(),second],[l(),second_label]);self.assertFalse(bad)
        groups=ev.summarize(good,bad)
        self.assertEqual({(r["lead_hours"],r["target_month"]) for r in groups},{("18","2026-07"),("24","2026-08")})
    def test_active_auxiliary_cities_are_accepted(self):
        for city in ("nyc", "la", "los_angeles", "austin"):
            row=f(city=city,event_ticker=f"KXHIGHT{city.upper()}-26JUL01")
            lab=l(event_ticker=row["event_ticker"])
            good,bad=ev.build_rows([row],[lab])
            self.assertEqual(len(good),1); self.assertFalse(bad)
    def test_earliest_future_label(self):
        good,_=ev.build_rows([f()],[l(label_available_ts="2026-07-03T00:00:00Z",observed_f="103"),l()]);self.assertEqual(good[0]["observed_f"],101)
    def test_rejections(self):
        rows=[f(source_receipt_time="2026-07-01T00:00:00Z"),f(source_receipt_time=""),f(mean_f="bad"),f(stddev_f="bad"),f(event_ticker="X")]
        _,bad=ev.build_rows(rows,[l()]);self.assertIn("missing_timestamp",{x.reason for x in bad});self.assertIn("invalid_value",{x.reason for x in bad});self.assertIn("no_label_found",{x.reason for x in bad})
    def test_leakage_and_no_label(self):
        _,bad=ev.build_rows([f()],[l(label_available_ts="2026-06-30T17:00:00Z")]);self.assertEqual(bad[0].reason,"target_leakage");_,bad=ev.build_rows([f()],[]);self.assertEqual(bad[0].reason,"no_label_found")
    def test_output(self):
        with tempfile.TemporaryDirectory() as d:
            d=Path(d);fp,lp,op,rp=[d/x for x in ("f.csv","l.csv","o.csv","r.csv")]
            for path,row in ((fp,f()),(lp,l())):
                with path.open("w",newline="") as h:w=csv.DictWriter(h,fieldnames=list(row));w.writeheader();w.writerow(row)
            self.assertEqual(ev.evaluate(fp,lp,op,rp),(1,0,1));self.assertTrue(op.exists() and rp.exists())
if __name__=="__main__":unittest.main()

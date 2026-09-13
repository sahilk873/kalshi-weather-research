"""Summarize decoded ECMWF ensemble point temperatures."""
from __future__ import annotations
import argparse,csv,math,statistics
from pathlib import Path

FIELDS=["model","city","initialization_time_utc","valid_time_utc","lead_hours","variable","member_count","ensemble_mean_f","ensemble_spread_f","p10_f","p50_f","p90_f","prob_ge_80_f","prob_ge_90_f","raw_path","sha256"]
def summarize(path:Path,output:Path)->int:
 groups={}
 with path.open(newline="") as handle:
  for r in csv.DictReader(handle):
   key=tuple(r[k] for k in ("model","city","initialization_time_utc","valid_time_utc","lead_hours","variable")); groups.setdefault(key,[]).append(r)
 rows=[]
 for key,items in sorted(groups.items()):
  vals=sorted(float(x["value"]) for x in items); mean=statistics.fmean(vals); spread=statistics.pstdev(vals) if len(vals)>1 else 0.0
  q=lambda p: vals[min(len(vals)-1,max(0,math.ceil(p*len(vals))-1))]
  r=dict(zip(("model","city","initialization_time_utc","valid_time_utc","lead_hours","variable"),key)); r.update({"member_count":len(vals),"ensemble_mean_f":round(mean,6),"ensemble_spread_f":round(spread,6),"p10_f":q(.1),"p50_f":q(.5),"p90_f":q(.9),"prob_ge_80_f":round(sum(v>=80 for v in vals)/len(vals),6),"prob_ge_90_f":round(sum(v>=90 for v in vals)/len(vals),6),"raw_path":items[0]["raw_path"],"sha256":items[0]["sha256"]}); rows.append(r)
 output.parent.mkdir(parents=True,exist_ok=True)
 with output.open("w",newline="") as h: w=csv.DictWriter(h,fieldnames=FIELDS); w.writeheader(); w.writerows(rows)
 return len(rows)
def main()->None:
 p=argparse.ArgumentParser(description=__doc__); p.add_argument("--input",type=Path,required=True); p.add_argument("--output",type=Path,required=True); a=p.parse_args(); print(f"wrote {summarize(a.input,a.output)} summaries")
if __name__=="__main__": main()

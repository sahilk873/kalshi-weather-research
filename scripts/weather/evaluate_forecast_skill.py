"""Point-in-time forecast skill metrics; no model fitting or trading."""
from __future__ import annotations
import argparse, csv, math, sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path
_SELF=Path(__file__).resolve().parent; sys.path.insert(0,str(_SELF))
from common import parse_utc_iso
from pit import available_asof

CITY_ALIASES={"nyc":"nyc","new_york":"nyc","la":"la","los_angeles":"la","los angeles":"la","austin":"austin","phx":"phx","lv":"lv"}

FREQ={"event_ticker","decision_time_utc","forecast_issue_time","source_receipt_time","mean_f","model_name","model_version","lead_hours","city","temp_type","outcome_local_date"}
LFREQ={"event_ticker","label_available_ts","observed_f"}
SUMMARY=["model_name","model_version","city","temp_type","lead_hours","target_month","eligible_predictions","mae_f","crps_predictions","crps_f","rejected_missing_timestamp","rejected_target_leakage","rejected_no_label_found","rejected_invalid_value","rejected_invalid_label"]
REJECTIONS=["event_ticker","model_name","model_version","decision_time_utc","reason","detail"]

@dataclass(frozen=True)
class Rejection:
    event_ticker:str; model_name:str; model_version:str; decision_time_utc:str; reason:str; detail:str

def read_csv(path:Path)->list[dict]:
    with path.open(newline="") as fh:return list(csv.DictReader(fh))
def require(rows, fields, name):
    if not rows: raise ValueError(f"{name} input is empty")
    missing=fields-set(rows[0]);
    if missing: raise ValueError(f"{name} input missing required columns: {sorted(missing)}")
def crps(mean:float, observed:float, sigma:float)->float:
    if sigma<=0: raise ValueError("stddev_f must be positive")
    z=(observed-mean)/sigma; phi=math.exp(-z*z/2)/math.sqrt(2*math.pi); cdf=(1+math.erf(z/math.sqrt(2)))/2
    return sigma*(z*(2*cdf-1)+2*phi-1/math.sqrt(math.pi))
gaussian_crps=crps
def _num(row, key):
    value=str(row.get(key,"" )).strip()
    if not value: raise ValueError(f"missing {key}")
    try:return float(value)
    except ValueError as exc:raise ValueError(f"invalid {key}") from exc
def _reject(row, reason, detail):
    return Rejection(row.get("event_ticker",""),row.get("model_name",""),row.get("model_version",""),row.get("decision_time_utc",""),reason,detail)
def _label_index(labels):
    index=defaultdict(list); invalid=defaultdict(int)
    for label in labels:
        ts=parse_utc_iso(label.get("label_available_ts"))
        if ts is None: invalid[label.get("event_ticker","")]+=1
        else:index[label.get("event_ticker","")].append((ts,label))
    for values in index.values():values.sort(key=lambda x:x[0])
    return index,invalid
def build_rows(forecasts,labels):
    require(forecasts,FREQ,"forecast")
    if labels:
        require(labels,LFREQ,"label")
    index,invalid_labels=_label_index(labels)
    good=[]; bad=[]
    for row in forecasts:
        try:
            decision=parse_utc_iso(row.get("decision_time_utc"))
            if decision is None:raise ValueError("missing timestamp decision_time_utc")
            if not available_asof(row,decision,issue_fields=("forecast_issue_time",),receipt_fields=("source_receipt_time",)):raise ValueError("missing or late issue/receipt timestamp")
            city=CITY_ALIASES.get(row["city"].strip().lower(),""); typ=row["temp_type"].strip().lower()
            if not city or typ not in ("high","low"):raise ValueError("invalid city or temp_type")
            month=date.fromisoformat(row["outcome_local_date"]).strftime("%Y-%m")
            lead=float(row["lead_hours"]); mean=_num(row,"mean_f")
            if not math.isfinite(lead) or not math.isfinite(mean):raise ValueError("invalid numeric value")
            text=row.get("stddev_f","").strip(); sigma=None if not text else float(text)
            if sigma is not None and (not math.isfinite(sigma) or sigma<=0):raise ValueError("invalid stddev_f")
        except (KeyError,TypeError,ValueError) as exc:
            reason="missing_timestamp" if "timestamp" in str(exc) or "issue/receipt" in str(exc) else "invalid_value"; bad.append(_reject(row,reason,str(exc))); continue
        candidates=index.get(row.get("event_ticker",""),[]); future=[x for x in candidates if x[0]>decision]
        if not future:
            event = row.get("event_ticker", "")
            reason="target_leakage" if candidates else ("invalid_label" if invalid_labels.get(event, 0) else "no_label_found")
            bad.append(_reject(row,reason,"no label strictly after decision")); continue
        label=future[0][1]
        try:observed=_num(label,"observed_f")
        except ValueError as exc:bad.append(_reject(row,"invalid_label",str(exc)));continue
        good.append({"event_ticker": row.get("event_ticker", ""), "outcome_local_date": row["outcome_local_date"], "model_name":row["model_name"],"model_version":row["model_version"],"city":city,"temp_type":typ,"lead_hours":f"{lead:g}","target_month":month,"mean_f":mean,"observed_f":observed,"crps_f":crps(mean,observed,sigma) if sigma is not None else None})
    return good,bad
def summarize(good,bad):
    groups=defaultdict(list)
    for row in good:groups[tuple(row[k] for k in ("model_name","model_version","city","temp_type","lead_hours","target_month"))].append(row)
    out=[]
    for key,rows in sorted(groups.items()):
        reasons=[r.reason for r in bad if (r.model_name,r.model_version)==key[:2]]; scores=[r["crps_f"] for r in rows if r["crps_f"] is not None]
        out.append(dict(zip(SUMMARY,[*key,len(rows),sum(abs(r["mean_f"]-r["observed_f"]) for r in rows)/len(rows),len(scores),sum(scores)/len(scores) if scores else "",reasons.count("missing_timestamp"),reasons.count("target_leakage"),reasons.count("no_label_found"),reasons.count("invalid_value"),reasons.count("invalid_label")])))
    represented={(r.model_name,r.model_version) for r in bad}
    present={(r["model_name"],r["model_version"]) for r in good}
    for model_name,model_version in sorted(represented-present):
        reasons=[r.reason for r in bad if (r.model_name,r.model_version)==(model_name,model_version)]
        out.append(dict(zip(SUMMARY,[model_name,model_version,"","","","",0,"",0,"",reasons.count("missing_timestamp"),reasons.count("target_leakage"),reasons.count("no_label_found"),reasons.count("invalid_value"),reasons.count("invalid_label")])))
    return out
def evaluate(forecasts,labels,output,rejections=None):
    good,bad=build_rows(read_csv(forecasts),read_csv(labels)); summary=summarize(good,bad)
    with output.open("w",newline="") as fh: w=csv.DictWriter(fh,fieldnames=SUMMARY);w.writeheader();w.writerows(summary)
    if rejections:
        with rejections.open("w",newline="") as fh:w=csv.DictWriter(fh,fieldnames=REJECTIONS);w.writeheader();w.writerows(r.__dict__ for r in bad)
    return len(good),len(bad),len(summary)
def main():
    p=argparse.ArgumentParser();p.add_argument("--forecasts",type=Path,required=True);p.add_argument("--labels",type=Path,required=True);p.add_argument("--output",type=Path,required=True);p.add_argument("--rejections",type=Path);a=p.parse_args();print(evaluate(a.forecasts,a.labels,a.output,a.rejections))
if __name__=="__main__":main()

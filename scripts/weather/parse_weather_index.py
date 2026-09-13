"""Normalize archived Kalshi Weather Index JSON into timestamped rows."""
from __future__ import annotations
import argparse, csv, json
from datetime import datetime, timezone
from pathlib import Path

FIELDS=["city","timestamp_utc","value_f","contributors","status","config_version","source_receipt_time","raw_path","sha256"]

def parse(raw_path: Path, manifest_row: dict) -> list[dict[str,str]]:
    payload=json.loads(raw_path.read_text()); city=str(payload.get("city", manifest_row.get("city", "")))
    out=[]
    for item in payload.get("timeseries", []):
        try: stamp=datetime.fromtimestamp(int(item["t"])/1000, timezone.utc).isoformat().replace("+00:00","Z"); value=float(item["v"])
        except (KeyError, TypeError, ValueError, OverflowError): continue
        out.append({"city":city,"timestamp_utc":stamp,"value_f":f"{value:.3f}","contributors":str(item.get("contributors", "")),"status":str(item.get("status", "")),"config_version":str(payload.get("config_version", "")),"source_receipt_time":manifest_row.get("retrieved_at_utc", ""),"raw_path":manifest_row.get("raw_path", str(raw_path)),"sha256":manifest_row.get("sha256", "")})
    return out

def main() -> None:
    p=argparse.ArgumentParser(description=__doc__); p.add_argument("--input",type=Path,required=True); p.add_argument("--manifest",type=Path,required=True); p.add_argument("--output",type=Path,required=True); a=p.parse_args()
    manifest=json.loads(a.manifest.read_text()).get("rows", []); row=next((r for r in manifest if r.get("city")==json.loads(a.input.read_text()).get("city")), {})
    rows=parse(a.input,row); a.output.parent.mkdir(parents=True,exist_ok=True)
    with a.output.open("w",newline="") as f: w=csv.DictWriter(f,fieldnames=FIELDS); w.writeheader(); w.writerows(rows)
    print(f"wrote {a.output} ({len(rows)} rows)")
if __name__ == "__main__": main()

"""Collect a bounded ECMWF IFS open-data surface-temperature forecast."""
from __future__ import annotations
import argparse, hashlib, json
from datetime import datetime, timezone
from pathlib import Path


def collect(date: str, cycle: int, output: Path, reuse: bool = False, stream: str = "oper", forecast_type: str = "fc", numbers: list[int] | None = None) -> dict:
    try:
        from ecmwf.opendata import Client
    except ImportError as exc:
        raise RuntimeError("install ecmwf-opendata in the runtime environment") from exc
    output.parent.mkdir(parents=True, exist_ok=True)
    if not reuse or not output.exists():
        kwargs = {"type": forecast_type, "stream": stream, "levtype": "sfc", "param": ["2t"], "date": date, "time": cycle, "step": [0, 3, 6, 9, 12], "target": str(output)}
        if numbers: kwargs["number"] = numbers
        Client(source="ecmwf").retrieve(**kwargs)
    data = output.read_bytes()
    return {"model":"IFS", "date":date, "cycle_utc":cycle, "parameter":"2t",
            "steps_hours":[0,3,6,9,12], "stream": stream, "type": forecast_type, "numbers": numbers or [], "source_url":"https://data.ecmwf.int/forecasts/",
            "retrieved_at_utc":datetime.now(timezone.utc).isoformat().replace("+00:00","Z"),
            "raw_path":str(output), "bytes":len(data), "sha256":hashlib.sha256(data).hexdigest(),
            "decoded":False}


def main() -> None:
    p=argparse.ArgumentParser(description=__doc__); p.add_argument("--date",required=True); p.add_argument("--cycle",type=int,choices=(0,6,12,18),required=True); p.add_argument("--output",type=Path,required=True); p.add_argument("--manifest",type=Path,required=True); p.add_argument("--reuse",action="store_true"); p.add_argument("--stream",default="oper"); p.add_argument("--type",default="fc"); p.add_argument("--numbers",nargs="*",type=int); a=p.parse_args()
    row=collect(a.date,a.cycle,a.output,a.reuse,a.stream,a.type,a.numbers); a.manifest.parent.mkdir(parents=True,exist_ok=True); a.manifest.write_text(json.dumps({"rows":[row]},indent=2,sort_keys=True)+"\n"); print(a.manifest)


if __name__ == "__main__": main()

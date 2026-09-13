"""Credential-aware ERA5 point request; never fabricates reanalysis data."""
from __future__ import annotations
import argparse, json, os
from datetime import datetime, timezone
from pathlib import Path


def request_spec(date: str, variables: list[str], area: list[float]) -> dict:
    return {"dataset": "reanalysis-era5-single-levels", "product_type": "reanalysis", "variable": variables, "year": date[:4], "month": date[5:7], "day": date[8:10], "time": [f"{hour:02d}:00" for hour in range(24)], "area": area, "format": "netcdf"}


def collect(date: str, variables: list[str], area: list[float], output: Path) -> dict:
    if not os.environ.get("CDS_API_KEY"):
        raise RuntimeError("ERA5 requires CDS_API_KEY credentials; no data was downloaded")
    try:
        import cdsapi
    except ImportError as exc:
        raise RuntimeError("install cdsapi in the runtime environment") from exc
    output.parent.mkdir(parents=True, exist_ok=True)
    spec=request_spec(date,variables,area); cdsapi.Client().retrieve(spec["dataset"],spec,str(output))
    return {"request":spec,"retrieved_at_utc":datetime.now(timezone.utc).isoformat().replace("+00:00","Z"),"raw_path":str(output),"credentials_source":"CDS_API_KEY environment variable"}


def main() -> None:
    p=argparse.ArgumentParser(description=__doc__); p.add_argument("--date",required=True); p.add_argument("--variables",nargs="+",default=["2m_temperature"]); p.add_argument("--area",nargs=4,type=float,default=[42,-118,29,-70],metavar=("N","W","S","E")); p.add_argument("--output",type=Path,required=True); p.add_argument("--manifest",type=Path,required=True); a=p.parse_args(); row=collect(a.date,a.variables,a.area,a.output); a.manifest.parent.mkdir(parents=True,exist_ok=True); a.manifest.write_text(json.dumps({"rows":[row]},indent=2,sort_keys=True)+"\n")


if __name__ == "__main__": main()

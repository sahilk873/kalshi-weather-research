"""Materialize model-run provenance from source manifests."""
from __future__ import annotations
import argparse, csv, hashlib, json
from pathlib import Path

FIELDS = ["model_run_id", "provider", "model", "model_version", "init_ts", "published_ts", "published_ts_method", "ingested_ts", "grid_resolution_km", "raw_manifest_uri"]

def build(root: Path) -> list[dict]:
    records = {}
    def add(provider, model, init, ingested, raw, uri, version=""):
        key = "|".join((provider, model, init, raw))
        rid = hashlib.sha256(key.encode()).hexdigest()[:32]
        records[rid] = {"model_run_id": rid, "provider": provider, "model": model, "model_version": version, "init_ts": init, "published_ts": "", "published_ts_method": "unobserved", "ingested_ts": ingested, "grid_resolution_km": "", "raw_manifest_uri": uri or raw}
    path = root / "forecasts" / "manifest.csv"
    if path.exists():
        with path.open(newline="") as handle:
            for r in csv.DictReader(handle):
                add("NOAA/NOMADS", r.get("model", ""), r.get("initialization_time_utc", ""), r.get("ingested_at_utc", ""), r.get("raw_path", ""), r.get("request_url", ""))
    for folder, provider in (("gefs", "Open-Meteo"), ("gefs/historical_raw", "Open-Meteo")):
        manifest = root / folder / "manifest.csv"
        if manifest.exists():
            with manifest.open(newline="") as handle:
                for r in csv.DictReader(handle):
                    add(provider, r.get("model", ""), r.get("initialization_time_utc", ""), r.get("retrieved_at", ""), r.get("raw_path", ""), r.get("request_url", ""))
    manifest = root / "glmp" / "manifest.json"
    if manifest.exists():
        payload = json.loads(manifest.read_text())
        for r in payload.get("snapshots", []): add("NOAA/NOMADS", r.get("model", "GLMP"), r.get("initialization_time_utc", ""), r.get("retrieved_at_utc", ""), r.get("raw_path", ""), r.get("source_url", ""))
    return [records[k] for k in sorted(records)]

def main() -> None:
    p = argparse.ArgumentParser(description=__doc__); p.add_argument("--root", type=Path, default=Path("data/weather_research")); p.add_argument("--output", type=Path, default=Path("data/weather_research/reports/model_runs.csv")); a=p.parse_args(); rows=build(a.root); a.output.parent.mkdir(parents=True,exist_ok=True)
    with a.output.open("w",newline="") as h: w=csv.DictWriter(h,fieldnames=FIELDS); w.writeheader(); w.writerows(rows)
    print(f"wrote {len(rows)} model runs")
if __name__ == "__main__": main()

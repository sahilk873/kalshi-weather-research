"""Versioned report-2 live-job cadence manifest and validator."""
from __future__ import annotations
import argparse, json
from pathlib import Path

JOBS = (
    ("kalshi_active_contracts", 60, "market"), ("intraday_market_capture", 60, "market"),
    ("kalshi_orderbook_ws", 0, "continuous"),
    ("kalshi_trades_ws", 0, "continuous"), ("awc_metar", 60, "weather"),
    ("nearby_metar", 60, "weather"), ("open_meteo_freshness", 300, "model"),
    ("hrrr_run_detector", 180, "model"), ("nbm_run_detector", 300, "model"),
    ("lamp_run_detector", 300, "model"), ("gefs_run_detector", 600, "model"),
    ("feature_regeneration", 60, "pipeline"), ("probability_inference", 60, "pipeline"),
    ("risk_recomputation", 60, "risk"), ("twc_settlement_archive", 3600, "settlement"),
    ("daily_data_qc", 86400, "quality"), ("fast_recalibration", 86400, "quality"),
    ("challenger_retrain", 604800, "research"), ("hyperparameter_review", 2592000, "research"),
)

def schedule() -> dict:
    return {"version": "report2-v1", "jobs": [{"job": n, "cadence_seconds": c, "class": k, "continuous": c == 0} for n, c, k in JOBS]}

def validate(value: dict) -> list[str]:
    errors = []
    if not isinstance(value, dict) or not isinstance(value.get("jobs"), list): return ["jobs must be a list"]
    names = []
    for row in value["jobs"]:
        if not isinstance(row, dict): errors.append("job must be an object"); continue
        name = str(row.get("job", "")); names.append(name)
        try: cadence = int(row.get("cadence_seconds"))
        except (TypeError, ValueError): errors.append(f"{name}: cadence is not integer"); continue
        if cadence < 0: errors.append(f"{name}: cadence must be non-negative")
        if bool(row.get("continuous")) != (cadence == 0): errors.append(f"{name}: continuous flag mismatch")
    if len(names) != len(set(names)): errors.append("duplicate job names")
    return errors

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument("--output", type=Path); args = parser.parse_args()
    result = schedule(); errors = validate(result)
    if errors: raise SystemExit("invalid schedule: " + "; ".join(errors))
    text = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output: args.output.parent.mkdir(parents=True, exist_ok=True); args.output.write_text(text)
    else: print(text, end="")

if __name__ == "__main__": main()

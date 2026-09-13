"""Audit the report-2 M0–M13 model ladder before any training run.

This tool is deliberately an eligibility manifest, not a performance claim.
Each candidate records input presence separately from trained/OOS evidence;
input rows alone never constitute a completed experiment or promotion.
"""
from __future__ import annotations

import argparse, csv, json
from pathlib import Path

MODELS = (
    ("M0", "climatology", "labels"),
    ("M1", "persistence", "observations"),
    ("M2", "raw_hrrr", "hrrr"),
    ("M3", "raw_nbm", "nbm"),
    ("M4", "raw_lamp", "lamp"),
    ("M5", "raw_gefs_member_frequency", "gefs"),
    ("M6", "linear_dynamic_bias", "decision_features"),
    ("M7", "gaussian_emos", "decision_features"),
    ("M8", "lightgbm_residual_mean", "decision_features"),
    ("M9", "lightgbm_quantiles", "decision_features"),
    ("M10", "catboost_multi_quantile", "decision_features"),
    ("M11", "stacked_m7_m9_physical", "decision_features"),
    ("M12", "optional_tcn_lstm", "decision_features"),
    ("M13", "optional_transformer_mdn_deep_ensemble", "decision_features"),
)


def _count(path: Path) -> int:
    if not path.exists(): return 0
    with path.open(newline="") as handle: return sum(1 for _ in csv.DictReader(handle))


def _count_model(path: Path, names: set[str]) -> int:
    if not path.exists(): return 0
    with path.open(newline="") as handle:
            return sum(1 for row in csv.DictReader(handle) if row.get("model", "").lower() in names)


def _count_lamp_temperature(root: Path) -> int:
    path = root / "lamp" / "station_forecasts.csv"
    if not path.exists():
        return 0
    with path.open(newline="") as handle:
        return sum(1 for row in csv.DictReader(handle) if row.get("field", "").upper() in {"TMP", "DPT"})


def _count_parquet(path: Path) -> int:
    try:
        import pyarrow.parquet as pq
        return pq.read_metadata(path).num_rows if path.exists() else 0
    except (ImportError, OSError):
        return 0


def audit(root: Path) -> dict:
    counts = {
        "labels": _count(root / "ghcn_city" / "labels_daily.csv"),
        "observations": _count(root / "city_asos" / "asos_parsed_canonical.csv"),
        "hrrr": _count_model(root / "forecasts" / "model_forecasts_points.csv", {"hrrr"}),
        "nbm": _count_model(root / "forecasts" / "model_forecasts_points.csv", {"nbm"}),
        "lamp": _count_lamp_temperature(root) + _count(root / "glmp" / "point_features.csv"),
        "gefs": _count_parquet(root / "gefs" / "gefs_features.parquet"),
        "decision_features": _count(root / "reports" / "decision_features.csv"),
    }
    rows = []
    for model_id, name, requirement in MODELS:
        available = counts[requirement] > 0
        deferred = model_id in {"M12", "M13"}
        rows.append({
            "model_id": model_id, "name": name, "required_artifact": requirement,
            "input_rows": counts[requirement],
            "status": "deferred_optional" if deferred else ("eligible_for_run" if available else "data_missing"),
            "input_presence_only": available,
            "trained": False,
            "oos_evidence": False,
            "promotion_eligible": False,
            "reason": ("optional challenger deferred until M11 improves and PIT/OOS evidence exists"
                       if deferred else ("input artifact has rows; training and OOS evidence are absent"
                                         if available else f"no rows available for {requirement}")),
        })
    return {"version": "report2-model-ladder-v2", "models": rows,
            "complete": False, "completion_reason": "no trained rolling OOS evidence is recorded",
            "counts": counts}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument("--root", type=Path, default=Path("data/weather_research")); parser.add_argument("--output", type=Path, default=Path("data/weather_research/reports/model_ladder.json")); args=parser.parse_args(); result=audit(args.root); args.output.parent.mkdir(parents=True,exist_ok=True); args.output.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n"); print(json.dumps({"complete":result["complete"],"models":len(result["models"])},sort_keys=True))
if __name__ == "__main__": main()

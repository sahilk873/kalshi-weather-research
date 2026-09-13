"""Deterministic robustness scenarios for point-in-time predictions.

This module transforms an already aligned prediction/evaluation table. It does
not invent outcomes: rows missing a valid prediction/outcome or required
timestamps are excluded and counted as rejections. Scenarios model feed delay,
observation outage, late model arrival, calibration shocks, threshold
proximity, and market stress columns when present.
"""
from __future__ import annotations

import argparse, csv, json, math
from datetime import datetime, timedelta, timezone
from pathlib import Path

def _time(value: object) -> datetime | None:
    try:
        result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return result.replace(tzinfo=timezone.utc) if result.tzinfo is None else result
    except (TypeError, ValueError): return None

def _prob(row: dict) -> float | None:
    try:
        value = float(row.get("prediction", row.get("probability", row.get("bucket_probability", "nan"))))
        return value if math.isfinite(value) and 0 <= value <= 1 else None
    except (TypeError, ValueError): return None

def _outcome(row: dict) -> int | None:
    value = str(row.get("outcome", row.get("settled_yes", ""))).lower()
    return 1 if value in {"1", "true", "yes"} else 0 if value in {"0", "false", "no"} else None

def _metrics(rows: list[dict], bias: float = 0.0, filtered_out: int = 0) -> dict:
    scored = []; rejected = 0
    for row in rows:
        p, y = _prob(row), _outcome(row)
        if p is None or y is None: rejected += 1; continue
        p = min(1 - 1e-12, max(1e-12, p + bias)); scored.append((p, y))
    return {"rows": len(rows), "filtered_out": filtered_out, "scored": len(scored), "rejected": rejected,
            "brier": sum((p-y) ** 2 for p, y in scored) / len(scored) if scored else None,
            "log_loss": sum(-(y * math.log(p) + (1-y) * math.log(1-p)) for p, y in scored) / len(scored) if scored else None}

def run(rows: list[dict], delays: tuple[int, ...] = (2, 5, 10, 20), outages: tuple[int, ...] = (5, 15, 30, 60), biases: tuple[float, ...] = (-.05, -.03, -.02, -.01, .01, .02, .03, .05)) -> dict:
    scenarios = {"baseline": _metrics(rows)}
    for minutes in delays:
        kept = []
        for row in rows:
            decision = _time(row.get("decision_time_utc", row.get("decision_time"))); receipt = _time(row.get("source_receipt_time", row.get("receipt_time_utc")))
            if decision is not None and receipt is not None and receipt + timedelta(minutes=minutes) <= decision: kept.append(row)
        scenarios[f"feed_delay_{minutes}m"] = _metrics(kept, filtered_out=len(rows)-len(kept))
        kept = []
        for row in rows:
            decision = _time(row.get("decision_time_utc", row.get("decision_time"))); receipt = _time(row.get("nwp_receipt_time", row.get("model_receipt_time")))
            if decision is not None and receipt is not None and receipt + timedelta(minutes=minutes) <= decision: kept.append(row)
        scenarios[f"nwp_late_{minutes}m"] = _metrics(kept, filtered_out=len(rows)-len(kept))
    for minutes in outages:
        kept = []
        for row in rows:
            try: age = float(row.get("observation_age_minutes", "nan"))
            except (TypeError, ValueError): age = float("nan")
            if math.isfinite(age) and age >= minutes: kept.append(row)
        scenarios[f"observation_outage_{minutes}m"] = _metrics(kept, filtered_out=len(rows)-len(kept))
    for bias in biases: scenarios[f"calibration_bias_{bias:+.2f}"] = _metrics(rows, bias)
    for label, predicate in (("threshold_within_0.25f", .25), ("threshold_within_0.5f", .5), ("threshold_within_1f", 1.0), ("threshold_within_2f", 2.0)):
        kept = []
        for row in rows:
            try: distance = abs(float(row.get("threshold_distance_f", "nan")))
            except (TypeError, ValueError): distance = float("nan")
            if math.isfinite(distance) and distance <= predicate: kept.append(row)
        scenarios[label] = _metrics(kept, filtered_out=len(rows)-len(kept))
    # Market-stress subsets are only evaluated when the source table provides
    # the relevant observed fields; missing fields fail closed to zero rows.
    for label, predicate in (("wide_spread", lambda r: float(r.get("spread", "nan")) >= .05), ("low_volume", lambda r: float(r.get("volume", "nan")) <= 10), ("quote_jump", lambda r: abs(float(r.get("quote_jump", "nan"))) >= .10)):
        kept = []
        for row in rows:
            try:
                if predicate(row): kept.append(row)
            except (TypeError, ValueError): pass
        scenarios[label] = _metrics(kept, filtered_out=len(rows)-len(kept))
    return scenarios

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument("--input", type=Path, required=True); parser.add_argument("--output", type=Path, required=True); args = parser.parse_args()
    with args.input.open(newline="") as handle: rows = list(csv.DictReader(handle))
    args.output.parent.mkdir(parents=True, exist_ok=True); args.output.write_text(json.dumps({"input_rows": len(rows), "scenarios": run(rows)}, indent=2, sort_keys=True) + "\n"); print(args.output)

if __name__ == "__main__": main()

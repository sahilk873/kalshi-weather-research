"""Fail-closed edge-first evaluation boundary for admitted NYC PIT rows."""
from __future__ import annotations

import argparse
import csv
import json
import math
from collections import defaultdict
from pathlib import Path
from datetime import datetime, timezone


def _parse(value: object) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return (parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def _metric_rows(rows: list[dict]) -> dict:
    """Compute guarded binary and executable metrics for already-admitted rows."""
    values = []
    for row in rows:
        probability = float(row["predicted_probability"])
        outcome = 1.0 if row["kalshi_result"] == "yes" else 0.0
        brier = (probability - outcome) ** 2
        log_loss = -math.log(max(probability if outcome else 1.0 - probability, 1e-15))
        values.append((row, probability, outcome, brier, log_loss))
    mean_probability = sum(item[1] for item in values) / len(values)
    observed_rate = sum(item[2] for item in values) / len(values)
    metrics = {
        "rows": len(values),
        "brier_score": sum(item[3] for item in values) / len(values),
        "crps_binary": sum(item[3] for item in values) / len(values),
        "log_loss": sum(item[4] for item in values) / len(values),
        "mean_predicted_probability": mean_probability,
        "observed_rate": observed_rate,
        "calibration_abs_error": abs(mean_probability - observed_rate),
    }
    reliability = []
    for bucket in range(10):
        selected = [item for item in values if (item[1] >= bucket / 10.0 and (item[1] < (bucket + 1) / 10.0 or bucket == 9))]
        if not selected:
            continue
        predicted = sum(item[1] for item in selected) / len(selected)
        observed = sum(item[2] for item in selected) / len(selected)
        reliability.append({"bin": bucket, "rows": len(selected), "mean_predicted_probability": predicted, "observed_rate": observed, "absolute_error": abs(predicted - observed)})
    metrics["reliability_bins"] = reliability
    metrics["max_bin_calibration_error"] = max((row["absolute_error"] for row in reliability), default=0.0)
    executable = []
    for row, probability, outcome, *_ in values:
        ask = float(row["yes_ask"])
        fee = float(row.get("fee", 0.0) or 0.0)
        slippage = float(row.get("slippage", 0.0) or 0.0)
        threshold = fee + slippage
        if probability > ask + threshold:
            executable.append(outcome - ask - fee - slippage)
    metrics["signals"] = len(executable)
    metrics["realized_edge"] = (sum(executable) / len(executable)) if executable else None
    metrics["net_pnl"] = sum(executable)
    return metrics


def evaluate(dataset: Path) -> dict:
    with dataset.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        return {"version": "edge-first-evaluation-v1", "rows": 0, "status": "not_evaluable", "metrics": None, "reason": "empty_admitted_pit_dataset", "pass": False}
    required = {"market_ticker", "target_time_utc", "decision_ts", "kalshi_result", "features_json"}
    missing = sorted(required - set(rows[0]))
    if missing:
        return {"version": "edge-first-evaluation-v1", "rows": len(rows), "status": "not_evaluable", "metrics": None, "reason": "dataset_schema_missing:" + ",".join(missing), "pass": False}
    quote_clock = next((field for field in ("quote_available_ts", "quote_receipt_ts", "quote_asof_ts") if field in rows[0]), None)
    if quote_clock is None:
        return {"version": "edge-first-evaluation-v1", "rows": len(rows), "status": "not_evaluable", "metrics": None, "reason": "missing_executable_quote_availability_clock", "pass": False}
    for index, row in enumerate(rows):
        decision = _parse(row.get("decision_ts")); target = _parse(row.get("target_time_utc")); quote = _parse(row.get(quote_clock))
        if decision is None or target is None or quote is None:
            return {"version": "edge-first-evaluation-v1", "rows": len(rows), "status": "not_evaluable", "metrics": None, "reason": f"invalid_pit_or_quote_clock:row_{index}", "pass": False}
        if target <= decision or quote > decision:
            return {"version": "edge-first-evaluation-v1", "rows": len(rows), "status": "not_evaluable", "metrics": None, "reason": f"late_or_invalid_quote_clock:row_{index}", "pass": False}
    required_prediction = {"predicted_probability", "oos_fold", "model_fit_end_ts"}
    missing_prediction = sorted(required_prediction - set(rows[0]))
    if missing_prediction:
        return {"version": "edge-first-evaluation-v2", "rows": len(rows), "status": "not_evaluable", "metrics": None, "reason": "missing_oos_prediction_fields:" + ",".join(missing_prediction), "pass": False}
    for index, row in enumerate(rows):
        try:
            probability = float(row["predicted_probability"])
            if not math.isfinite(probability) or not 0 <= probability <= 1:
                raise ValueError("probability outside [0,1]")
            if row.get("kalshi_result") not in {"yes", "no"}:
                raise ValueError("invalid binary label")
            fit_end = _parse(row.get("model_fit_end_ts")); decision = _parse(row.get("decision_ts"))
            if fit_end is None or decision is None or fit_end > decision:
                raise ValueError("model fit was not complete by decision")
        except (TypeError, ValueError, OverflowError) as exc:
            return {"version": "edge-first-evaluation-v2", "rows": len(rows), "status": "not_evaluable", "metrics": None, "reason": f"invalid_oos_prediction:row_{index}:{exc}", "pass": False}
    folds = defaultdict(list)
    for row in rows:
        folds[str(row["oos_fold"])].append(row)
    fold_metrics = {fold: _metric_rows(fold_rows) for fold, fold_rows in sorted(folds.items())}
    metrics = _metric_rows(rows)
    return {"version": "edge-first-evaluation-v2", "rows": len(rows), "status": "evaluated", "metrics": metrics, "fold_metrics": fold_metrics, "reason": "explicit OOS folds and fit clocks validated", "pass": bool(fold_metrics)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=Path("data/weather_research/reports/nyc_edge_first_dataset.csv"))
    parser.add_argument("--output", type=Path, default=Path("data/weather_research/reports/edge_first_evaluation.json"))
    args = parser.parse_args()
    result = evaluate(args.dataset)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"rows": result["rows"], "status": result["status"], "pass": result["pass"]}))


if __name__ == "__main__":
    main()

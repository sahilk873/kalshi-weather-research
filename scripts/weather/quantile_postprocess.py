"""Fit a transparent PIT-safe empirical residual quantile postprocessor."""
from __future__ import annotations

import argparse
import csv
import math
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

_SELF = Path(__file__).resolve().parent
sys.path.insert(0, str(_SELF))
from common import parse_utc_iso  # noqa: E402

MIN_TRAINING = 5
Z90 = 1.2815515655446004


def _lead_bucket(value: object) -> str:
    return str(int(round(float(value) / 6.0) * 6))


def _key(row: dict, fields: tuple[str, ...]) -> tuple[str, ...]:
    values = {"city": row.get("city", ""), "model_name": row.get("model_name", ""), "temp_type": row.get("temp_type", ""), "lead_bucket": _lead_bucket(row.get("lead_hours", "")), "month": date.fromisoformat(row["outcome_local_date"]).strftime("%m")}
    return tuple(values[field] for field in fields)


def _quantile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    if not ordered: raise ValueError("quantile of empty values")
    position = (len(ordered) - 1) * probability
    lower, upper = math.floor(position), math.ceil(position)
    if lower == upper: return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def fit_quantiles(forecasts: list[dict], labels: list[dict], min_training: int = MIN_TRAINING, as_of=None) -> dict[tuple[str, ...], tuple[float, float, float, int]]:
    label_index = {}
    for label in labels:
        available = parse_utc_iso(label.get("label_available_ts"))
        try: observed = float(label.get("observed_f", ""))
        except (TypeError, ValueError): continue
        if available is not None and math.isfinite(observed) and label.get("event_ticker"):
            label_index[label["event_ticker"]] = (available, observed)
    groups: dict[tuple[str, ...], list[float]] = defaultdict(list)
    for row in forecasts:
        label = label_index.get(row.get("event_ticker", "")); decision = parse_utc_iso(row.get("decision_time_utc"))
        try: target, mean = date.fromisoformat(row["outcome_local_date"]), float(row["mean_f"])
        except (KeyError, TypeError, ValueError): continue
        # The target may be tomorrow (or later); label availability, not the
        # calendar comparison, is the point-in-time leakage gate.
        gate = as_of or decision
        if label is None or decision is None or label[0] > gate or (as_of is not None and target >= gate.date()) or not math.isfinite(mean): continue
        residual = label[1] - mean
        for fields in (("city", "model_name", "temp_type", "lead_bucket", "month"), ("city", "model_name", "temp_type", "lead_bucket"), ("city", "model_name", "temp_type"), ("city", "temp_type")):
            groups[_key(row, fields)].append(residual)
    result = {}
    for key, values in groups.items():
        if len(values) >= min_training: result[key] = (_quantile(values, .1), _quantile(values, .5), _quantile(values, .9), len(values))
    return result


def apply_quantiles(forecasts: list[dict], fitted: dict[tuple[str, ...], tuple[float, float, float, int]]) -> list[dict]:
    fields = (("city", "model_name", "temp_type", "lead_bucket", "month"), ("city", "model_name", "temp_type", "lead_bucket"), ("city", "model_name", "temp_type"), ("city", "temp_type"))
    output = []
    for row in forecasts:
        selected = None
        for group_fields in fields:
            selected = fitted.get(_key(row, group_fields))
            if selected: break
        q10, q50, q90, count = selected or (0.0, 0.0, 0.0, 0)
        result = dict(row)
        try:
            mean = float(row["mean_f"])
            result["p10_f"] = f"{mean + q10:.6f}"; result["p50_f"] = f"{mean + q50:.6f}"; result["p90_f"] = f"{mean + q90:.6f}"
            result["mean_f"] = result["p50_f"]; result["stddev_f"] = f"{max((q90 - q10) / (2 * Z90), 0.01):.6f}"
        except (KeyError, TypeError, ValueError): pass
        result["quantile_training_rows"] = str(count); result["model_version"] = f"{row.get('model_version', '')}+quantile_v1"
        output.append(result)
    return output


def render(training_forecasts: Path, training_labels: Path, forecasts: Path, output: Path) -> int:
    with training_forecasts.open(newline="") as fh: training = list(csv.DictReader(fh))
    with training_labels.open(newline="") as fh: labels = list(csv.DictReader(fh))
    with forecasts.open(newline="") as fh: current = list(csv.DictReader(fh))
    rows = apply_quantiles(current, fit_quantiles(training, labels))
    output.parent.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0]) if rows else list(current[0]) if current else []
    with output.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields); writer.writeheader(); writer.writerows(rows)
    return len(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--training-forecasts", type=Path, required=True); parser.add_argument("--training-labels", type=Path, required=True); parser.add_argument("--forecasts", type=Path, required=True); parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(); print(f"wrote {render(args.training_forecasts, args.training_labels, args.forecasts, args.output)} quantile rows")


if __name__ == "__main__": main()

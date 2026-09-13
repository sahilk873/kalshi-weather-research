"""Apply a leakage-safe station/model bias correction to forecast means.

This is a small, transparent P1 postprocessor rather than a fitted black-box
model.  Residuals are learned only from earlier target dates whose labels were
available by the forecast decision time.  The correction is grouped by city,
model, high/low type, lead bucket, and target month, with progressively wider
fallback groups when a narrow group has too little history.
"""
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


def _lead_bucket(value: object) -> str:
    lead = float(value)
    return str(int(round(lead / 6.0) * 6))


def _label_index(labels: list[dict]) -> dict[str, tuple[object, float]]:
    result = {}
    for row in labels:
        available = parse_utc_iso(row.get("label_available_ts"))
        try:
            observed = float(row.get("observed_f", ""))
        except (TypeError, ValueError):
            continue
        if available is not None and math.isfinite(observed) and row.get("event_ticker"):
            result[row["event_ticker"]] = (available, observed)
    return result


def _key(row: dict, include: tuple[str, ...]) -> tuple[str, ...]:
    month = date.fromisoformat(row["outcome_local_date"]).strftime("%m")
    values = {"city": row.get("city", ""), "model_name": row.get("model_name", ""),
              "temp_type": row.get("temp_type", ""), "lead_bucket": _lead_bucket(row.get("lead_hours", "")),
              "month": month}
    return tuple(values[name] for name in include)


def fit_bias(forecasts: list[dict], labels: list[dict], min_training: int = MIN_TRAINING, as_of=None) -> dict[tuple[str, ...], tuple[float, int]]:
    """Fit residual means from rows available without target leakage."""
    index = _label_index(labels)
    groups: dict[tuple[str, ...], list[float]] = defaultdict(list)
    for row in forecasts:
        label = index.get(row.get("event_ticker", ""))
        decision = parse_utc_iso(row.get("decision_time_utc"))
        try:
            target = date.fromisoformat(row["outcome_local_date"])
            mean = float(row["mean_f"])
        except (KeyError, TypeError, ValueError):
            continue
        if label is None or decision is None or not math.isfinite(mean):
            continue
        # A day-ahead target is normally later than the decision date. The
        # observed availability timestamp above is the authoritative leakage
        # gate; do not reject valid future-target forecasts here.
        gate = as_of or decision
        if label[0] > gate or (as_of is not None and target >= gate.date()):
            continue
        residual = label[1] - mean
        for fields in (
            ("city", "model_name", "temp_type", "lead_bucket", "month"),
            ("city", "model_name", "temp_type", "lead_bucket"),
            ("city", "model_name", "temp_type"),
            ("city", "temp_type"),
        ):
            groups[_key(row, fields)].append(residual)
    return {key: (sum(values) / len(values), len(values)) for key, values in groups.items() if len(values) >= min_training}


def apply_bias(forecasts: list[dict], fitted: dict[tuple[str, ...], tuple[float, int]]) -> list[dict]:
    output = []
    for row in forecasts:
        candidates = [
            ("city", "model_name", "temp_type", "lead_bucket", "month"),
            ("city", "model_name", "temp_type", "lead_bucket"),
            ("city", "model_name", "temp_type"),
            ("city", "temp_type"),
        ]
        correction, count = 0.0, 0
        for fields in candidates:
            match = fitted.get(_key(row, fields))
            if match:
                correction, count = match
                break
        result = dict(row)
        try:
            result["mean_f"] = f"{float(row['mean_f']) + correction:.6f}"
        except (KeyError, TypeError, ValueError):
            pass
        result["bias_f"] = f"{correction:.6f}"
        result["bias_training_rows"] = str(count)
        result["model_version"] = f"{row.get('model_version', '')}+station_bias_v1"
        output.append(result)
    return output


def render(training_forecasts: Path, training_labels: Path, forecasts: Path, output: Path) -> int:
    with training_forecasts.open(newline="") as fh: train = list(csv.DictReader(fh))
    with training_labels.open(newline="") as fh: labels = list(csv.DictReader(fh))
    with forecasts.open(newline="") as fh: current = list(csv.DictReader(fh))
    rows = apply_bias(current, fit_bias(train, labels))
    output.parent.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0]) if rows else list(current[0]) + ["bias_f", "bias_training_rows", "model_version"] if current else ["bias_f", "bias_training_rows", "model_version"]
    with output.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields); writer.writeheader(); writer.writerows(rows)
    return len(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--training-forecasts", type=Path, required=True)
    parser.add_argument("--training-labels", type=Path, required=True)
    parser.add_argument("--forecasts", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(f"wrote {render(args.training_forecasts, args.training_labels, args.forecasts, args.output)} bias-corrected rows")


if __name__ == "__main__":
    main()

"""Fit and apply a small leakage-safe Gaussian EMOS-style postprocessor.

This implementation deliberately stays transparent: it fits an affine mean
correction and a residual spread scale by city/model/type/lead/month, then
falls back to progressively broader groups. It is a research component only;
it does not place orders or claim skill without overlapping point-in-time
forecast/label folds.
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
MIN_STDDEV = 0.01


def _lead_bucket(value: object) -> str:
    return str(int(round(float(value) / 6.0) * 6))


def _key(row: dict, fields: tuple[str, ...]) -> tuple[str, ...]:
    values = {
        "city": row.get("city", ""), "model_name": row.get("model_name", ""),
        "temp_type": row.get("temp_type", ""), "lead_bucket": _lead_bucket(row.get("lead_hours", "")),
        "month": date.fromisoformat(row["outcome_local_date"]).strftime("%m"),
    }
    return tuple(values[field] for field in fields)


def _fit(values: list[tuple[float, float, float]], min_training: int) -> tuple[float, float, float, int] | None:
    if len(values) < min_training:
        return None
    xs = [x for x, _, _ in values]; ys = [y for _, y, _ in values]
    xbar, ybar = sum(xs) / len(xs), sum(ys) / len(ys)
    denom = sum((x - xbar) ** 2 for x in xs)
    slope = sum((x - xbar) * (y - ybar) for x, y in zip(xs, ys)) / denom if denom > 1e-12 else 0.0
    intercept = ybar - slope * xbar
    residuals = [y - (intercept + slope * x) for x, y in zip(xs, ys)]
    residual_std = math.sqrt(sum(r * r for r in residuals) / len(residuals))
    input_sigmas = [s for _, _, s in values if math.isfinite(s) and s > 0]
    scale = residual_std / (sum(input_sigmas) / len(input_sigmas)) if input_sigmas and sum(input_sigmas) > 0 else 1.0
    return intercept, slope, max(scale, MIN_STDDEV), len(values)


def fit_emos(forecasts: list[dict], labels: list[dict], min_training: int = MIN_TRAINING, as_of=None) -> dict[tuple[str, ...], tuple[float, float, float, int]]:
    index = {}
    for label in labels:
        available = parse_utc_iso(label.get("label_available_ts"))
        try: observed = float(label.get("observed_f", ""))
        except (TypeError, ValueError): continue
        if available is not None and math.isfinite(observed) and label.get("event_ticker"):
            index[label["event_ticker"]] = (available, observed)
    groups: dict[tuple[str, ...], list[tuple[float, float, float]]] = defaultdict(list)
    for row in forecasts:
        label = index.get(row.get("event_ticker", "")); decision = parse_utc_iso(row.get("decision_time_utc"))
        try:
            target = date.fromisoformat(row["outcome_local_date"]); mean = float(row["mean_f"]); sigma = float(row.get("stddev_f", ""))
        except (KeyError, TypeError, ValueError): continue
        # Day-ahead targets are expected to be after the decision date. The
        # availability timestamp is the authoritative leakage gate.
        gate = as_of or decision
        if label is None or decision is None or label[0] > gate or (as_of is not None and target >= gate.date()): continue
        if not all(math.isfinite(x) for x in (mean, sigma)) or sigma <= 0: continue
        for fields in (("city", "model_name", "temp_type", "lead_bucket", "month"), ("city", "model_name", "temp_type", "lead_bucket"), ("city", "model_name", "temp_type"), ("city", "temp_type")):
            groups[_key(row, fields)].append((mean, label[1], sigma))
    fitted = {}
    for key, values in groups.items():
        result = _fit(values, min_training)
        if result is not None: fitted[key] = result
    return fitted


def apply_emos(forecasts: list[dict], fitted: dict[tuple[str, ...], tuple[float, float, float, int]]) -> list[dict]:
    fields = (("city", "model_name", "temp_type", "lead_bucket", "month"), ("city", "model_name", "temp_type", "lead_bucket"), ("city", "model_name", "temp_type"), ("city", "temp_type"))
    output = []
    for row in forecasts:
        selected = None
        for group_fields in fields:
            selected = fitted.get(_key(row, group_fields))
            if selected: break
        intercept, slope, scale, count = selected or (0.0, 1.0, 1.0, 0)
        result = dict(row)
        try:
            mean = float(row["mean_f"]); sigma = float(row["stddev_f"])
            result["mean_f"] = f"{intercept + slope * mean:.6f}"
            result["stddev_f"] = f"{max(sigma * scale, MIN_STDDEV):.6f}"
        except (KeyError, TypeError, ValueError): pass
        result["emos_intercept"] = f"{intercept:.6f}"; result["emos_slope"] = f"{slope:.6f}"
        result["emos_spread_scale"] = f"{scale:.6f}"; result["emos_training_rows"] = str(count)
        result["model_version"] = f"{row.get('model_version', '')}+emos_v1"
        output.append(result)
    return output


def render(training_forecasts: Path, training_labels: Path, forecasts: Path, output: Path) -> int:
    with training_forecasts.open(newline="") as fh: train = list(csv.DictReader(fh))
    with training_labels.open(newline="") as fh: labels = list(csv.DictReader(fh))
    with forecasts.open(newline="") as fh: current = list(csv.DictReader(fh))
    rows = apply_emos(current, fit_emos(train, labels))
    output.parent.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0]) if rows else list(current[0]) if current else []
    with output.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields); writer.writeheader(); writer.writerows(rows)
    return len(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--training-forecasts", type=Path, required=True); parser.add_argument("--training-labels", type=Path, required=True)
    parser.add_argument("--forecasts", type=Path, required=True); parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(); print(f"wrote {render(args.training_forecasts, args.training_labels, args.forecasts, args.output)} EMOS rows")


if __name__ == "__main__": main()

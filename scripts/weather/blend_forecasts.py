"""Build an auditable convex blend of forecast distributions."""
from __future__ import annotations

import argparse
import csv
import math
import sys
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

_SELF = Path(__file__).resolve().parent
sys.path.insert(0, str(_SELF))
from common import parse_utc_iso  # noqa: E402


def _eligible_training(forecasts: list[dict], labels: list[dict], as_of: datetime | None = None) -> dict[str, list[tuple[str, float]]]:
    label_index = {}
    for label in labels:
        ts = parse_utc_iso(label.get("label_available_ts"))
        try: observed = float(label.get("observed_f", ""))
        except (TypeError, ValueError): continue
        if ts is not None and math.isfinite(observed): label_index[label.get("event_ticker", "")] = (ts, observed)
    groups = defaultdict(list)
    for row in forecasts:
        label = label_index.get(row.get("event_ticker", "")); decision = parse_utc_iso(row.get("decision_time_utc"))
        try: target, mean = date.fromisoformat(row["outcome_local_date"]), float(row["mean_f"])
        except (KeyError, TypeError, ValueError): continue
        # A fold fit is allowed to use a forecast only after its label was
        # published and before the fold clock. This permits day-ahead rows,
        # whose label is unavailable at their original decision time.
        if not row.get("model_name") or label is None or decision is None or (as_of is None and label[0] > decision) or (as_of is not None and label[0] > as_of) or (as_of is not None and target >= as_of.date()) or not math.isfinite(mean): continue
        groups[row["model_name"]].append((row["event_ticker"], abs(label[1] - mean)))
    return groups


def fit_weights(forecasts: list[dict], labels: list[dict], min_training: int = 3, as_of: datetime | None = None) -> dict[str, float]:
    grouped = _eligible_training(forecasts, labels, as_of)
    scores = {model: sum(error for _, error in errors) / len(errors) for model, errors in grouped.items() if len(errors) >= min_training}
    if not scores: return {}
    inverse = {model: 1.0 / max(error, 1e-6) for model, error in scores.items()}
    total = sum(inverse.values())
    return {model: weight / total for model, weight in inverse.items()}


def apply_blend(forecasts: list[dict], weights: dict[str, float]) -> list[dict]:
    grouped = defaultdict(list)
    for row in forecasts: grouped[row.get("event_ticker", "")].append(row)
    output = []
    for event, rows in grouped.items():
        selected = [(row, weights[row.get("model_name", "")]) for row in rows if row.get("model_name", "") in weights]
        if not selected: continue
        total = sum(weight for _, weight in selected)
        selected = [(row, weight / total) for row, weight in selected]
        try:
            mean = sum(weight * float(row["mean_f"]) for row, weight in selected)
            variance = sum(weight * (float(row.get("stddev_f", "0") or 0) ** 2 + (float(row["mean_f"]) - mean) ** 2) for row, weight in selected)
        except (TypeError, ValueError): continue
        first = selected[0][0]
        result = dict(first)
        result.update({"model_name": "convex_blend", "model_version": "inverse_mae_v1", "mean_f": f"{mean:.6f}", "stddev_f": f"{max(math.sqrt(max(variance, 0)), 0.01):.6f}", "blend_member_count": str(len(selected)), "blend_weights": ";".join(f"{row.get('model_name')}:{weight:.8f}" for row, weight in selected)})
        output.append(result)
    return output


def render(training_forecasts: Path, training_labels: Path, forecasts: Path, output: Path) -> int:
    with training_forecasts.open(newline="") as fh: training = list(csv.DictReader(fh))
    with training_labels.open(newline="") as fh: labels = list(csv.DictReader(fh))
    with forecasts.open(newline="") as fh: current = list(csv.DictReader(fh))
    rows = apply_blend(current, fit_weights(training, labels))
    output.parent.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0]) if rows else list(current[0]) if current else []
    with output.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields); writer.writeheader(); writer.writerows(rows)
    return len(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--training-forecasts", type=Path, required=True); parser.add_argument("--training-labels", type=Path, required=True); parser.add_argument("--forecasts", type=Path, required=True); parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(); print(f"wrote {render(args.training_forecasts, args.training_labels, args.forecasts, args.output)} blend rows")


if __name__ == "__main__": main()

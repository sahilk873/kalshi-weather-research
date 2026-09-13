"""Build a leakage-safe persistence hurdle forecast from prior daily labels."""
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

CITY_ALIASES = {"nyc": "nyc", "new_york": "nyc", "la": "la", "los_angeles": "la", "los angeles": "la", "austin": "austin", "phx": "phx", "lv": "lv"}
OUTPUT_COLUMNS = [
    "event_ticker", "decision_time_utc", "forecast_issue_time", "source_receipt_time",
    "model_name", "model_version", "city", "temp_type", "outcome_local_date",
    "lead_hours", "mean_f", "stddev_f", "training_rows",
]


def _city(value: object) -> str:
    return CITY_ALIASES.get(str(value or "").strip().lower(), "")


def build_rows(schedules: list[dict], labels: list[dict], window: int = 30) -> tuple[list[dict], list[dict]]:
    required_schedule = {"event_ticker", "decision_time_utc", "city", "temp_type", "outcome_local_date", "lead_hours"}
    required_labels = {"city", "date", "tmax_f", "tmin_f", "label_available_ts"}
    if schedules and (missing := required_schedule - set(schedules[0])):
        raise ValueError(f"schedule input missing required columns: {sorted(missing)}")
    if labels and (missing := required_labels - set(labels[0])):
        raise ValueError(f"label input missing required columns: {sorted(missing)}")
    index: dict[tuple[str, str], list[tuple[date, object, float]]] = defaultdict(list)
    for row in labels:
        city = _city(row.get("city"))
        try:
            day = date.fromisoformat(str(row.get("date", "")))
            available = parse_utc_iso(row.get("label_available_ts"))
            high, low = float(row.get("tmax_f")), float(row.get("tmin_f"))
        except (TypeError, ValueError):
            continue
        if not city or available is None:
            continue
        for temp_type, value in (("high", high), ("low", low)):
            if math.isfinite(value):
                index[(city, temp_type)].append((day, available, value))
    output, rejected = [], []
    for row in schedules:
        city = _city(row.get("city")); temp_type = str(row.get("temp_type", "")).strip().lower()
        decision = parse_utc_iso(row.get("decision_time_utc"))
        try:
            target = date.fromisoformat(str(row.get("outcome_local_date", "")))
        except ValueError:
            target = None
        if not city or temp_type not in {"high", "low"} or decision is None or target is None:
            rejected.append({"event_ticker": row.get("event_ticker", ""), "reason": "invalid_schedule"})
            continue
        prior = [(day, value) for day, available, value in index[(city, temp_type)]
                 if day < target and available <= decision]
        if not prior:
            rejected.append({"event_ticker": row.get("event_ticker", ""), "reason": "no_prior_available_label"})
            continue
        prior.sort(key=lambda item: item[0])
        training = [value for _, value in prior[-max(1, window):]]
        mean = training[-1]
        sigma = math.sqrt(sum((value - sum(training) / len(training)) ** 2 for value in training) / (len(training) - 1)) if len(training) > 1 else None
        decision_text = decision.isoformat().replace("+00:00", "Z")
        output.append({
            "event_ticker": row["event_ticker"], "decision_time_utc": decision_text,
            "forecast_issue_time": decision_text, "source_receipt_time": decision_text,
            "model_name": "persistence", "model_version": f"last_value_v1_window{window}",
            "city": city, "temp_type": temp_type, "outcome_local_date": target.isoformat(),
            "lead_hours": row["lead_hours"], "mean_f": f"{mean:.6f}",
            "stddev_f": "" if sigma is None or sigma <= 0 else f"{sigma:.6f}",
            "training_rows": str(len(training)),
        })
    return output, rejected


def render(schedule_path: Path, labels_path: Path, output_path: Path, rejection_path: Path | None = None, window: int = 30) -> tuple[int, int]:
    with schedule_path.open(newline="") as fh:
        schedules = list(csv.DictReader(fh))
    with labels_path.open(newline="") as fh:
        labels = list(csv.DictReader(fh))
    rows, rejected = build_rows(schedules, labels, window)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=OUTPUT_COLUMNS); writer.writeheader(); writer.writerows(rows)
    if rejection_path:
        rejection_path.parent.mkdir(parents=True, exist_ok=True)
        with rejection_path.open("w", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=["event_ticker", "reason"]); writer.writeheader(); writer.writerows(rejected)
    return len(rows), len(rejected)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--schedule", type=Path, required=True)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--rejections", type=Path)
    parser.add_argument("--window", type=int, default=30)
    args = parser.parse_args()
    print(render(args.schedule, args.labels, args.output, args.rejections, args.window))


if __name__ == "__main__":
    main()

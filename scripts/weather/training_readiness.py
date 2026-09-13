"""Create a fail-closed rolling-origin training/calibration/test plan.

This is a planning and validation artifact, not a model-fit claim.  Complete
target events are kept in one partition, and no partition is emitted as ready
unless it has distinct chronological target dates.
"""
from __future__ import annotations

import argparse
import csv
import json
from datetime import date
from pathlib import Path


def _day(row: dict) -> date | None:
    value = row.get("target_time_utc") or row.get("target_ts") or row.get("outcome_local_date")
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def plan(rows: list[dict], *, train_days: int = 365, calibration_days: int = 30,
         test_days: int = 30, embargo_days: int = 0) -> dict:
    dates = sorted({stamp for row in rows if (stamp := _day(row)) is not None})
    required = train_days + calibration_days + test_days + embargo_days
    if not dates:
        return {"version": "report2-training-plan-v1", "status": "data_missing",
                "reason": "no parseable target dates", "folds": [], "unique_target_dates": 0}
    if len(dates) < required:
        return {"version": "report2-training-plan-v1", "status": "insufficient_history",
                "reason": f"need at least {required} distinct target dates for configured partitions",
                "folds": [], "unique_target_dates": len(dates), "required_target_dates": required}
    folds = []
    # Use an expanding train window and non-overlapping calibration/test windows.
    for end in range(required, len(dates) + 1, test_days):
        test_end = min(end, len(dates))
        test_start = test_end - test_days
        calibration_start = test_start - embargo_days - calibration_days
        train_end = calibration_start - embargo_days
        train_start = max(0, train_end - train_days)
        if train_end <= train_start or calibration_start < 0:
            continue
        folds.append({"fold": len(folds), "train_start": dates[train_start].isoformat(),
                      "train_end": dates[train_end - 1].isoformat(),
                      "calibration_start": dates[calibration_start].isoformat(),
                      "calibration_end": dates[test_start - embargo_days - 1].isoformat(),
                      "test_start": dates[test_start].isoformat(),
                      "test_end": dates[test_end - 1].isoformat(),
                      "embargo_days": embargo_days})
    status = "ready" if folds else "insufficient_history"
    return {"version": "report2-training-plan-v1", "status": status,
            "reason": "chronological event-level partitions" if folds else "no valid fold",
            "folds": folds, "unique_target_dates": len(dates), "required_target_dates": required}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--train-days", type=int, default=365)
    parser.add_argument("--calibration-days", type=int, default=30)
    parser.add_argument("--test-days", type=int, default=30)
    parser.add_argument("--embargo-days", type=int, default=0)
    args = parser.parse_args()
    with args.input.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    result = plan(rows, train_days=args.train_days, calibration_days=args.calibration_days,
                  test_days=args.test_days, embargo_days=args.embargo_days)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": result["status"], "folds": len(result["folds"])}))


if __name__ == "__main__":
    main()

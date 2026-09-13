"""Evaluate forecast CSVs on chronological, embargo-aware test folds."""
from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path

from evaluate_forecast_skill import build_rows, read_csv
from validation_controls import walk_forward_folds


def evaluate(forecasts: list[dict], labels: list[dict], train_days: int = 365,
             test_days: int = 30, embargo_days: int = 0) -> tuple[list[dict], list]:
    good, rejected = build_rows(forecasts, labels)
    folds = walk_forward_folds(forecasts, train_days=train_days,
                               test_days=test_days, embargo_days=embargo_days)
    output = []
    for fold in folds:
        test_dates = set(fold["test_dates"])
        groups = defaultdict(list)
        for row in good:
            if row.get("outcome_local_date") in test_dates:
                groups[(row["model_name"], row["model_version"], row["city"], row["temp_type"], row["lead_hours"])].append(row)
        for key, rows in sorted(groups.items()):
            crps_rows = [row for row in rows if row["crps_f"] is not None]
            output.append({"fold": str(fold["fold"]), "train_start": fold["train_start"], "train_end": fold["train_end"], "test_start": fold["test_start"], "test_end": fold["test_end"], "model_name": key[0], "model_version": key[1], "city": key[2], "temp_type": key[3], "lead_hours": key[4], "eligible_predictions": str(len(rows)), "mae_f": f"{sum(abs(r['mean_f'] - r['observed_f']) for r in rows) / len(rows):.6f}", "crps_predictions": str(len(crps_rows)), "crps_f": f"{sum(r['crps_f'] for r in crps_rows) / len(crps_rows):.6f}" if crps_rows else ""})
    return output, rejected


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--forecasts", type=Path, required=True)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--train-days", type=int, default=365)
    parser.add_argument("--test-days", type=int, default=30)
    parser.add_argument("--embargo-days", type=int, default=0)
    args = parser.parse_args()
    rows, rejected = evaluate(read_csv(args.forecasts), read_csv(args.labels), args.train_days, args.test_days, args.embargo_days)
    fields = ["fold", "train_start", "train_end", "test_start", "test_end", "model_name", "model_version", "city", "temp_type", "lead_hours", "eligible_predictions", "mae_f", "crps_predictions", "crps_f"]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields); writer.writeheader(); writer.writerows(rows)
    print(f"wrote {len(rows)} fold rows; evaluator_rejections={len(rejected)}")


if __name__ == "__main__": main()

"""Evaluate convex forecast blending in chronological outer folds."""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from blend_forecasts import apply_blend, fit_weights  # noqa: E402
from evaluate_forecast_skill import build_rows, read_csv  # noqa: E402
from validation_controls import walk_forward_folds  # noqa: E402


def evaluate(forecast_paths: list[Path], labels_path: Path, output: Path,
             train_days: int = 365, test_days: int = 30) -> tuple[int, int]:
    forecasts = []
    for path in forecast_paths:
        forecasts.extend(read_csv(path))
    labels = read_csv(labels_path)
    if not forecasts:
        raise ValueError("forecast inputs are empty")
    folds = walk_forward_folds(forecasts, train_days=train_days, test_days=test_days)
    fields = ["fold", "train_start", "train_end", "test_start", "test_end",
              "eligible_predictions", "rejected_predictions", "mae_f", "crps_f",
              "member_models", "weights"]
    rows = []
    for fold in folds:
        test_dates = set(fold["test_dates"])
        train_start, train_end = fold["train_start"], fold["train_end"]
        test_start, test_end = fold["test_start"], fold["test_end"]
        train = [r for r in forecasts if train_start <= r.get("outcome_local_date", "") <= train_end]
        test = [r for r in forecasts if r.get("outcome_local_date", "") in test_dates]
        if not train or not test:
            continue
        as_of = datetime.fromisoformat(test_start).replace(tzinfo=timezone.utc)
        weights = fit_weights(train, labels, as_of=as_of)
        if len(weights) < 2:
            continue
        blended = apply_blend(test, weights)
        good, bad = build_rows(blended, labels)
        if not good:
            continue
        mae = sum(abs(r["mean_f"] - r["observed_f"]) for r in good) / len(good)
        scores = [r["crps_f"] for r in good if r["crps_f"] is not None]
        rows.append({"fold": str(fold["fold"]), "train_start": train_start,
                     "train_end": train_end, "test_start": test_start,
                     "test_end": test_end,
                     "eligible_predictions": str(len(good)),
                     "rejected_predictions": str(len(bad)), "mae_f": f"{mae:.6f}",
                     "crps_f": f"{sum(scores) / len(scores):.6f}" if scores else "",
                     "member_models": ";".join(sorted(weights)),
                     "weights": ";".join(f"{k}:{weights[k]:.8f}" for k in sorted(weights))})
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields); writer.writeheader(); writer.writerows(rows)
    return len(rows), sum(int(r["eligible_predictions"]) for r in rows)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--forecasts", nargs="+", type=Path, required=True)
    p.add_argument("--labels", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--train-days", type=int, default=365)
    p.add_argument("--test-days", type=int, default=30)
    a = p.parse_args()
    print(evaluate(a.forecasts, a.labels, a.output, a.train_days, a.test_days))


if __name__ == "__main__":
    main()

"""Reusable walk-forward and calibration controls for weather evaluations."""
from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from typing import Iterable, Mapping


def walk_forward_folds(rows: Iterable[Mapping[str, object]], date_field: str = "outcome_local_date", train_days: int = 90, test_days: int = 14, step_days: int | None = None, embargo_days: int = 0) -> list[dict]:
    """Return chronological train/test memberships with an optional embargo.

    Dates are deduplicated before splitting, so multiple buckets from one event
    cannot land in different folds. A test window starts after the train end
    plus ``embargo_days`` and folds advance by ``step_days`` (default test
    length).
    """
    if train_days <= 0 or test_days <= 0 or embargo_days < 0:
        raise ValueError("train_days/test_days must be positive and embargo_days non-negative")
    dates = sorted({date.fromisoformat(str(row[date_field])) for row in rows if row.get(date_field)})
    if not dates:
        return []
    step = step_days or test_days
    if step <= 0: raise ValueError("step_days must be positive")
    first = dates[0]
    last = dates[-1]
    folds = []
    fold_id = 0
    train_start = first
    while True:
        train_end = train_start + timedelta(days=train_days - 1)
        test_start = train_end + timedelta(days=1 + embargo_days)
        test_end = test_start + timedelta(days=test_days - 1)
        train_dates = [d.isoformat() for d in dates if train_start <= d <= train_end]
        test_dates = [d.isoformat() for d in dates if test_start <= d <= test_end]
        if train_dates and test_dates:
            folds.append({"fold": fold_id, "train_start": train_start.isoformat(), "train_end": train_end.isoformat(), "test_start": test_start.isoformat(), "test_end": test_end.isoformat(), "train_dates": train_dates, "test_dates": test_dates})
            fold_id += 1
        if test_end >= last: break
        train_start += timedelta(days=step)
    return folds


def reliability_bins(probabilities: Iterable[Mapping[str, object]], probability_field: str = "probability", outcome_field: str = "outcome", bins: int = 10) -> list[dict]:
    """Summarize forecast probability versus empirical event frequency."""
    if bins <= 0: raise ValueError("bins must be positive")
    groups = defaultdict(list)
    for row in probabilities:
        try: p, y = float(row[probability_field]), float(row[outcome_field])
        except (KeyError, TypeError, ValueError): continue
        if not 0 <= p <= 1 or y not in (0, 1): continue
        index = min(int(p * bins), bins - 1)
        groups[index].append((p, y))
    output = []
    for index in range(bins):
        values = groups.get(index, [])
        output.append({"bin": index, "lower": index / bins, "upper": (index + 1) / bins, "count": len(values), "mean_probability": sum(p for p, _ in values) / len(values) if values else "", "event_rate": sum(y for _, y in values) / len(values) if values else ""})
    return output

"""Leakage-safe forecast as-of filtering for training and backtests."""
from __future__ import annotations
import csv
from datetime import datetime, timezone

def _dt(v): return datetime.fromisoformat(v.replace("Z", "+00:00")).astimezone(timezone.utc)
def known_forecasts(rows, decision_time_utc):
    t = _dt(decision_time_utc) if isinstance(decision_time_utc, str) else decision_time_utc
    # A forecast for a future valid time is usable once its model run has
    # initialized. Do not discard those rows: they are precisely the signal
    # used to predict a later daily extreme.
    out = [r for r in rows if _dt(r["initialization_time_utc"]) <= t]
    if any(_dt(r["initialization_time_utc"]) > t for r in out): raise AssertionError("forecast initialization after decision time")
    return out

def valid_forecasts_asof(rows, decision_time_utc):
    """Restrict observations joined at a timestamp to already-valid fields."""
    t = _dt(decision_time_utc) if isinstance(decision_time_utc, str) else decision_time_utc
    return [r for r in known_forecasts(rows, t) if _dt(r["valid_time_utc"]) <= t]
def filter_csv(path, decision_time, output):
    with open(path, newline="") as f: rows = list(csv.DictReader(f))
    rows = known_forecasts(rows, decision_time)
    with open(output, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=rows[0].keys() if rows else []); w.writeheader(); w.writerows(rows)
    return len(rows)

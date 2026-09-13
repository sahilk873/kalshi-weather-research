"""Leakage-safe forecast as-of filtering for training and backtests."""
from __future__ import annotations

import csv
from datetime import datetime, timezone

from common import parse_utc_iso  # noqa: E402
from pit import available_asof  # noqa: E402


def _aware_utc(value: object, label: str) -> datetime:
    parsed = parse_utc_iso(value)
    if parsed is None:
        raise ValueError(f"missing or invalid {label}; expected an ISO-8601 UTC timestamp")
    return parsed


def _decision_time(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    return _aware_utc(value, "decision_time_utc")


def known_forecasts(rows, decision_time_utc):
    """Forecasts initialized and received by a decision time.

    A forecast for a future valid time is usable once its model run has
    initialized. Do not discard those rows: they are precisely the signal
    used to predict a later daily extreme. Missing issue/receipt timestamps
    fail closed and raise.
    """
    t = _decision_time(decision_time_utc)
    out = [r for r in rows if available_asof(
        r, t,
        issue_fields=("initialization_time_utc",),
        receipt_fields=("source_receipt_time", "receipt_time_utc",
                        "ingested_at_utc", "ingested_at", "retrieved_at"),
    )]
    for r in out:
        if _aware_utc(r["initialization_time_utc"], "initialization_time_utc") > t:
            raise AssertionError("forecast initialization after decision time")
    return out


def valid_forecasts_asof(rows, decision_time_utc):
    """Restrict observations joined at a timestamp to already-valid fields.

    Unlike :func:`known_forecasts`, rows whose ``valid_time_utc`` is after the
    decision time are excluded; a missing/invalid valid time fails closed.
    """
    t = _decision_time(decision_time_utc)
    kept = []
    for r in known_forecasts(rows, t):
        valid = _aware_utc(r.get("valid_time_utc"), "valid_time_utc")
        if valid <= t:
            kept.append(r)
    return kept


def filter_csv(path, decision_time, output):
    with open(path, newline="") as f:
        rows = list(csv.DictReader(f))
    rows = known_forecasts(rows, decision_time)
    with open(output, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys() if rows else [])
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)
"""Bitemporal availability checks shared by point-in-time research joins."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Mapping

from common import parse_utc_iso

RECEIPT_TIME_FIELDS = ("source_receipt_time", "receipt_time_utc", "retrieved_at", "ingested_at_utc", "ingested_at")
ISSUE_TIME_FIELDS = ("forecast_issue_time", "initialization_time_utc", "issue_time_utc", "publication_time_utc")


def available_asof(
    row: Mapping[str, object], decision_time_utc: str | datetime,
    issue_fields: tuple[str, ...] = ISSUE_TIME_FIELDS,
    receipt_fields: tuple[str, ...] = RECEIPT_TIME_FIELDS,
) -> bool:
    """Return whether an input was both issued and received by a decision time.

    Missing timestamps fail closed.  Event time/valid time describes what a
    record is about; it does not establish that the researcher could have seen
    it.  Callers may pass narrower field tuples for source-specific schemas.
    """
    decision = _timestamp(decision_time_utc, "decision_time_utc")
    issue = _first_timestamp(row, issue_fields, "issue")
    receipt = _first_timestamp(row, receipt_fields, "receipt")
    return issue <= decision and receipt <= decision


def assert_available_asof(row: Mapping[str, object], decision_time_utc: str | datetime) -> None:
    if not available_asof(row, decision_time_utc):
        raise AssertionError("input issue/receipt time is after decision time or missing")


def _first_timestamp(row: Mapping[str, object], fields: tuple[str, ...], label: str) -> datetime:
    for field in fields:
        value = row.get(field)
        parsed = parse_utc_iso(value)
        if parsed is not None:
            return parsed
    raise ValueError(f"missing or invalid {label} timestamp; expected one of {fields}")


def _timestamp(value: str | datetime, label: str) -> datetime:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
    parsed = parse_utc_iso(value)
    if parsed is None:
        raise ValueError(f"missing or invalid {label}")
    return parsed

"""Source-agnostic point-in-time feature vintages.

The store is deliberately long-form: each input row is one version of one
feature for one market decision key.  A row is eligible only when its exact,
observed, or explicitly estimated availability is no later than the decision
clock.  When several revisions are eligible, the latest available revision is
selected without looking at revisions that arrived later.

Historical latency is never assumed implicitly.  Estimated availability
requires both ``availability_reference_time`` on the row and a caller-supplied
latency policy for the requested scenario.
"""
from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Mapping

from common import parse_utc_iso, utc_iso

SCENARIOS = ("optimistic", "base", "conservative", "highly_conservative")
DECISION_FIELDS = ("city", "contract", "target_time_utc", "decision_time_utc")
FEATURE_FIELDS = (
    "city", "contract", "target_time_utc", "decision_time_utc",
    "feature_name", "source", "source_event_time", "issue_time",
    "valid_time", "revision", "available_at", "availability_method",
    "availability_reference_time", "assumed_latency_seconds", "retrieved_at",
    "value", "provenance", "latency_scenario",
)


def _text(row: Mapping[str, object], field: str) -> str:
    value = row.get(field, "")
    return "" if value is None else str(value).strip()


def _timestamp(row: Mapping[str, object], field: str, *, required: bool = False) -> datetime | None:
    value = _text(row, field)
    parsed = parse_utc_iso(value)
    if required and parsed is None:
        raise ValueError(f"missing or invalid {field}")
    if value and parsed is None:
        raise ValueError(f"invalid {field}")
    return parsed


def _policy_delay(
    policies: Mapping[str, object], source: str, feature_name: str, scenario: str,
) -> float:
    """Resolve seconds from ``source/feature``, ``source``, then ``*`` policy."""
    for key in (f"{source}/{feature_name}", source, "*"):
        policy = policies.get(key)
        if isinstance(policy, Mapping) and scenario in policy:
            try:
                seconds = float(policy[scenario])
            except (TypeError, ValueError) as exc:
                raise ValueError(f"invalid {scenario} latency for policy {key}") from exc
            if seconds < 0:
                raise ValueError(f"negative {scenario} latency for policy {key}")
            return seconds
    raise ValueError(f"no {scenario} latency policy for source {source}")


def effective_availability(
    row: Mapping[str, object], scenario: str,
    policies: Mapping[str, object] | None = None,
) -> tuple[datetime, str, float | None]:
    """Return the effective availability clock, method, and assumed delay.

    Precedence is intentional: an explicit historical ``available_at`` is
    strongest, an observed ``retrieved_at`` is a conservative receipt bound,
    and an estimate is permitted only from an explicit reference clock plus a
    supplied scenario policy.
    """
    if scenario not in SCENARIOS:
        raise ValueError(f"unknown latency scenario {scenario!r}")
    exact = _timestamp(row, "available_at")
    if exact is not None:
        return exact, "exact", None
    receipt = _timestamp(row, "retrieved_at")
    if receipt is not None:
        return receipt, "observed_receipt", None
    reference = _timestamp(row, "availability_reference_time")
    if reference is None:
        raise ValueError(
            "missing availability: expected available_at, retrieved_at, or "
            "availability_reference_time with a latency policy"
        )
    source = _text(row, "source")
    feature_name = _text(row, "feature_name")
    seconds = _policy_delay(policies or {}, source, feature_name, scenario)
    return reference + timedelta(seconds=seconds), "estimated", seconds


def _normalize_feature(
    row: Mapping[str, object], scenario: str, policies: Mapping[str, object],
) -> dict[str, object]:
    for field in ("city", "contract", "target_time_utc", "feature_name", "source", "value", "provenance"):
        if not _text(row, field):
            raise ValueError(f"missing {field}")
    _timestamp(row, "target_time_utc", required=True)
    for field in ("source_event_time", "issue_time", "valid_time", "retrieved_at", "availability_reference_time"):
        _timestamp(row, field)
    available, method, delay = effective_availability(row, scenario, policies)
    issue = _timestamp(row, "issue_time")
    source_event = _timestamp(row, "source_event_time")
    if issue is not None and issue > available:
        raise ValueError("issue_time is after available_at")
    if source_event is not None and source_event > available:
        raise ValueError("source_event_time is after available_at")
    normalized: dict[str, object] = {field: _text(row, field) for field in FEATURE_FIELDS}
    normalized.update({
        "available_at": utc_iso(available),
        "availability_method": method,
        "assumed_latency_seconds": "" if delay is None else f"{delay:g}",
        "latency_scenario": scenario,
    })
    return normalized


def _decision_key(row: Mapping[str, object]) -> tuple[str, str, str]:
    return (_text(row, "city"), _text(row, "contract"), _text(row, "target_time_utc"))


def reconstruct_vintages(
    features: list[Mapping[str, object]],
    decisions: list[Mapping[str, object]],
    *,
    scenario: str = "base",
    latency_policies: Mapping[str, object] | None = None,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """Build deterministic feature vintages and an explicit rejection ledger."""
    if scenario not in SCENARIOS:
        raise ValueError(f"unknown latency scenario {scenario!r}")
    policies = latency_policies or {}
    normalized_by_key: dict[tuple[str, str, str], list[dict[str, object]]] = {}
    rejected: list[dict[str, object]] = []
    for row_number, row in enumerate(features, 2):
        try:
            normalized = _normalize_feature(row, scenario, policies)
        except ValueError as exc:
            rejected.append({"kind": "feature", "row": row_number, "reason": str(exc)})
            continue
        normalized_by_key.setdefault(_decision_key(normalized), []).append(normalized)

    output: list[dict[str, object]] = []
    for row_number, decision_row in enumerate(decisions, 2):
        try:
            for field in DECISION_FIELDS:
                if not _text(decision_row, field):
                    raise ValueError(f"missing {field}")
            decision = _timestamp(decision_row, "decision_time_utc", required=True)
            _timestamp(decision_row, "target_time_utc", required=True)
            assert decision is not None
        except ValueError as exc:
            rejected.append({"kind": "decision", "row": row_number, "reason": str(exc)})
            continue

        latest: dict[tuple[str, str], dict[str, object]] = {}
        candidates = normalized_by_key.get(_decision_key(decision_row), [])
        for candidate in candidates:
            available = parse_utc_iso(candidate["available_at"])
            assert available is not None
            if available > decision:
                continue
            identity = (_text(candidate, "source"), _text(candidate, "feature_name"))
            # Arrival time controls vintage selection. Other clocks and the
            # revision token make equal-arrival selection deterministic.
            rank = (
                available,
                parse_utc_iso(candidate["issue_time"]) or datetime.min.replace(tzinfo=available.tzinfo),
                parse_utc_iso(candidate["source_event_time"]) or datetime.min.replace(tzinfo=available.tzinfo),
                _text(candidate, "revision"),
                _text(candidate, "provenance"),
            )
            previous = latest.get(identity)
            if previous is None or rank > previous["_rank"]:
                selected = dict(candidate)
                selected["_rank"] = rank
                latest[identity] = selected
        if not latest:
            rejected.append({
                "kind": "decision", "row": row_number,
                "reason": "no_features_available_asof_decision",
                **{field: _text(decision_row, field) for field in DECISION_FIELDS},
            })
            continue
        for selected in latest.values():
            selected.pop("_rank", None)
            selected["decision_time_utc"] = utc_iso(decision)
            output.append(selected)

    output.sort(key=lambda row: tuple(_text(row, field) for field in (
        "city", "contract", "target_time_utc", "decision_time_utc", "source", "feature_name",
    )))
    return output, rejected


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def _write_csv(path: Path, fields: tuple[str, ...] | list[str], rows: list[Mapping[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--features", type=Path, required=True)
    parser.add_argument("--decisions", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--rejections", type=Path, required=True)
    parser.add_argument("--scenario", choices=SCENARIOS, default="base")
    parser.add_argument("--latency-policies", type=Path)
    args = parser.parse_args()
    policies = json.loads(args.latency_policies.read_text()) if args.latency_policies else {}
    rows, rejected = reconstruct_vintages(
        _read_csv(args.features), _read_csv(args.decisions),
        scenario=args.scenario, latency_policies=policies,
    )
    _write_csv(args.output, FEATURE_FIELDS, rows)
    rejection_fields = ["kind", "row", "reason", *DECISION_FIELDS]
    _write_csv(args.rejections, rejection_fields, rejected)
    print(json.dumps({"feature_rows": len(rows), "rejected_rows": len(rejected), "scenario": args.scenario}, sort_keys=True))


if __name__ == "__main__":
    main()

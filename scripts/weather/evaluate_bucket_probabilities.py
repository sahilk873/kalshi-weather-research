"""Evaluate coherent bucket probabilities with Brier and log loss.

Inputs are one row per event/market from ``bucket_probabilities.csv`` and a
label table containing the settled market ticker. The evaluator requires one
label strictly after the decision time and rejects incomplete or non-coherent
event partitions. It is a forecasting metric only; it does not use prices or
place orders.
"""
from __future__ import annotations

import argparse
import csv
import math
import sys
from collections import defaultdict
from pathlib import Path

_SELF = Path(__file__).resolve().parent
sys.path.insert(0, str(_SELF))
from pit import available_asof  # noqa: E402
from common import parse_utc_iso  # noqa: E402

SUMMARY_FIELDS = ["model_name", "model_version", "city", "temp_type", "events", "brier", "log_loss", "mean_probability_sum", "rejected_events"]
REJECTION_FIELDS = ["event_ticker", "reason", "detail"]


def _float(row: dict, field: str) -> float:
    value = float(row.get(field, ""))
    if not math.isfinite(value): raise ValueError(f"invalid {field}")
    return value


def evaluate(probabilities: list[dict], labels: list[dict]) -> tuple[list[dict], list[dict]]:
    labels_by_event = defaultdict(list)
    for label in labels:
        if label.get("event_ticker") and parse_utc_iso(label.get("label_available_ts")) is not None:
            labels_by_event[label["event_ticker"]].append(label)
    for rows in labels_by_event.values(): rows.sort(key=lambda r: parse_utc_iso(r["label_available_ts"]))
    groups = defaultdict(list); rejected = []
    by_event = defaultdict(list)
    for row in probabilities: by_event[row.get("event_ticker", "")].append(row)
    for event, rows in by_event.items():
        if not event:
            rejected.append({"event_ticker": event, "reason": "missing_event", "detail": "empty event ticker"}); continue
        try:
            decision = parse_utc_iso(rows[0].get("decision_time_utc"))
            if decision is None: raise ValueError("missing decision timestamp")
            if any(r.get("decision_time_utc") != rows[0].get("decision_time_utc") for r in rows): raise ValueError("inconsistent decision timestamp")
            values = [_float(r, "bucket_probability") for r in rows]
            if any(v < 0 or v > 1 for v in values): raise ValueError("probability outside [0,1]")
            total = sum(values)
            if abs(total - 1.0) > 1e-6: raise ValueError(f"probability sum {total:.12f} != 1")
            if any(not available_asof(r, decision, issue_fields=("forecast_issue_time",), receipt_fields=("source_receipt_time",)) for r in rows): raise ValueError("late or missing issue/receipt timestamp")
        except (TypeError, ValueError) as exc:
            rejected.append({"event_ticker": event, "reason": "invalid_partition", "detail": str(exc)}); continue
        candidates = [r for r in labels_by_event.get(event, []) if parse_utc_iso(r["label_available_ts"]) > decision]
        if not candidates:
            rejected.append({"event_ticker": event, "reason": "no_label_after_decision", "detail": "label unavailable point-in-time"}); continue
        label = candidates[0].get("settled_market_ticker", "")
        tickers = [r.get("market_ticker", "") for r in rows]
        if label not in tickers:
            rejected.append({"event_ticker": event, "reason": "label_not_in_partition", "detail": label}); continue
        brier = sum((p - (1.0 if ticker == label else 0.0)) ** 2 for ticker, p in zip(tickers, values))
        truth = values[tickers.index(label)]
        log_loss = -math.log(max(truth, 1e-15))
        first = rows[0]
        key = (first.get("model_name", ""), first.get("model_version", ""), first.get("city", ""), first.get("temp_type", ""))
        groups[key].append((brier, log_loss, total))
    summary = []
    for key, values in sorted(groups.items()):
        rejected_count = sum(1 for r in rejected if r["event_ticker"] in by_event and r["reason"] != "")
        summary.append(dict(zip(SUMMARY_FIELDS, [*key, len(values), f"{sum(v[0] for v in values)/len(values):.12f}", f"{sum(v[1] for v in values)/len(values):.12f}", f"{sum(v[2] for v in values)/len(values):.12f}", rejected_count])))
    return summary, rejected


def render(probability_path: Path, label_path: Path, output: Path, rejection_path: Path | None = None) -> tuple[int, int]:
    with probability_path.open(newline="") as fh: probabilities = list(csv.DictReader(fh))
    with label_path.open(newline="") as fh: labels = list(csv.DictReader(fh))
    summary, rejected = evaluate(probabilities, labels)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=SUMMARY_FIELDS); writer.writeheader(); writer.writerows(summary)
    if rejection_path:
        rejection_path.parent.mkdir(parents=True, exist_ok=True)
        with rejection_path.open("w", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=REJECTION_FIELDS); writer.writeheader(); writer.writerows(rejected)
    return len(summary), len(rejected)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--probabilities", type=Path, required=True); parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True); parser.add_argument("--rejections", type=Path)
    args = parser.parse_args(); print(render(args.probabilities, args.labels, args.output, args.rejections))


if __name__ == "__main__": main()

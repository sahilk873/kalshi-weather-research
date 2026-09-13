"""Build PIT evaluation labels from normalized settled market outcomes."""
from __future__ import annotations
import argparse, csv
from pathlib import Path

FIELDS = ["event_ticker", "label_available_ts", "settled_market_ticker"]

def build(outcomes: list[dict], labels: list[dict]) -> tuple[list[dict], list[dict]]:
    availability = {(r.get("city", ""), r.get("date", "")): r.get("label_available_ts", "") for r in labels}
    grouped = {}
    rejected = []
    for row in outcomes:
        if str(row.get("settled_yes", "")).lower() not in {"yes", "true", "1"}:
            continue
        key = row.get("event_ticker", "")
        city, day = row.get("city", ""), row.get("outcome_local_date", "")
        available = availability.get((city, day), "")
        if not key or not available:
            rejected.append({"event_ticker": key, "reason": "missing_label_availability"}); continue
        if key in grouped:
            rejected.append({"event_ticker": key, "reason": "multiple_settled_yes"}); continue
        grouped[key] = {"event_ticker": key, "label_available_ts": available, "settled_market_ticker": row.get("market_ticker", "")}
    return list(grouped.values()), rejected

def main() -> None:
    p = argparse.ArgumentParser(); p.add_argument("--outcomes", type=Path, required=True); p.add_argument("--labels", type=Path, required=True); p.add_argument("--output", type=Path, required=True); p.add_argument("--rejections", type=Path)
    a = p.parse_args()
    with a.outcomes.open(newline="") as f: outcomes = list(csv.DictReader(f))
    with a.labels.open(newline="") as f: labels = list(csv.DictReader(f))
    rows, rejected = build(outcomes, labels); a.output.parent.mkdir(parents=True, exist_ok=True)
    with a.output.open("w", newline="") as f: w = csv.DictWriter(f, fieldnames=FIELDS); w.writeheader(); w.writerows(rows)
    if a.rejections:
        with a.rejections.open("w", newline="") as f: w = csv.DictWriter(f, fieldnames=["event_ticker", "reason"]); w.writeheader(); w.writerows(rejected)
    print(f"wrote {len(rows)} settled labels; rejected={len(rejected)}")

if __name__ == "__main__": main()

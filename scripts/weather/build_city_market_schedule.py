"""Convert normalized daily temperature market metadata into a PIT schedule.

One row is emitted per event/series, using the earliest market opening time as
the decision timestamp. This is a research schedule only; it does not assert
that the GHCN proxy label is the event's Weather Company settlement value.
"""
from __future__ import annotations

import argparse
import csv
import re
from datetime import datetime
from pathlib import Path

SERIES = {
    # In-scope settlement series; auxiliary city lines remain below.
    "KXHIGHTPHX": ("phx", "high"), "KXLOWTPHX": ("phx", "low"),
    "KXHIGHTLV": ("lv", "high"), "KXLOWTLV": ("lv", "low"),
    "KXHIGHNY": ("nyc", "high"), "KXLOWTNYC": ("nyc", "low"),
    "KXHIGHLAX": ("la", "high"), "KXLOWTLAX": ("la", "low"),
    "KXHIGHAUS": ("austin", "high"), "KXLOWTAUS": ("austin", "low"),
}


def _event_date(event_ticker: str) -> str:
    match = re.search(r"-(\d{2})([A-Z]{3})(\d{2})(?:$|-)", event_ticker)
    if not match:
        return ""
    try:
        return datetime.strptime("".join(match.groups()), "%y%b%d").date().isoformat()
    except ValueError:
        return ""


def build_schedule(markets: list[dict]) -> tuple[list[dict], list[dict]]:
    grouped: dict[tuple[str, str], list[dict]] = {}
    rejected = []
    for row in markets:
        series = row.get("series_ticker", "")
        if series not in SERIES:
            continue
        event = row.get("event_ticker", "")
        target = _event_date(event)
        try:
            decision = datetime.fromisoformat(row.get("open_time", "").replace("Z", "+00:00"))
        except ValueError:
            rejected.append({"event_ticker": event, "reason": "invalid_open_time"})
            continue
        if not target:
            rejected.append({"event_ticker": event, "reason": "invalid_event_date"})
            continue
        key = (series, event)
        grouped.setdefault(key, []).append({"row": row, "target": target, "decision": decision})
    output = []
    for (series, event), candidates in sorted(grouped.items()):
        chosen = min(candidates, key=lambda item: item["decision"])
        city, temp_type = SERIES[series]
        decision = chosen["decision"].isoformat().replace("+00:00", "Z")
        target = chosen["target"]
        lead = max(0, (datetime.fromisoformat(target + "T12:00:00+00:00") - chosen["decision"].replace(hour=12, minute=0, second=0, microsecond=0)).total_seconds() / 3600)
        output.append({"event_ticker": event, "decision_time_utc": decision,
                       "city": city, "temp_type": temp_type,
                       "outcome_local_date": target, "lead_hours": f"{lead:.3f}"})
    return output, rejected


def build_labels(schedule: list[dict], labels: list[dict]) -> tuple[list[dict], list[dict]]:
    index = {(r.get("city", ""), r.get("date", "")): r for r in labels}
    output, rejected = [], []
    for row in schedule:
        label = index.get((row["city"], row["outcome_local_date"]))
        value_key = "tmax_f" if row["temp_type"] == "high" else "tmin_f"
        if not label or not label.get(value_key) or not label.get("label_available_ts"):
            rejected.append({"event_ticker": row["event_ticker"], "reason": "missing_proxy_label"})
            continue
        output.append({"event_ticker": row["event_ticker"],
                       "label_available_ts": label["label_available_ts"],
                       "observed_f": label[value_key]})
    return output, rejected


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields); writer.writeheader(); writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--markets", type=Path, required=True)
    parser.add_argument("--labels", type=Path)
    parser.add_argument("--schedule", type=Path, required=True)
    parser.add_argument("--evaluation-labels", type=Path)
    parser.add_argument("--rejections", type=Path)
    args = parser.parse_args()
    with args.markets.open(newline="") as fh:
        schedule, rejected = build_schedule(list(csv.DictReader(fh)))
    write_csv(args.schedule, schedule, ["event_ticker", "decision_time_utc", "city", "temp_type", "outcome_local_date", "lead_hours"])
    if args.labels and args.evaluation_labels:
        with args.labels.open(newline="") as fh:
            eval_labels, label_rejected = build_labels(schedule, list(csv.DictReader(fh)))
        rejected.extend(label_rejected)
        write_csv(args.evaluation_labels, eval_labels, ["event_ticker", "label_available_ts", "observed_f"])
    if args.rejections:
        write_csv(args.rejections, rejected, ["event_ticker", "reason"])
    print(f"schedule_rows={len(schedule)} rejected={len(rejected)}")


if __name__ == "__main__":
    main()

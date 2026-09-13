"""Evaluate leakage-safe observed-extrema nowcast diagnostics.

This measures how much error remains between the running ASOS high/low and the
final station label at each local hour. It is a diagnostic baseline for the
report's P2 nowcasting work, not a claim that observations alone beat NWP.
Rows are eligible only when the label availability timestamp is strictly after
the feature's ``feature_asof_utc`` timestamp.
"""
from __future__ import annotations

import argparse
import csv
import math
from collections import defaultdict
from datetime import date
from pathlib import Path
import sys

_SELF = Path(__file__).resolve().parent
sys.path.insert(0, str(_SELF))
from common import parse_utc_iso  # noqa: E402

CITY_ALIASES = {"nyc": "nyc", "new_york": "nyc", "la": "la", "los_angeles": "la", "los angeles": "la", "austin": "austin"}
SUMMARY_FIELDS = ["city", "local_hour", "eligible_rows", "days", "mae_high_f", "mae_low_f", "rejected_missing_label", "rejected_leakage"]


def _num(row: dict, field: str) -> float | None:
    try:
        value = float(row.get(field, ""))
        return value if math.isfinite(value) else None
    except (TypeError, ValueError):
        return None


def evaluate(state_rows: list[dict], labels: list[dict]) -> tuple[list[dict], list[dict]]:
    label_index = {}
    for row in labels:
        city = CITY_ALIASES.get(str(row.get("city", "")).strip().lower(), "")
        available = parse_utc_iso(row.get("label_available_ts"))
        try: target = date.fromisoformat(str(row.get("date", "")))
        except ValueError: continue
        high, low = _num(row, "tmax_f"), _num(row, "tmin_f")
        if city and available is not None and high is not None and low is not None:
            label_index[(city, target.isoformat())] = (available, high, low)
    groups: dict[tuple[str, str], list[tuple[float, float]]] = defaultdict(list)
    rejected = []
    for row in state_rows:
        city = CITY_ALIASES.get(str(row.get("city", "")).strip().lower(), "")
        key = (city, str(row.get("local_date", "")))
        label = label_index.get(key)
        feature_time = parse_utc_iso(row.get("feature_asof_utc") or row.get("valid_utc"))
        if label is None:
            rejected.append({"city": city, "local_date": key[1], "reason": "missing_label"}); continue
        if feature_time is None or label[0] <= feature_time:
            rejected.append({"city": city, "local_date": key[1], "reason": "label_not_available_asof"}); continue
        high, low = _num(row, "observed_high_so_far_f"), _num(row, "observed_low_so_far_f")
        try: hour = str(int(float(row.get("local_hour", ""))))
        except (TypeError, ValueError):
            rejected.append({"city": city, "local_date": key[1], "reason": "invalid_local_hour"}); continue
        if high is None or low is None:
            continue
        groups[(city, hour)].append((abs(high - label[1]), abs(low - label[2])))
    summary = []
    for (city, hour), values in sorted(groups.items()):
        summary.append({"city": city, "local_hour": hour, "eligible_rows": len(values), "days": "", "mae_high_f": f"{sum(v[0] for v in values) / len(values):.6f}", "mae_low_f": f"{sum(v[1] for v in values) / len(values):.6f}", "rejected_missing_label": sum(r["reason"] == "missing_label" and r["city"] == city for r in rejected), "rejected_leakage": sum(r["reason"] == "label_not_available_asof" and r["city"] == city for r in rejected)})
    return summary, rejected


def render(state_path: Path, labels_path: Path, output: Path, rejections: Path | None = None) -> tuple[int, int]:
    with state_path.open(newline="") as fh: state = list(csv.DictReader(fh))
    with labels_path.open(newline="") as fh: labels = list(csv.DictReader(fh))
    summary, rejected = evaluate(state, labels)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=SUMMARY_FIELDS); writer.writeheader(); writer.writerows(summary)
    if rejections:
        with rejections.open("w", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=["city", "local_date", "reason"]); writer.writeheader(); writer.writerows(rejected)
    return len(summary), len(rejected)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    root = Path(__file__).resolve().parents[2] / "data" / "weather_research"
    parser.add_argument("--state", type=Path, default=root / "derived_intraday_state_city" / "derived_intraday_state.csv")
    parser.add_argument("--labels", type=Path, default=root / "ghcn_city" / "labels_daily.csv")
    parser.add_argument("--output", type=Path, default=root / "reports" / "nowcast_skill_summary.csv")
    parser.add_argument("--rejections", type=Path, default=root / "reports" / "nowcast_rejections.csv")
    args = parser.parse_args(); print(render(args.state, args.labels, args.output, args.rejections))


if __name__ == "__main__": main()

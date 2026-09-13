"""Build fixed-length, point-in-time intraday sequence windows for P4 models."""
from __future__ import annotations

import argparse
import csv
import json
import math
from datetime import date
from pathlib import Path

FEATURES = ("current_temperature_f", "current_dew_point_f", "observed_high_so_far_f", "observed_low_so_far_f", "temperature_change_5m_f", "temperature_change_15m_f", "temperature_change_30m_f", "temperature_change_60m_f", "dewpoint_change_60m_f", "wind_speed_change_60m_kt", "cloud_change_60m", "minutes_since_sunrise", "minutes_until_sunset")
ALIASES = {"nyc": "nyc", "la": "la", "los_angeles": "la", "austin": "austin"}
OUT_FIELDS = ["city", "local_date", "temp_type", "decision_time_utc", "label_available_ts", "observed_f", "window_start_utc", "window_end_utc", "window_rows", "feature_names", "sequence_json"]


def _float(value: object) -> float | None:
    try:
        number = float(value); return number if math.isfinite(number) else None
    except (TypeError, ValueError): return None


def _utc_seconds(value: str) -> float | None:
    try:
        from datetime import datetime
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError, OverflowError):
        return None


def build(state_rows: list[dict], labels: list[dict], window: int = 12, stride: int = 1, max_gap_minutes: float | None = None) -> tuple[list[dict], list[dict]]:
    label_index = {}
    for row in labels:
        city = ALIASES.get(str(row.get("city", "")).lower(), "")
        try: day = date.fromisoformat(row["date"]); high = float(row["tmax_f"]); low = float(row["tmin_f"])
        except (KeyError, TypeError, ValueError): continue
        if city and row.get("label_available_ts"): label_index[(city, day)] = (row["label_available_ts"], high, low)
    groups = {}
    for row in state_rows:
        city = ALIASES.get(str(row.get("city", "")).lower(), "")
        if city and row.get("local_date") and row.get("feature_asof_utc"): groups.setdefault((city, row["local_date"]), []).append(row)
    output, rejected = [], []
    for (city, day_text), rows in sorted(groups.items()):
        try: day = date.fromisoformat(day_text)
        except ValueError: continue
        label = label_index.get((city, day))
        if label is None: rejected.append({"city": city, "local_date": day_text, "reason": "missing_label"}); continue
        rows.sort(key=lambda row: row["feature_asof_utc"])
        for index in range(window - 1, len(rows), max(1, stride)):
            current = rows[index]; decision = current["feature_asof_utc"]
            # Strict availability gate: finalized label must be observed after
            # the entire sequence's last feature timestamp.
            decision_ts = _utc_seconds(decision); label_ts = _utc_seconds(label[0])
            if decision_ts is None or label_ts is None:
                rejected.append({"city": city, "local_date": day_text, "reason": "invalid_timestamp"}); continue
            if label_ts <= decision_ts:
                rejected.append({"city": city, "local_date": day_text, "reason": "label_not_available_asof"}); continue
            sequence_rows = rows[index - window + 1:index + 1]
            if max_gap_minutes is not None:
                times = [_utc_seconds(row["feature_asof_utc"]) for row in sequence_rows]
                if any(a is None or b is None or (b - a) > max_gap_minutes * 60 for a, b in zip(times, times[1:])):
                    rejected.append({"city": city, "local_date": day_text, "reason": "sequence_gap"}); continue
            sequence = []
            for row in sequence_rows:
                sequence.append([_float(row.get(feature)) for feature in FEATURES])
            for temp_type, observed in (("high", label[1]), ("low", label[2])):
                output.append({"city": city, "local_date": day_text, "temp_type": temp_type, "decision_time_utc": decision, "label_available_ts": label[0], "observed_f": f"{observed:.6f}", "window_start_utc": rows[index - window + 1]["feature_asof_utc"], "window_end_utc": decision, "window_rows": str(window), "feature_names": json.dumps(FEATURES), "sequence_json": json.dumps(sequence, separators=(",", ":"))})
    return output, rejected


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path, required=True); parser.add_argument("--labels", type=Path, required=True); parser.add_argument("--output", type=Path, required=True); parser.add_argument("--rejections", type=Path); parser.add_argument("--window", type=int, default=12); parser.add_argument("--stride", type=int, default=1); parser.add_argument("--max-gap-minutes", type=float)
    args = parser.parse_args()
    with args.state.open(newline="") as fh: state = list(csv.DictReader(fh))
    with args.labels.open(newline="") as fh: labels = list(csv.DictReader(fh))
    rows, rejected = build(state, labels, args.window, args.stride, args.max_gap_minutes)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="") as fh: writer = csv.DictWriter(fh, fieldnames=OUT_FIELDS); writer.writeheader(); writer.writerows(rows)
    if args.rejections:
        with args.rejections.open("w", newline="") as fh: writer = csv.DictWriter(fh, fieldnames=["city", "local_date", "reason"]); writer.writeheader(); writer.writerows(rejected)
    print(f"wrote {len(rows)} sequence windows; rejected={len(rejected)}")


if __name__ == "__main__": main()

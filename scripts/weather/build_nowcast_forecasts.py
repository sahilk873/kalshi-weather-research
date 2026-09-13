"""Build PIT-safe observation-only high/low nowcast distributions."""
from __future__ import annotations

import argparse
import csv
import math
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path
from statistics import median, pstdev

_SELF = Path(__file__).resolve().parent
sys.path.insert(0, str(_SELF))
from common import parse_utc_iso  # noqa: E402

ALIASES = {"nyc": "nyc", "la": "la", "los_angeles": "la", "austin": "austin"}
OUT_FIELDS = ["event_ticker", "decision_time_utc", "forecast_issue_time", "source_receipt_time", "model_name", "model_version", "city", "temp_type", "outcome_local_date", "lead_hours", "mean_f", "stddev_f", "training_rows"]


def _num(row: dict, key: str) -> float | None:
    try:
        value = float(row.get(key, "")); return value if math.isfinite(value) else None
    except (TypeError, ValueError):
        return None


def build(state_rows: list[dict], labels: list[dict], min_training: int = 10) -> tuple[list[dict], list[dict]]:
    label_index = {}
    for row in labels:
        city = ALIASES.get(str(row.get("city", "")).strip().lower(), "")
        available = parse_utc_iso(row.get("label_available_ts"))
        try: day = date.fromisoformat(str(row.get("date", ""))); high = float(row["tmax_f"]); low = float(row["tmin_f"])
        except (KeyError, TypeError, ValueError): continue
        if city and available is not None and math.isfinite(high) and math.isfinite(low): label_index[(city, day)] = (available, high, low)
    rows = []
    for raw in state_rows:
        city = ALIASES.get(str(raw.get("city", "")).strip().lower(), "")
        feature = parse_utc_iso(raw.get("feature_asof_utc") or raw.get("valid_utc"))
        try: day = date.fromisoformat(str(raw.get("local_date", ""))); hour = int(float(raw.get("local_hour", "")))
        except (TypeError, ValueError): continue
        label = label_index.get((city, day))
        if not city or feature is None or label is None or label[0] <= feature: continue
        high = _num(raw, "observed_high_so_far_f"); low = _num(raw, "observed_low_so_far_f")
        if high is None and low is None: continue
        rows.append((feature, city, day, hour, high, low, label))
    rows.sort(key=lambda item: item[0])
    # Store completed historical residuals by group; only release them after
    # their observed label availability timestamp.
    pending = sorted(rows, key=lambda item: item[6][0]); pending_index = 0
    residuals: dict[tuple[str, str, int], list[float]] = defaultdict(list)
    residuals_broad: dict[tuple[str, str], list[float]] = defaultdict(list)
    output, rejected = [], []
    for feature, city, day, hour, high, low, label in rows:
        while pending_index < len(pending) and pending[pending_index][6][0] <= feature:
            _, pcity, pday, phour, phigh, plow, (_, pfinal_high, pfinal_low) = pending[pending_index]
            if phigh is not None: residuals[(pcity, "high", phour)].append(pfinal_high - phigh); residuals_broad[(pcity, "high")].append(pfinal_high - phigh)
            if plow is not None: residuals[(pcity, "low", phour)].append(pfinal_low - plow); residuals_broad[(pcity, "low")].append(pfinal_low - plow)
            pending_index += 1
        decision = feature.isoformat().replace("+00:00", "Z")
        for temp_type, current, final in (("high", high, label[1]), ("low", low, label[2])):
            if current is None: continue
            values = residuals[(city, temp_type, hour)]
            if len(values) < min_training: values = residuals_broad[(city, temp_type)]
            if len(values) < min_training:
                rejected.append({"city": city, "local_date": day.isoformat(), "reason": "insufficient_prior_residuals"}); continue
            center = median(values); spread = max(pstdev(values), 0.25)
            ticker = f"NOWCAST-{city}-{day.isoformat()}-{temp_type}-{feature.strftime('%Y%m%dT%H%M%SZ')}"
            lead_hours = max(0.0, (day - feature.date()).days * 24.0 + 12.0 - feature.hour)
            output.append({"event_ticker": ticker, "decision_time_utc": decision, "forecast_issue_time": decision, "source_receipt_time": decision, "model_name": "observation_nowcast", "model_version": "running_extrema_residual_v1", "city": city, "temp_type": temp_type, "outcome_local_date": day.isoformat(), "lead_hours": f"{lead_hours:.3f}", "mean_f": f"{current + center:.6f}", "stddev_f": f"{spread:.6f}", "training_rows": str(len(values))})
    return output, rejected


def evaluation_labels(forecasts: list[dict], labels: list[dict]) -> list[dict]:
    index = {}
    for row in labels:
        city = ALIASES.get(str(row.get("city", "")).strip().lower(), "")
        try:
            day = date.fromisoformat(str(row.get("date", "")))
            index[(city, day)] = (row.get("label_available_ts", ""), float(row["tmax_f"]), float(row["tmin_f"]))
        except (KeyError, TypeError, ValueError):
            continue
    output = []
    for row in forecasts:
        try: available, high, low = index[(row["city"], date.fromisoformat(row["outcome_local_date"]))]
        except (KeyError, TypeError, ValueError): continue
        output.append({"event_ticker": row["event_ticker"], "label_available_ts": available, "observed_f": f"{high if row['temp_type'] == 'high' else low:.6f}"})
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path, required=True); parser.add_argument("--labels", type=Path, required=True); parser.add_argument("--output", type=Path, required=True); parser.add_argument("--evaluation-labels", type=Path); parser.add_argument("--rejections", type=Path); parser.add_argument("--min-training", type=int, default=10)
    args = parser.parse_args()
    with args.state.open(newline="") as fh: state = list(csv.DictReader(fh))
    with args.labels.open(newline="") as fh: labels = list(csv.DictReader(fh))
    rows, rejected = build(state, labels, args.min_training)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="") as fh: writer = csv.DictWriter(fh, fieldnames=OUT_FIELDS); writer.writeheader(); writer.writerows(rows)
    if args.evaluation_labels:
        args.evaluation_labels.parent.mkdir(parents=True, exist_ok=True)
        with args.evaluation_labels.open("w", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=["event_ticker", "label_available_ts", "observed_f"]); writer.writeheader(); writer.writerows(evaluation_labels(rows, labels))
    if args.rejections:
        with args.rejections.open("w", newline="") as fh: writer = csv.DictWriter(fh, fieldnames=["city", "local_date", "reason"]); writer.writeheader(); writer.writerows(rejected)
    print(f"wrote {len(rows)} nowcast forecasts; rejected={len(rejected)}")


if __name__ == "__main__": main()

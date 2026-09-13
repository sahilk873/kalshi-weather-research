"""Score a transparent GOES cloud adjustment against an observation baseline.

This is a research diagnostic only.  It never uses market prices and does not
claim that GHCN labels reproduce a contract's licensed settlement source.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import math
from pathlib import Path


def _time(value: str) -> dt.datetime:
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))


def evaluate(cloud_path: Path, labels_path: Path, output: Path, rejections: Path,
             max_cloud_age_minutes: float = 180.0) -> tuple[int, int]:
    labels = {}
    with labels_path.open(newline="") as fh:
        for row in csv.DictReader(fh):
            labels[(row["city"], row["date"])] = row
    rows, rejected = [], []
    with cloud_path.open(newline="") as fh:
        for row in csv.DictReader(fh):
            try:
                valid = _time(row["valid_utc"])
                cloud_time = _time(row["cloud_time_utc"])
                age = float(row["cloud_age_minutes"])
                clear = float(row["dqf_clear_fraction"])
                ir_k = float(row["ir_brightness_temperature_k_mean"])
                high = float(row["observed_high_so_far_f"])
                low = float(row["observed_low_so_far_f"])
                label = labels[("lv" if row["city"] == "klas" else row["city"], row["local_date"])]
                available = _time(label["label_available_ts"])
                if cloud_time > valid:
                    raise ValueError("cloud_after_observation")
                if age < 0 or age > max_cloud_age_minutes:
                    raise ValueError("cloud_stale")
                if not (0 <= clear <= 1) or not math.isfinite(ir_k):
                    raise ValueError("invalid_cloud_value")
                if available <= valid:
                    raise ValueError("label_available_before_decision")
                # Evaluate both extrema when available; one row contributes two
                # transparent diagnostics, with no inferred settlement rule.
                ir_f = (ir_k - 273.15) * 9 / 5 + 32
                for kind, baseline, target in (("high", high, float(label["tmax_f"])),
                                               ("low", low, float(label["tmin_f"]))):
                    # Satellite adjustment is deliberately conservative: pull
                    # 10% toward the IR proxy, weighted by clear-pixel fraction.
                    augmented = baseline + 0.10 * clear * (ir_f - baseline)
                    rows.append({"city": row["city"], "station": row["station"],
                                 "local_date": row["local_date"], "valid_utc": row["valid_utc"],
                                 "kind": kind, "baseline_f": f"{baseline:.6f}",
                                 "goes_augmented_f": f"{augmented:.6f}",
                                 "target_f": f"{target:.6f}",
                                 "baseline_abs_error_f": f"{abs(baseline-target):.6f}",
                                 "goes_abs_error_f": f"{abs(augmented-target):.6f}",
                                 "cloud_age_minutes": f"{age:.3f}",
                                 "dqf_clear_fraction": f"{clear:.6f}",
                                 "feature_asof_utc": row["cloud_time_utc"]})
            except (KeyError, TypeError, ValueError) as exc:
                rejected.append({"station": row.get("station", ""),
                                 "valid_utc": row.get("valid_utc", ""),
                                 "reason": str(exc)})
    fields = list(rows[0]) if rows else ["city", "station", "local_date", "valid_utc", "kind"]
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields); writer.writeheader(); writer.writerows(rows)
    with rejections.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["station", "valid_utc", "reason"]); writer.writeheader(); writer.writerows(rejected)
    summary = output.with_name(output.stem + "_summary.csv")
    groups = {}
    for row in rows:
        key = (row["city"], row["kind"])
        bucket = groups.setdefault(key, {"n": 0, "baseline": 0.0, "goes": 0.0})
        bucket["n"] += 1; bucket["baseline"] += float(row["baseline_abs_error_f"]); bucket["goes"] += float(row["goes_abs_error_f"])
    with summary.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["city", "kind", "rows", "baseline_mae_f", "goes_augmented_mae_f"]); writer.writeheader()
        for (city, kind), b in sorted(groups.items()):
            writer.writerow({"city": city, "kind": kind, "rows": b["n"], "baseline_mae_f": f"{b['baseline']/b['n']:.6f}", "goes_augmented_mae_f": f"{b['goes']/b['n']:.6f}"})
    return len(rows), len(rejected)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cloud", type=Path, required=True)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--rejections", type=Path, required=True)
    parser.add_argument("--max-cloud-age-minutes", type=float, default=180.0)
    args = parser.parse_args()
    accepted, rejected = evaluate(args.cloud, args.labels, args.output, args.rejections, args.max_cloud_age_minutes)
    print(f"accepted_rows={accepted} rejected_rows={rejected}")


if __name__ == "__main__":
    main()

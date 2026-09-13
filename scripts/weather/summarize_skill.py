"""Aggregate monthly point-in-time skill summaries with sample weighting."""
from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path


def summarize(rows: list[dict]) -> list[dict]:
    groups = defaultdict(list)
    keys = ("model_name", "model_version", "city", "temp_type", "lead_hours")
    for row in rows:
        groups[tuple(row.get(k, "") for k in keys)].append(row)
    output = []
    for key, group in sorted(groups.items()):
        n = sum(int(row.get("eligible_predictions") or 0) for row in group)
        crps_n = sum(int(row.get("crps_predictions") or 0) for row in group)
        weighted_mae = sum(float(row.get("mae_f") or 0) * int(row.get("eligible_predictions") or 0) for row in group)
        weighted_crps = sum(float(row.get("crps_f") or 0) * int(row.get("crps_predictions") or 0) for row in group)
        output.append({**dict(zip(keys, key)), "target_months": str(len(group)),
                       "eligible_predictions": str(n),
                       "weighted_mae_f": f"{weighted_mae / n:.6f}" if n else "",
                       "crps_predictions": str(crps_n),
                       "weighted_crps_f": f"{weighted_crps / crps_n:.6f}" if crps_n else "",
                       "rejected_missing_timestamp": str(sum(int(r.get("rejected_missing_timestamp") or 0) for r in group)),
                       "rejected_target_leakage": str(sum(int(r.get("rejected_target_leakage") or 0) for r in group)),
                       "rejected_no_label_found": str(sum(int(r.get("rejected_no_label_found") or 0) for r in group)),
                       "rejected_invalid_value": str(sum(int(r.get("rejected_invalid_value") or 0) for r in group)),
                       "rejected_invalid_label": str(sum(int(r.get("rejected_invalid_label") or 0) for r in group))})
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", nargs="+", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rows = []
    for path in args.inputs:
        with path.open(newline="") as fh:
            rows.extend(csv.DictReader(fh))
    output = summarize(rows)
    fields = list(output[0]) if output else ["model_name", "model_version", "city", "temp_type", "lead_hours"]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields); writer.writeheader(); writer.writerows(output)
    print(f"wrote {len(output)} aggregate rows")


if __name__ == "__main__": main()

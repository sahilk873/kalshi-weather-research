"""Build a strict PIT dataset for any supported KXTEMP intraday city line.

This is the city-generic entry point for the existing fail-closed dataset
builder.  It deliberately keeps the same schema and rejection semantics as
the NYC implementation, while allowing LA and Austin terms/labels/features to
be audited without copying or silently changing the PIT rules.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from build_nyc_edge_dataset import build


SERIES = {
    "nyc": "kxtempnych",
    "la": "kxtemplaxh",
    "austin": "kxtempaush",
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--city", choices=sorted(SERIES), required=True)
    parser.add_argument("--root", type=Path, default=Path("data/weather_research"))
    parser.add_argument("--labels", type=Path)
    parser.add_argument("--features", type=Path)
    parser.add_argument("--feature-rejections", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--rejections-output", type=Path)
    parser.add_argument("--status-output", type=Path)
    args = parser.parse_args()

    stem = SERIES[args.city]
    terms = args.root / "kalshi_hourly" / f"{stem}_terms" / "contracts.csv"
    defaults = {
        "labels": args.root / "kalshi_hourly" / f"{stem}_terms" / "twc_labels.csv",
        "features": args.root / "reports" / f"{args.city}_intraday_features.csv",
        "feature_rejections": args.root / "reports" / f"{args.city}_intraday_feature_rejections.csv",
        "output": args.root / "reports" / f"{args.city}_edge_first_dataset.csv",
        "rejections_output": args.root / "reports" / f"{args.city}_edge_first_rejections.csv",
        "status_output": args.root / "reports" / f"{args.city}_edge_first_dataset_status.json",
    }
    paths = {key: getattr(args, key) or value for key, value in defaults.items()}
    accepted, rejected = build(terms, paths["labels"], paths["features"], paths["feature_rejections"])
    paths["output"].parent.mkdir(parents=True, exist_ok=True)
    import csv
    from build_nyc_edge_dataset import OUTPUT_FIELDS
    with paths["output"].open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_FIELDS)
        writer.writeheader(); writer.writerows(accepted)
    with paths["rejections_output"].open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["market_ticker", "reason", "reason_codes"])
        writer.writeheader(); writer.writerows(rejected)
    status = {"version": "edge-first-intraday-city-v1", "city": args.city,
              "series": stem.upper(), "contracts": len(accepted) + len(rejected),
              "accepted_rows": len(accepted), "rejected_rows": len(rejected),
              "non_empty": bool(accepted), "pass": bool(accepted),
              "rejection_reasons": {}}
    for row in rejected:
        reason = row["reason"]
        status["rejection_reasons"][reason] = status["rejection_reasons"].get(reason, 0) + 1
    paths["status_output"].write_text(json.dumps(status, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"city": args.city, "accepted": len(accepted),
                      "rejected": len(rejected), "pass": status["pass"]}))


if __name__ == "__main__":
    main()

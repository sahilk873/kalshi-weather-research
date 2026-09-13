"""Summarize an unlabeled live probability/price diagnostic.

This report intentionally contains no realized P&L: active contracts have not
settled and the input distribution is not calibrated OOS evidence.
"""
from __future__ import annotations

import argparse
import csv
import json
import statistics
from pathlib import Path


def summarize(path: Path) -> dict:
    with path.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    result = {"version": "live-price-comparison-summary-v1", "status": "diagnostic_only",
              "rows": len(rows), "settled_rows": 0, "realized_edge": None,
              "net_pnl": None, "scenarios": {},
              "reason": "active contracts are unlabeled and distribution is uncalibrated"}
    for field, label in (("yes_net_edge_conservative", "conservative"),
                         ("yes_net_edge_base", "base"),
                         ("yes_net_edge_optimistic", "optimistic")):
        values = []
        for row in rows:
            try:
                value = float(row.get(field, ""))
                if value == value:
                    values.append(value)
            except (TypeError, ValueError):
                continue
        result["scenarios"][label] = {
            "rows": len(values),
            "positive_candidates": sum(value > 0 for value in values),
            "mean_net_edge": statistics.fmean(values) if values else None,
            "min_net_edge": min(values) if values else None,
            "max_net_edge": max(values) if values else None,
        }
    result["pass"] = False
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = summarize(args.input)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"rows": result["rows"], "status": result["status"], "pass": result["pass"]}))


if __name__ == "__main__":
    main()

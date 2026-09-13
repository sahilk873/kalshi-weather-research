"""Generate PIT-gated persistence probabilities for NYC, LA, or Austin."""
from __future__ import annotations

import argparse
from pathlib import Path

from generate_edge_baseline_predictions import generate


SERIES = {"nyc": "kxtempnych", "la": "kxtemplaxh", "austin": "kxtempaush"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--city", choices=sorted(SERIES), required=True)
    parser.add_argument("--root", type=Path, default=Path("data/weather_research"))
    args = parser.parse_args()
    stem = SERIES[args.city]
    report = args.root / "reports"
    result = generate(
        report / f"{args.city}_edge_first_dataset.csv",
        args.root / "kalshi_hourly" / f"{stem}_terms" / "contracts.csv",
        report / f"{args.city}_edge_baseline_predictions.csv",
        args.root / "predictions" / f"model_version=persistence_{args.city}",
        source_index=report / "provenance_indexes" / "source_index.csv",
        observation_index=report / "provenance_indexes" / "observation_index.csv",
    )
    (report / f"{args.city}_edge_baseline_status.json").write_text(
        __import__("json").dumps(result, indent=2, sort_keys=True) + "\n"
    )
    print(__import__("json").dumps({"city": args.city, "predictions": result.get("prediction_rows", 0),
                                     "manifests": result.get("manifest_rows", 0), "pass": result["pass"]}))


if __name__ == "__main__":
    main()

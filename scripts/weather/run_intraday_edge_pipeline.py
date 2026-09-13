"""Run the fail-closed intraday probability pipeline for all three cities."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("data/weather_research"))
    parser.add_argument("--output", type=Path,
                        default=Path("data/weather_research/reports/intraday_edge_pipeline_status.json"))
    args = parser.parse_args()
    root = args.root
    statuses: dict[str, object] = {}
    readiness = root / "reports" / "intraday_city_readiness.json"
    commands = [[sys.executable, "scripts/weather/audit_intraday_city_readiness.py",
                 "--root", str(root), "--output", str(readiness)]]
    for city in ("nyc", "la", "austin"):
        commands.append([sys.executable, "scripts/weather/build_intraday_edge_dataset.py",
                         "--city", city, "--root", str(root)])
        commands.append([sys.executable, "scripts/weather/generate_intraday_baseline_predictions.py",
                         "--city", city, "--root", str(root)])
    for command in commands:
        completed = subprocess.run(command, capture_output=True, text=True, check=False)
        if completed.returncode != 0:
            raise SystemExit(f"pipeline step failed ({completed.returncode}): {' '.join(command)}\n{completed.stderr}")
    if readiness.exists():
        statuses["readiness"] = json.loads(readiness.read_text())
    reports = root / "reports"
    for city in ("nyc", "la", "austin"):
        status_path = reports / f"{city}_edge_first_dataset_status.json"
        baseline_path = reports / f"{city}_edge_baseline_status.json"
        statuses[city] = {
            "dataset": json.loads(status_path.read_text()) if status_path.exists() else None,
            "baseline": json.loads(baseline_path.read_text()) if baseline_path.exists() else None,
        }
    statuses["version"] = "intraday-edge-pipeline-v1"
    statuses["pass"] = bool(statuses.get("readiness", {}).get("pass")) and all(
        bool(statuses.get(city, {}).get("dataset", {}).get("pass")) for city in ("nyc", "la", "austin")
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(statuses, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"output": str(args.output), "pass": statuses["pass"]}))


if __name__ == "__main__":
    main()

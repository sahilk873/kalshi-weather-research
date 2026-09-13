"""Ingest conservative execution rows into the research paper ledger.

The runner is intentionally transport-agnostic: a scheduler or upstream
collector refreshes the execution CSV, while this process validates the
manifest and appends only unseen hypothetical order/fill records.  It has no
broker, exchange, or order-placement integration.
"""
from __future__ import annotations

import argparse
import csv
import json
import time
from pathlib import Path

from paper_trading_ledger import append_records, from_execution_rows
from prediction_manifest import validate_manifest


def _existing_ids(path: Path) -> set[str]:
    if not path.exists():
        return set()
    ids = set()
    for line in path.read_text().splitlines():
        if line.strip():
            payload = json.loads(line)
            ids.add(str(payload.get("record_id", "")))
    return ids


def ingest_once(execution: Path, manifest: Path, output: Path) -> int:
    payload = json.loads(manifest.read_text())
    if not isinstance(payload, dict):
        raise ValueError("manifest must be a JSON object")
    errors = validate_manifest(payload)
    if errors:
        raise ValueError("manifest failed validation: " + "; ".join(errors))
    with execution.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    records = from_execution_rows(rows, str(manifest))
    existing = _existing_ids(output)
    fresh = [record for record in records if str(record["record_id"]) not in existing]
    return append_records(output, fresh, {str(manifest)})


def run(execution: Path, manifest: Path, output: Path, *, iterations: int = 1,
        interval_seconds: float = 60.0) -> int:
    if iterations < 0:
        raise ValueError("iterations must be non-negative")
    total = 0; completed = 0
    while iterations == 0 or completed < iterations:
        total += ingest_once(execution, manifest, output)
        completed += 1
        if iterations == 0 or completed < iterations:
            time.sleep(min(60.0, max(0.0, interval_seconds)))
    return total


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execution", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--iterations", type=int, default=1, help="0 means continuous")
    parser.add_argument("--interval-seconds", type=float, default=60.0)
    args = parser.parse_args()
    count = run(args.execution, args.manifest, args.output, iterations=args.iterations,
                interval_seconds=args.interval_seconds)
    print(json.dumps({"appended": count, "output": str(args.output)}))


if __name__ == "__main__":
    main()

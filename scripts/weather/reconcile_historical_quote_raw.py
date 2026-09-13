"""Index raw quote payloads left by an interrupted historical crawl.

This never promotes an orphan payload to executable evidence. It records the
payload hash and filesystem receipt upper bound in a quarantine manifest so a
rate-limited/interrupted batch is auditable and cannot be mistaken for a
complete collection.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


def reconcile(root: Path, reason: str = "interrupted_rate_limited_batch") -> dict:
    raw = root / "raw"
    indexed_path = root / "raw_manifest.jsonl"
    quarantine_path = root / "raw_quarantine_manifest.jsonl"
    indexed = set()
    if indexed_path.exists():
        for line in indexed_path.read_text().splitlines():
            if line.strip():
                try:
                    indexed.add(str(Path(json.loads(line).get("raw_path", "")).resolve()))
                except (ValueError, TypeError, OSError):
                    continue
    quarantined = {}
    if quarantine_path.exists():
        for line in quarantine_path.read_text().splitlines():
            if line.strip():
                try:
                    row = json.loads(line)
                    quarantined[str(Path(row.get("raw_path", "")).resolve())] = row
                except (ValueError, TypeError, OSError):
                    continue
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    for path in sorted(raw.glob("*.json")):
        resolved = str(path.resolve())
        if resolved in indexed or resolved in quarantined:
            continue
        payload = path.read_bytes()
        quarantined[resolved] = {
            "raw_path": str(path),
            "sha256": hashlib.sha256(payload.rstrip(b"\n")).hexdigest(),
            "observed_at_utc": now,
            "filesystem_mtime_utc": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat().replace("+00:00", "Z"),
            "reason": reason,
            "status": "quarantined",
        }
    with quarantine_path.open("w") as handle:
        for row in sorted(quarantined.values(), key=lambda value: value["raw_path"]):
            handle.write(json.dumps(row, sort_keys=True) + "\n")
    return {"indexed": len(indexed), "quarantined": len(quarantined), "path": str(quarantine_path), "reason": reason}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("data/weather_research/kalshi_hourly/historical_quotes"))
    args = parser.parse_args()
    print(json.dumps(reconcile(args.root), sort_keys=True))


if __name__ == "__main__":
    main()

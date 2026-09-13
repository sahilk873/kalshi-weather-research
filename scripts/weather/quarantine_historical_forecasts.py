"""Record unavailable historical forecast responses without treating them as data."""
from __future__ import annotations

import argparse, csv, hashlib, json
from pathlib import Path


def build(manifest: Path, root: Path, reason: str = "provider_returned_no_non_null_forecast_values") -> list[dict]:
    rows = []
    with manifest.open(newline="") as handle:
        for row in csv.DictReader(handle):
            relative = Path(row["raw_path"])
            if relative.is_absolute() or ".." in relative.parts:
                continue
            path = root / relative
            if not path.exists():
                continue
            try:
                payload = json.loads(path.read_text())
                hourly = (payload.get("hourly") or {}) if isinstance(payload, dict) else {}
                values = [v for key, vals in hourly.items() if key != "time" for v in vals if v is not None]
            except (OSError, ValueError, TypeError):
                continue
            if not values:
                rows.append({"raw_path": row["raw_path"], "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "reason": reason, "reviewed": "true"})
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=Path("data/weather_research/gefs/historical_raw/manifest.csv"))
    parser.add_argument("--root", type=Path, default=Path("data/weather_research"))
    parser.add_argument("--output", type=Path, default=Path("data/weather_research/gefs/historical_raw/quarantine.csv"))
    args = parser.parse_args(); rows = build(args.manifest, args.root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["raw_path", "sha256", "reason", "reviewed"]); writer.writeheader(); writer.writerows(rows)
    print(f"quarantined={len(rows)}")


if __name__ == "__main__": main()

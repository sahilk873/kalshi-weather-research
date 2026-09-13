"""Archive the latest NOAA NOMADS LAMP station bulletin for PIT research."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

BASE = "https://nomads.ncep.noaa.gov/pub/data/nccf/com/lmp/prod"
DIR_RE = re.compile(r'href="(lmp\.\d{8}/)"')
FILE_RE = re.compile(r'href="(lmp\.t\d{4}z\.lavtxt\.ascii)"')


def _get(url: str) -> bytes:
    with urlopen(Request(url, headers={"User-Agent": "kalshi-weather-research/1.0"}), timeout=60) as response:
        return response.read()


def collect(output: Path) -> dict:
    index = _get(BASE + "/").decode("utf-8", errors="replace")
    directories = sorted(DIR_RE.findall(index))
    if not directories:
        raise RuntimeError("NOMADS LAMP product directory is unavailable")
    directory = directories[-1]
    listing_url = BASE + "/" + directory
    listing = _get(listing_url).decode("utf-8", errors="replace")
    files = sorted(FILE_RE.findall(listing))
    if not files:
        raise RuntimeError(f"no LAMP ASCII cycle found in {listing_url}")
    filename = files[-1]
    source_url = listing_url + filename
    payload = _get(source_url)
    receipt = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    digest = hashlib.sha256(payload).hexdigest()
    output.mkdir(parents=True, exist_ok=True)
    raw_path = output / filename
    raw_path.write_bytes(payload)
    snapshot = {"retrieved_at_utc": receipt, "source_url": source_url,
                "raw_path": str(raw_path), "sha256": digest,
                "bytes": len(payload), "cycle_file": filename}
    manifest_path = output / "manifest.json"
    history = []
    if manifest_path.exists():
        try:
            old = json.loads(manifest_path.read_text())
            history = old.get("snapshots", [])
            if not history and old.get("retrieved_at_utc"):
                history = [old]
        except (OSError, ValueError, TypeError):
            history = []
    if not any(item.get("raw_sha256", item.get("sha256")) == digest and item.get("raw_path") == str(raw_path) for item in history):
        history.append(snapshot)
    manifest = {"snapshots": history, "latest": snapshot}
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return snapshot


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("data/weather_research/lamp"))
    args = parser.parse_args()
    print(json.dumps(collect(args.output), sort_keys=True))


if __name__ == "__main__":
    main()

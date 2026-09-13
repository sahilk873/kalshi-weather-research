"""Archive the latest NOAA GLMP 2-m temperature GRIB2 guidance object."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

BASE = "https://nomads.ncep.noaa.gov/pub/data/nccf/com/glmp/prod"
DIR_RE = re.compile(r'href="(glmp\.\d{8}/)"')
FILE_RE = re.compile(r'href="(glmp\.t\d{4}z\.fcsts_t\.g\.co\.grib2)"')


def _get(url: str) -> bytes:
    with urlopen(Request(url, headers={"User-Agent": "kalshi-weather-research/1.0"}), timeout=120) as response:
        return response.read()


def collect(output: Path) -> dict:
    index = _get(BASE + "/").decode("utf-8", errors="replace")
    directories = sorted(DIR_RE.findall(index))
    if not directories: raise RuntimeError("NOMADS GLMP product directory is unavailable")
    listing_url = ""; files = []
    for directory in reversed(directories):
        listing_url = BASE + "/" + directory
        listing = _get(listing_url).decode("utf-8", errors="replace")
        files = sorted(FILE_RE.findall(listing))
        if files: break
    if not files: raise RuntimeError("no GLMP temperature product found in available directories")
    filename = files[-1]; source_url = listing_url + filename; payload = _get(source_url)
    if payload[:4] != b"GRIB" or len(payload) < 16:
        raise RuntimeError(f"GLMP response is not a valid GRIB payload: {source_url}")
    receipt = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    digest = hashlib.sha256(payload).hexdigest(); output.mkdir(parents=True, exist_ok=True)
    raw_path = output / filename; raw_path.write_bytes(payload)
    cycle = re.search(r"glmp\.t(\d{4})z", filename)
    run_date = re.search(r"glmp\.(\d{8})/", source_url)
    init = datetime.strptime(run_date.group(1) + cycle.group(1), "%Y%m%d%H%M").replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z") if cycle and run_date else ""
    snapshot = {"model": "GLMP", "initialization_time_utc": init,
                "retrieved_at_utc": receipt, "source_url": source_url,
                "raw_path": str(raw_path), "sha256": digest,
                "bytes": len(payload), "cycle_file": filename}
    manifest_path = output / "manifest.json"; history = []
    if manifest_path.exists():
        try:
            old = json.loads(manifest_path.read_text()); history = old.get("snapshots", [])
            if not history and old.get("retrieved_at_utc"): history = [old]
        except (OSError, ValueError, TypeError): history = []
    for old in history:
        if old.get("initialization_time_utc"):
            continue
        old_cycle = re.search(r"glmp\.t(\d{4})z", old.get("cycle_file", old.get("source_url", "")))
        old_date = re.search(r"glmp\.(\d{8})", old.get("source_url", ""))
        if old_cycle and old_date:
            old["model"] = "GLMP"
            old["initialization_time_utc"] = datetime.strptime(old_date.group(1) + old_cycle.group(1), "%Y%m%d%H%M").replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")
    if not any(item.get("sha256") == digest and item.get("raw_path") == str(raw_path) for item in history): history.append(snapshot)
    manifest_path.write_text(json.dumps({"snapshots": history, "latest": snapshot}, indent=2, sort_keys=True) + "\n")
    return snapshot


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("data/weather_research/glmp"))
    args = parser.parse_args(); print(json.dumps(collect(args.output), sort_keys=True))


if __name__ == "__main__": main()

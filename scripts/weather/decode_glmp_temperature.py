"""Decode GLMP 2-m temperature GRIB2 to point features with PIT metadata."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

CITY_COORDS = {"nyc": (40.7789, -73.9692), "phx": (33.4343, -112.0116),
               "lv": (36.0719, -115.1633), "la": (33.9382, -118.3886),
               "austin": (30.1945, -97.6699)}
FIELDS = ["model", "city", "initialization_time_utc", "valid_time_utc",
          "lead_hours", "source_receipt_time", "variable", "value", "unit",
          "grid_latitude", "grid_longitude", "raw_path", "sha256",
          "message_index"]


def _utc_from_grib(date: int, time: int) -> str:
    return datetime.strptime(f"{date:08d}{time:04d}", "%Y%m%d%H%M").replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")


def _resolve_raw_path(manifest_path: Path, raw_path: str) -> Path:
    """Resolve manifest paths from either repo-root or manifest-relative runs."""
    candidate = Path(raw_path)
    if candidate.exists():
        return candidate
    # Manifests commonly store a repository-relative data/... path.  Resolve
    # that path from the repository root even when called outside the repo.
    repo_root = Path(__file__).resolve().parents[2]
    candidate = repo_root / raw_path
    if candidate.exists():
        return candidate
    candidate = manifest_path.parent / Path(raw_path).name
    return candidate


def decode(manifest_path: Path, output_path: Path, cities: set[str] | None = None) -> int:
    try:
        from eccodes import (codes_get, codes_grib_find_nearest,
                             codes_grib_new_from_file, codes_release)
    except ImportError as exc:
        raise RuntimeError("eccodes is required for GLMP decoding") from exc
    payload = json.loads(manifest_path.read_text())
    snapshots = payload.get("snapshots", []) or [payload.get("latest", payload)]
    rows = []
    for meta in snapshots:
        path = _resolve_raw_path(manifest_path, meta["raw_path"])
        if not path.exists(): raise FileNotFoundError(path)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != meta.get("sha256"): raise ValueError(f"raw hash mismatch: {path}")
        selected = cities or {"nyc"}
        with path.open("rb") as handle:
            index = 0
            while (gid := codes_grib_new_from_file(handle)) is not None:
                index += 1
                try:
                    if codes_get(gid, "shortName") != "2t": continue
                    valid = _utc_from_grib(codes_get(gid, "validityDate"), codes_get(gid, "validityTime"))
                    lead = int(codes_get(gid, "forecastTime"))
                    for city in sorted(selected):
                        if city not in CITY_COORDS: continue
                        nearest = codes_grib_find_nearest(gid, *CITY_COORDS[city])[0]
                        value_f = (float(nearest["value"]) - 273.15) * 9 / 5 + 32
                        lon = float(nearest["lon"]); lon = lon - 360 if lon > 180 else lon
                        rows.append({"model": "GLMP", "city": city,
                                     "initialization_time_utc": meta["initialization_time_utc"],
                                     "valid_time_utc": valid, "lead_hours": lead,
                                     "source_receipt_time": meta["retrieved_at_utc"],
                                     "variable": "temperature_2m", "value": f"{value_f:.8f}", "unit": "F",
                                     "grid_latitude": f"{float(nearest['lat']):.8f}",
                                     "grid_longitude": f"{lon:.8f}", "raw_path": str(path),
                                     "sha256": digest, "message_index": index})
                finally:
                    codes_release(gid)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS); writer.writeheader(); writer.writerows(rows)
    return len(rows)


def main() -> None:
    root = Path(__file__).resolve().parents[2] / "data" / "weather_research"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=root / "glmp" / "manifest.json")
    parser.add_argument("--output", type=Path, default=root / "glmp" / "point_features.csv")
    parser.add_argument("--cities", nargs="*", choices=sorted(CITY_COORDS), default=["nyc"])
    args = parser.parse_args()
    print(f"wrote {decode(args.manifest, args.output, set(args.cities))} GLMP point rows")


if __name__ == "__main__": main()

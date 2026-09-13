"""Decode RTMA 2-D analysis values at registered station points."""
from __future__ import annotations
import argparse, csv, hashlib
from pathlib import Path

STATIONS = {"phx": (33.4343, -112.0116), "klas": (36.0719, -115.1633), "nyc": (40.7789, -73.9692), "la": (33.9382, -118.3886), "austin": (30.1945, -97.6699)}
KEEP = {"2t": ("temperature_2m", "K"), "2d": ("dewpoint_2m", "K"), "10u": ("wind_u_10m", "m/s"), "10v": ("wind_v_10m", "m/s"), "tcc": ("cloud_cover", "%"), "vis": ("visibility", "m")}

def decode(path: Path, output: Path, cities: list[str]) -> int:
    from eccodes import codes_get, codes_grib_find_nearest, codes_grib_new_from_file, codes_release
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    rows = []
    with path.open("rb") as fh:
        while (gid := codes_grib_new_from_file(fh)) is not None:
            try:
                short = codes_get(gid, "shortName")
                if short not in KEEP: continue
                name, unit = KEEP[short]
                valid = f"{codes_get(gid, 'dataDate'):08d}{codes_get(gid, 'dataTime'):04d}"
                valid_iso = valid[:4] + "-" + valid[4:6] + "-" + valid[6:8] + "T" + valid[8:10] + ":" + valid[10:12] + ":00Z"
                for city in cities:
                    nearest = codes_grib_find_nearest(gid, *STATIONS[city])[0]
                    lon = float(nearest["lon"])
                    if lon > 180: lon -= 360
                    rows.append({"city": city, "variable": name, "value": f"{float(nearest['value']):.8f}", "unit": unit, "valid_time_utc": valid_iso, "grid_latitude": f"{nearest['lat']:.8f}", "grid_longitude": f"{lon:.8f}", "raw_path": str(path), "sha256": digest})
            finally: codes_release(gid)
    output.parent.mkdir(parents=True, exist_ok=True)
    fields = ["city", "variable", "value", "unit", "valid_time_utc", "grid_latitude", "grid_longitude", "raw_path", "sha256"]
    with output.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields); w.writeheader(); w.writerows(rows)
    return len(rows)

def main() -> None:
    p = argparse.ArgumentParser(); p.add_argument("--input", type=Path, required=True); p.add_argument("--output", type=Path, required=True); p.add_argument("--cities", nargs="+", choices=sorted(STATIONS), default=list(STATIONS)); a = p.parse_args()
    print(f"wrote {decode(a.input, a.output, a.cities)} RTMA point rows")
if __name__ == "__main__": main()

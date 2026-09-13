"""Extract a small, auditable GOES ABI infrared cloud proxy at station points."""
from __future__ import annotations
import argparse, csv, hashlib
from datetime import datetime, timezone
from pathlib import Path
import math

STATIONS = {"phx": (33.4343, -112.0116), "klas": (36.0719, -115.1633), "nyc": (40.7789, -73.9692), "la": (33.9382, -118.3886), "austin": (30.1945, -97.6699)}

def _pixel(lat: float, lon: float, projection) -> tuple[float, float]:
    lat = math.radians(lat); lon = math.radians(lon); lon0 = math.radians(float(projection.attrs["longitude_of_projection_origin"]))
    req = float(projection.attrs["semi_major_axis"]); rpol = float(projection.attrs["semi_minor_axis"]); h = float(projection.attrs["perspective_point_height"]) + req
    e2 = 1.0 - (rpol * rpol) / (req * req); rlat = rpol / math.sqrt(1.0 - e2 * math.cos(lat) ** 2); dl = lon - lon0
    r1 = h - rlat * math.cos(lat) * math.cos(dl); r2 = -rlat * math.cos(lat) * math.sin(dl); r3 = rlat * math.sin(lat)
    return math.atan(-r2 / r1), math.atan(r3 / math.sqrt(r1 * r1 + r2 * r2))

def extract(paths: list[Path], output: Path, stations: list[str]) -> int:
    try:
        import xarray as xr
    except ImportError as exc:
        raise RuntimeError("xarray and netCDF4 are required; install them in the optional GOES environment") from exc
    out = []
    for path in paths:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        ds = xr.open_dataset(path, engine="netcdf4")
        try:
            projection = ds["goes_imager_projection"]; xs = ds["x"].values; ys = ds["y"].values
            cmi = ds["CMI_C13"].values; dqf = ds["DQF_C13"].values
            timestamp = str(ds.attrs.get("time_coverage_start", ""))
            for station in stations:
                lat, lon = STATIONS[station]; px, py = _pixel(lat, lon, projection)
                ix = int(abs(xs - px).argmin()); iy = int(abs(ys - py).argmin()); y0, y1 = max(0, iy - 1), min(len(ys), iy + 2); x0, x1 = max(0, ix - 1), min(len(xs), ix + 2)
                values = [float(v) for v in cmi[y0:y1, x0:x1].ravel() if math.isfinite(float(v))]
                quality = [int(v) for v in dqf[y0:y1, x0:x1].ravel()]
                good = sum(v == 0 for v in quality)
                out.append({"station": station, "latitude": lat, "longitude": lon, "source_file": str(path), "source_sha256": digest, "time_coverage_start": timestamp, "pixel_x": px, "pixel_y": py, "window_rows": len(values), "dqf_clear_fraction": f"{good / len(quality):.6f}" if quality else "", "ir_brightness_temperature_k_mean": f"{sum(values) / len(values):.6f}" if values else ""})
        finally:
            ds.close()
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(out[0]) if out else ["station"]); writer.writeheader(); writer.writerows(out)
    return len(out)

def main() -> None:
    p = argparse.ArgumentParser(description=__doc__); p.add_argument("--input", nargs="+", type=Path, required=True); p.add_argument("--output", type=Path, required=True); p.add_argument("--stations", nargs="+", choices=sorted(STATIONS), default=["phx", "klas"]); a = p.parse_args(); print(f"wrote {extract(a.input, a.output, a.stations)} GOES station features")

if __name__ == "__main__": main()

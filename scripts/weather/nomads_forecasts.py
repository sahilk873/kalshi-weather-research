"""Download small, point-in-time HRRR/NBM GRIB2 subsets from NOAA NOMADS.

Raw filtered GRIB2 files are immutable evidence. Decoding is optional and
requires eccodes (preferred) or wgrib2; values are never synthesized.
"""
from __future__ import annotations
import argparse, csv, hashlib, shutil, subprocess, sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2] / "data" / "weather_research" / "forecasts"
BBOX = {"phx": (36.5, -115.5, -111.5, 33.0), "klas": (38.5, -117.5, -113.0, 34.0)}
VARS = {"hrrr": [("TMP", "lev_2_m_above_ground"), ("DPT", "lev_2_m_above_ground"), ("UGRD", "lev_10_m_above_ground"), ("VGRD", "lev_10_m_above_ground"), ("APCP", "lev_surface"), ("PRES", "lev_surface"), ("TCDC", "lev_entire_atmosphere"), ("DSWRF", "lev_surface")], "nbm": [("TMP", "lev_2_m_above_ground"), ("DPT", "lev_2_m_above_ground"), ("WIND", "lev_10_m_above_ground"), ("WDIR", "lev_10_m_above_ground"), ("APCP", "lev_surface"), ("TCDC", "lev_entire_atmosphere"), ("TMAX", "lev_2_m_above_ground"), ("TMIN", "lev_2_m_above_ground")]}

def iso(dt): return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
def url_for(model, init, lead, city):
    top, left, right, bottom = BBOX[city]; d, h = init.strftime("%Y%m%d"), init.strftime("%H")
    if model == "hrrr":
        endpoint = "https://nomads.ncep.noaa.gov/cgi-bin/filter_hrrr_2d.pl"
        fn = f"hrrr.t{h}z.wrfsfcf{lead:02d}.grib2"; directory = f"/hrrr.{d}/conus"
    else:
        endpoint = "https://nomads.ncep.noaa.gov/cgi-bin/filter_blend.pl"
        fn = f"blend.t{h}z.core.f{lead:03d}.co.grib2"; directory = f"/blend.{d}/{h}/core"
    q = {"dir": directory, "file": fn, "subregion": "", "toplat": top, "leftlon": left, "rightlon": right, "bottomlat": bottom}
    for var, lev in VARS[model]: q[f"var_{var}"] = "on"; q[lev] = "on"
    return endpoint + "?" + urlencode(q)

def existing_keys():
    mp = ROOT / "manifest.csv"
    if not mp.exists():
        return {}
    def _led(r):
        try:
            return int(r["lead_hours"])
        except (ValueError, TypeError):
            return r["lead_hours"]
    with mp.open(newline="") as f:
        return {(r["model"], r["city"], r["initialization_time_utc"], _led(r)): r["sha256"]
                for r in csv.DictReader(f)}

def download(model, init, lead, city, max_bytes=80_000_000):
    out = ROOT / "raw" / model; out.mkdir(parents=True, exist_ok=True)
    path = out / f"{model}_{city}_{init:%Y%m%dT%HZ}_f{lead:03d}.grib2"
    uri = url_for(model, init, lead, city)
    if path.exists(): data = path.read_bytes()
    else:
        with urlopen(Request(uri, headers={"User-Agent": "kalshi-weather-research/1.0"}), timeout=180) as r: data = r.read(max_bytes + 1)
        if len(data) > max_bytes: raise RuntimeError("filtered GRIB exceeds --max-bytes")
        path.write_bytes(data)
    row = {"model": model, "city": city, "initialization_time_utc": iso(init), "valid_time_utc": iso(init + timedelta(hours=lead)), "lead_hours": lead, "station_lat": 33.4343 if city == "phx" else 36.0719, "station_lon": -112.0116 if city == "phx" else -115.1633, "request_url": uri, "raw_path": str(path.relative_to(ROOT)), "sha256": hashlib.sha256(data).hexdigest(), "ingested_at_utc": iso(datetime.now(timezone.utc))}
    key = (row["model"], row["city"], row["initialization_time_utc"], row["lead_hours"])
    seen = existing_keys()
    if key in seen:
        if seen[key] != row["sha256"]:
            print(f"  WARNING: {key} exists with differing sha256 in "
                  f"manifest.csv; raw file {row['raw_path']} left untouched, "
                  f"no manifest row appended", file=sys.stderr)
        return row
    mp = ROOT / "manifest.csv"; fields = list(row)
    exists = mp.exists()
    with mp.open("a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields); (w.writeheader() if not exists else None); w.writerow(row)
    return row

def decode(path):
    """Return parsed messages using eccodes, or raise an actionable error."""
    try:
        import eccodes
    except ImportError:
        if not shutil.which("wgrib2"): raise RuntimeError("No GRIB decoder installed. Install python-eccodes (recommended), cfgrib+xarray, or wgrib2.")
        return subprocess.check_output(["wgrib2", str(path), "-s"], text=True)
    rows = []
    with open(path, "rb") as f:
        while (gid := eccodes.codes_grib_new_from_file(f)) is not None:
            rows.append({"short_name": eccodes.codes_get(gid, "shortName"), "level": eccodes.codes_get(gid, "level"), "valid_time_utc": eccodes.codes_get(gid, "validityDate"), "values": eccodes.codes_get_array(gid, "values").tolist()})
            eccodes.codes_release(gid)
    return rows

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--model", choices=["hrrr", "nbm"], required=True)
    ap.add_argument("--init", help="single UTC run, ISO timestamp")
    ap.add_argument("--start", help="archive start UTC date (inclusive)"); ap.add_argument("--end", help="archive end UTC date (inclusive)")
    ap.add_argument("--run-hours", nargs="+", type=int, default=[0,6,12,18]); ap.add_argument("--leads", nargs="+", type=int, default=[0,1,2]); ap.add_argument("--cities", nargs="+", choices=list(BBOX), default=list(BBOX)); ap.add_argument("--max-requests", type=int, default=100); ap.add_argument("--decode", action="store_true"); args = ap.parse_args()
    if not args.init and not (args.start and args.end): ap.error("provide --init or both --start and --end")
    if args.init: inits = [datetime.fromisoformat(args.init.replace("Z", "+00:00"))]
    else:
        s = datetime.fromisoformat(args.start).replace(tzinfo=timezone.utc); e = datetime.fromisoformat(args.end).replace(tzinfo=timezone.utc); inits = [d.replace(hour=h) for d in (s + timedelta(days=i) for i in range((e-s).days+1)) for h in args.run_hours]
    total = len(inits) * len(args.leads) * len(args.cities)
    if total > args.max_requests: ap.error(f"{total} requests exceed --max-requests {args.max_requests}")
    for init in inits:
        for city in args.cities:
            for lead in args.leads:
                row = download(args.model, init, lead, city); print(row["raw_path"])
                if args.decode: print(decode(ROOT / row["raw_path"]))
if __name__ == "__main__": main()

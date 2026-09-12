"""Nearby station discovery for Phoenix and Las Vegas.

Two complementary station registries:

1. GHCN-Daily station inventory (NCEI):
   - https://www.ncei.noaa.gov/pub/data/ghcn/daily/ghcnd-stations.txt
   - https://www.ncei.noaa.gov/pub/data/ghcn/daily/ghcnd-inventory.txt
   We select stations within ``--radius`` km that carry TMAX or TMIN.

2. IEM ASOS networks (Iowa Environmental Mesonet):
   - https://mesonet.agron.iastate.edu/geojson/network/AZ_ASOS.geojson
   - https://mesonet.agron.iastate.edu/geojson/network/NV_ASOS.geojson
   Attributes include sid, sname, ncei91 (=GHCN id link), tzname,
   archive_begin/end, elevation.

Outputs (data/weather_research/stations/):
- ghcn_nearby_stations.csv
- asos_nearby_stations.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path

_SELF = Path(__file__).resolve().parent
sys.path.insert(0, str(_SELF))

# ruff: noqa: E402
import common  # noqa: E402
from common import ensure_runtime_dirs, http_get, http_get_text, utcnow  # noqa: E402
from stations import (DEFAULT_CITIES, GHCN_INVENTORY_URL,  # noqa: E402
                      GHCN_STATIONS_URL, IEM_NETWORK_GEOJSON, get_cities)

EARTH_RADIUS_KM = 6371.0088


def haversine_km(lat1, lon1, lat2, lon2) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def fetch_cached(url: str, dest: Path) -> Path:
    if dest.exists() and dest.stat().st_size > 0:
        print(f"  cache hit  {dest}")
    else:
        print(f"  fetching  {url}")
        dest.write_bytes(http_get(url, timeout=180))
    return dest


def parse_stations_txt(path: Path) -> list[dict]:
    out = []
    for line in path.read_text(errors="replace").splitlines():
        parts = line.split()
        if len(parts) < 6:
            continue
        try:
            out.append({
                "station_id": parts[0],
                "lat": float(parts[1]),
                "lon": float(parts[2]),
                "elevation_m": float(parts[3]),
                "state": parts[4],
                "name": " ".join(parts[5:]),
            })
        except ValueError:
            continue
    return out


def parse_inventory(path: Path) -> dict[str, dict]:
    """station_id -> {TMAX: (y1,y2), TMIN: (y1,y2)}

    ghcnd-inventory.txt columns: ID  lat  lon  ELEMENT  FIRST_YEAR  LAST_YEAR
    """
    inv: dict[str, dict] = {}
    for line in path.read_text(errors="replace").splitlines():
        parts = line.split()
        if len(parts) != 6:
            continue
        sid, _lat, _lon, element, y1, y2 = parts
        if element not in ("TMAX", "TMIN"):
            continue
        inv.setdefault(sid, {})[element] = (int(y1), int(y2))
    return inv


def iem_network_stations(network: str, dirs) -> list[dict]:
    url = IEM_NETWORK_GEOJSON.format(network=network)
    dest = dirs["stations_out"] / f"iem_{network}.geojson"
    if not (dest.exists() and dest.stat().st_size > 0):
        print(f"  fetching  {url}")
        dest.write_bytes(http_get(url, timeout=120))
    data = json.loads(dest.read_text())
    out = []
    for f in data.get("features") or []:
        props = f.get("properties") or {}
        geo = f.get("geometry") or {}
        coords = geo.get("coordinates") or [None, None]
        out.append({
            "sid": props.get("sid"),
            "sname": props.get("sname"),
            "state": props.get("state"),
            "network": props.get("network"),
            "lat": coords[1],
            "lon": coords[0],
            "elevation_m": props.get("elevation"),
            "tzname": props.get("tzname"),
            "archive_begin": props.get("archive_begin"),
            "archive_end": props.get("archive_end"),
            "ncei91": props.get("ncei91"),
            "climate_site": props.get("climate_site"),
            "wmo": props.get("wmo"),
            "online": props.get("online"),
        })
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cities", nargs="*", default=None)
    ap.add_argument("--radius", type=float, default=75.0,
                    help="search radius in km (default 75)")
    args = ap.parse_args()

    dirs = ensure_runtime_dirs()
    cities = get_cities(args.cities or DEFAULT_CITIES)

    stations_file = fetch_cached(
        GHCN_STATIONS_URL, dirs["stations_out"] / "ghcnd-stations.txt")
    inventory_file = fetch_cached(
        GHCN_INVENTORY_URL, dirs["stations_out"] / "ghcnd-inventory.txt")
    stations = parse_stations_txt(stations_file)
    inventory = parse_inventory(inventory_file)

    rows = []
    for s in stations:
        if s["station_id"] not in inventory:
            continue
        if not inventory[s["station_id"]]:
            continue
        for city in cities:
            km = haversine_km(city.lat, city.lon, s["lat"], s["lon"])
            if km <= args.radius:
                inv = inventory[s["station_id"]]
                rows.append({
                    "city": city.key,
                    "distance_km": round(km, 2),
                    "station_id": s["station_id"],
                    "name": s["name"].strip(),
                    "state": s["state"],
                    "lat": s["lat"],
                    "lon": s["lon"],
                    "elevation_m": s["elevation_m"],
                    "tmax_range": str(inv.get("TMAX")),
                    "tmin_range": str(inv.get("TMIN")),
                })
    rows.sort(key=lambda r: (r["city"], r["distance_km"]))
    ghcn_out = dirs["stations_out"] / "ghcn_nearby_stations.csv"
    with ghcn_out.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()) if rows else
                                ["city"] + [])
        if rows:
            writer.writeheader()
            writer.writerows(rows)
    print(f"wrote {ghcn_out} ({len(rows)} GHCN stations within {args.radius} km)")

    asos_rows = []
    for city in cities:
        net = iem_network_stations(city.iem_network, dirs)
        for s in net:
            if s["lat"] is None:
                continue
            km = haversine_km(city.lat, city.lon, s["lat"], s["lon"])
            if km <= args.radius:
                asos_rows.append({
                    "city": city.key,
                    "distance_km": round(km, 2),
                    "sid": s["sid"],
                    "sname": s["sname"],
                    "state": s["state"],
                    "lat": s["lat"],
                    "lon": s["lon"],
                    "elevation_m": s["elevation_m"],
                    "tzname": s["tzname"],
                    "archive_begin": s["archive_begin"],
                    "archive_end": s["archive_end"],
                    "ncei91": s["ncei91"],
                    "online": s["online"],
                })
    asos_rows.sort(key=lambda r: (r["city"], r["distance_km"]))
    asos_out = dirs["stations_out"] / "asos_nearby_stations.csv"
    with asos_out.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(asos_rows[0].keys()) if asos_rows
                                else [])
        if asos_rows:
            writer.writeheader()
            writer.writerows(asos_rows)
    print(f"wrote {asos_out} ({len(asos_rows)} ASOS stations within {args.radius} km)")
    print(f"fetched_at={utcnow()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
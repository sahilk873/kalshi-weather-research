"""GHCN-Daily climate labels (NCEI) for Phoenix and Las Vegas.

What this fetches / normalizes:
- Per-station GHCN-Daily ".dly" files (static public files, no token needed):
    https://www.ncei.noaa.gov/pub/data/ghcn/daily/all/USW00023183.dly  (PHX)
    https://www.ncei.noaa.gov/pub/data/ghcn/daily/all/USW00023169.dly  (LAS)
- Daily TMAX / TMIN are NOAA's final daily extremes at the airport observation
  sites. They are a validation label, not a replacement for an event-specific
  Kalshi settlement source (some current events use The Weather Company).
- Station metadata from ghcnd-stations.txt.

Outputs:
- data/raw_ghcn/USW00023183.dly         (raw static file, cached)
- data/raw_ghcn/ghcnd-stations.txt      (inventory, cached)
- data/weather_research/ghcn/labels_daily.csv

.dly layout: ID(11) YEAR(4) MONTH(2) ELEMENT(4) then 31 x
[VALUE(5) MFLAG(1) QFLAG(1) SFLAG(1)]. TMAX/TMIN are in tenths of degrees
Celsius; -9999 = missing.

Anti-lookahead:
GHCN-Daily is refreshed ~once per day; the official extreme for climate day D
is not observable until it is published. We store a deliberately conservative
synthetic label_available_ts = D+36h; it is not an observed publication time.
Downstream joins must restrict on label_available_ts <= market timestamp.
"""

from __future__ import annotations

import argparse
import csv
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

_SELF = Path(__file__).resolve().parent
sys.path.insert(0, str(_SELF))

# ruff: noqa: E402
from common import ensure_runtime_dirs, http_get, http_get_text, utcnow  # noqa: E402
from stations import (CITIES, DEFAULT_CITIES, GHCN_ALL_URL,  # noqa: E402
                      GHCN_STATIONS_URL, get_cities)

# Fixed-width .dly record layout
_ID, _YEAR, _MONTH, _ELEMENT = slice(0, 11), slice(11, 15), slice(15, 17), slice(17, 21)
_ELEM_LEN, _VALUE, _MFLAG, _QFLAG, _SFLAG = 8, slice(0, 5), slice(5, 6), slice(6, 7), slice(7, 8)

ELEMENTS = ("TMAX", "TMIN")
_DAYS_IN_MONTH = [31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]

# Conservative first time the official daily value could be considered
# available to researchers explicitly (GHCN daily updates roughly once/day).
# GHCN-Daily files do not carry an individual public release timestamp.  This
# deliberately conservative synthetic gate is *not* evidence that the label
# was available then: it prevents an outcome for local date D from entering a
# D intraday feature set.  CLI/TWC publication timestamps, when collected,
# must supersede it.
_AVAIL_OFFSET_HOURS = 36


def _dly_records(raw: str):
    for line in raw.splitlines():
        line = line.strip()
        if len(line) < 21:
            continue
        yield {
            "station_id": line[_ID].strip(),
            "year": int(line[_YEAR]),
            "month": int(line[_MONTH]),
            "element": line[_ELEMENT].strip(),
            "days": line[21:],
        }


def _parse_value_cell(cell: str) -> tuple[float | None, str, str, str]:
    value = cell[_VALUE].strip()
    mflag = cell[_MFLAG].strip()
    qflag = cell[_QFLAG].strip()
    sflag = cell[_SFLAG].strip()
    if value == "-9999" or value == "":
        return None, mflag, qflag, sflag
    # TMAX/TMIN stored in tenths of degrees Celsius
    return float(value) / 10.0, mflag, qflag, sflag


def fetch_dly(ghcn_id: str, out_dir: Path) -> Path:
    url = f"{GHCN_ALL_URL}/{ghcn_id}.dly"
    dest = out_dir / f"{ghcn_id}.dly"
    if dest.exists() and dest.stat().st_size > 0:
        print(f"  cache hit  {dest}")
        return dest
    print(f"  fetching  {url}")
    dest.write_bytes(http_get(url, timeout=120))
    print(f"  wrote     {dest} ({dest.stat().st_size} bytes)")
    return dest


def fetch_stations_meta(out_dir: Path) -> Path:
    dest = out_dir / "ghcnd-stations.txt"
    if dest.exists() and dest.stat().st_size > 0:
        print(f"  cache hit  {dest}")
        return dest
    print(f"  fetching  {GHCN_STATIONS_URL}")
    dest.write_bytes(http_get(GHCN_STATIONS_URL, timeout=180))
    print(f"  wrote     {dest}")
    return dest


def station_meta(fpath: Path, ghcn_id: str) -> dict:
    """lat, lon, elevation from ghcnd-stations.txt (space separated)."""
    for line in fpath.read_text(errors="replace").splitlines():
        if line.startswith(ghcn_id):
            parts = line.split()
            # ID lat lon elev state name ...
            return {
                "station_id": parts[0],
                "lat": float(parts[1]),
                "lon": float(parts[2]),
                "elevation_m": float(parts[3]),
                "state": parts[4],
                "name": " ".join(parts[5:]) or None,
            }
    return {"station_id": ghcn_id}


def parse_dly(path: Path) -> list[dict]:
    rows: list[dict] = []
    raw = path.read_text(errors="replace")
    for rec in _dly_records(raw):
        if rec["element"] not in ELEMENTS:
            continue
        station = rec["station_id"]
        n_days = 29 if (rec["month"] == 2 and rec["year"] % 4 == 0 and
                        (rec["year"] % 100 != 0 or rec["year"] % 400 == 0)) else _DAYS_IN_MONTH[rec["month"] - 1]
        for day_idx in range(n_days):
            cell = rec["days"][day_idx * _ELEM_LEN:(day_idx + 1) * _ELEM_LEN]
            if len(cell) != _ELEM_LEN:
                continue
            value_c, mflag, qflag, sflag = _parse_value_cell(cell)
            if value_c is None:
                continue
            d = date_from(rec["year"], rec["month"], day_idx + 1)
            rows.append({
                "station_id": station,
                "element": rec["element"],
                "date": d.isoformat(),
                "value_c": round(value_c, 2),
                "value_f": round(value_c * 9.0 / 5.0 + 32.0, 2),
                "mflag": mflag,
                "qflag": qflag,
                "sflag": sflag,
                "label_available_ts": (datetime(d.year, d.month, d.day,
                                                tzinfo=timezone.utc) +
                                       timedelta(hours=_AVAIL_OFFSET_HOURS)
                                       ).isoformat().replace("+00:00", "Z"),
            })
    return rows


def date_from(year: int, month: int, day: int) -> datetime.date:
    import datetime as _dt
    return _dt.date(year, month, day)


def pivoted(rows: list[dict], station_city: dict[str, str]) -> list[dict]:
    """One row per station/date with tmax_* and tmin_* columns."""
    by_key: dict[tuple, dict] = {}
    for r in rows:
        key = (r["station_id"], r["date"])
        out = by_key.setdefault(key, {
            "station_id": r["station_id"],
            "city": station_city.get(r["station_id"], ""),
            "date": r["date"],
            "source": "GHCN-Daily",
            "tmax_c": None, "tmax_f": None, "tmax_qflag": "", "tmax_mflag": "", "tmax_sflag": "",
            "tmin_c": None, "tmin_f": None, "tmin_qflag": "", "tmin_mflag": "", "tmin_sflag": "",
            "label_available_ts": r["label_available_ts"],
        })
        if r["element"] == "TMAX":
            out["tmax_c"] = r["value_c"]
            out["tmax_f"] = r["value_f"]
            out["tmax_qflag"] = r["qflag"]
            out["tmax_mflag"] = r["mflag"]
            out["tmax_sflag"] = r["sflag"]
        else:
            out["tmin_c"] = r["value_c"]
            out["tmin_f"] = r["value_f"]
            out["tmin_qflag"] = r["qflag"]
            out["tmin_mflag"] = r["mflag"]
            out["tmin_sflag"] = r["sflag"]
    return sorted(by_key.values(), key=lambda r: (r["station_id"], r["date"]))


COLUMNS = [
    "station_id", "city", "date", "source",
    "tmax_c", "tmax_f", "tmax_qflag", "tmax_mflag", "tmax_sflag",
    "tmin_c", "tmin_f", "tmin_qflag", "tmin_mflag", "tmin_sflag",
    "label_available_ts",
]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cities", nargs="*", default=None,
                    help="city keys (default: phx lv)")
    ap.add_argument("--since", default=None,
                    help="include observations from YYYY-MM-DD onwards "
                         "(default: full station history); writes a suffixed "
                         "subset file rather than replacing canonical labels")
    args = ap.parse_args()

    dirs = ensure_runtime_dirs()
    cities = get_cities(args.cities or DEFAULT_CITIES)
    stations_meta = fetch_stations_meta(dirs["ghcn_raw"])

    all_rows: list[dict] = []
    station_city: dict[str, str] = {}
    for city in cities:
        dly = fetch_dly(city.ghcn_id, dirs["ghcn_raw"])
        meta = station_meta(stations_meta, city.ghcn_id)
        print(f"[{city.key}] {city.city} station meta: {meta}")
        rows = parse_dly(dly)
        if args.since:
            rows = [r for r in rows if r["date"] >= args.since]
        all_rows.extend(rows)
        station_city[city.ghcn_id] = city.key
        print(f"[{city.key}] parsed {len(rows)} TMAX/TMIN observations")

    piv = pivoted(all_rows, station_city)
    out = (dirs["ghcn_out"] / f"labels_daily_since_{args.since}.csv"
           if args.since else dirs["ghcn_out"] / "labels_daily.csv")
    with out.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(piv)
    print(f"wrote {out}")

    by_city: dict[str, int] = {}
    for r in piv:
        by_city[r["city"]] = by_city.get(r["city"], 0) + 1
    print("daily label rows per city:", by_city)
    print(f"fetched_at={utcnow()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

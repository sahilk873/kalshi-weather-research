"""IEM ASOS raw METAR archive + parsed fields/remarks for PHX and LAS.

Source: Iowa Environmental Mesonet ASOS downloader (authoritative NOAA METAR
feeder mirror, widely used in research):
    https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py
    params: network=AZ_ASOS (NV_ASOS), station=PHX (LAS),
            data=all, report_type=3 (routine) + 4 (specials),
            tz=Etc/UTC, format=onlycomma

The returned CSV includes parsed columns (tmpf F, dwpf, relh, drct, sknt,
gust, alti, mslp, vsby, p01i, skyc*, skyl*, wxcodes, peak wind, feel,
snowdepth) and a raw ``metar`` column containing the full METAR text with
its RMK (remarks) section verbatim.

Outputs:
- data/weather_research/iem/raw/<SID>_<start>_<end>.csv   (raw archive cache)
- data/weather_research/iem/asos_parsed.csv               (normalized obs)
- data/weather_research/iem/asos_daily.csv                (aggregates)

Aggregation notes (important, not fabricated):
- tmax_f/tmin_f from METAR are the *sampled* extremes of hourly/reported
  observations and are proxies, NOT the official daily extremes (GHCN-Daily
  is the official label source). The difference typically understates rapid
  intra-hour swings.
- Local calendar date uses the city's official IANA zone
  (America/Phoenix, America/Los_Angeles) so a daily join with Kalshi market
  dates is consistent with the local outcome date.
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

_SELF = Path(__file__).resolve().parent
sys.path.insert(0, str(_SELF))

# ruff: noqa: E402
import common  # noqa: E402
from common import ensure_runtime_dirs, http_get_text, to_float, utcnow  # noqa: E402
from stations import DEFAULT_CITIES, IEM_ASOS_DOWNLOAD, get_cities  # noqa: E402

MISSING_PLACEHOLDERS = {"M", "T", "", "None"}

PARSED_COLUMNS = [
    "station", "valid_utc", "local_date",
    "tmpf", "dwpf", "relh", "drct", "sknt", "gust",
    "p01i", "alti", "mslp", "vsby",
    "skyc1", "skyc2", "skyc3", "skyc4",
    "skyl1", "skyl2", "skyl3", "skyl4",
    "wxcodes", "ice_accretion_1hr", "ice_accretion_3hr", "ice_accretion_6hr",
    "peak_wind_gust", "peak_wind_drct", "peak_wind_time", "feel", "snowdepth",
    "remark_temp_tenths_c", "remark_dewpoint_tenths_c",
    "remark_6h_max_tenths_c", "remark_6h_min_tenths_c",
    "remark_24h_max_tenths_c", "remark_24h_min_tenths_c",
    "remark_pressure_tendency_code", "remark_pressure_change_tenths_hpa",
    "raw_metar",
]

DAILY_COLUMNS = [
    "station", "city", "local_date", "obs_count",
    "tmax_f", "tmin_f", "tmax_utc", "tmin_utc",
    "first_obs_utc", "last_obs_utc", "tmpf_missing_count",
    "is_complete_day_approx", "sampled_only_flag",
]


def _signed_tenths(group: str) -> float:
    """Decode METAR T-group magnitude; leading 1 means below zero C."""
    return (-1 if group[0] == "1" else 1) * int(group[1:]) / 10.0


def parse_remarks(raw_metar: str) -> dict[str, object]:
    """Extract standard ASOS remark groups without altering raw METAR.

    TsnTTTsnTTT is precise temperature/dew point; 1/2 groups are six-hour
    extrema; 4-group is 24-hour max/min; 5-group is pressure tendency.
    Missing groups stay null rather than being inferred from observations.
    """
    out = {k: None for k in PARSED_COLUMNS if k.startswith("remark_")}
    if " RMK " not in f" {raw_metar} ":
        return out
    remarks = raw_metar.split(" RMK ", 1)[1]
    m = re.search(r"\bT([01]\d{3})([01]\d{3})\b", remarks)
    if m:
        out["remark_temp_tenths_c"] = _signed_tenths(m.group(1))
        out["remark_dewpoint_tenths_c"] = _signed_tenths(m.group(2))
    m = re.search(r"\b1([01]\d{3})\b", remarks)
    if m:
        out["remark_6h_max_tenths_c"] = _signed_tenths(m.group(1))
    m = re.search(r"\b2([01]\d{3})\b", remarks)
    if m:
        out["remark_6h_min_tenths_c"] = _signed_tenths(m.group(1))
    m = re.search(r"\b4([01]\d{3})([01]\d{3})\b", remarks)
    if m:
        out["remark_24h_max_tenths_c"] = _signed_tenths(m.group(1))
        out["remark_24h_min_tenths_c"] = _signed_tenths(m.group(2))
    m = re.search(r"\b5(\d)(\d{3})\b", remarks)
    if m:
        out["remark_pressure_tendency_code"] = int(m.group(1))
        out["remark_pressure_change_tenths_hpa"] = int(m.group(2)) / 10.0
    return out


def iem_url(city, start: datetime, end: datetime) -> str:
    """Query string for the IEM ASOS downloader (single station)."""
    params = {
        "network": city.iem_network,
        "station": city.iem_sid,
        "data": "all",
        "year1": start.year, "month1": start.month, "day1": start.day,
        "year2": end.year, "month2": end.month, "day2": end.day,
        "tz": "Etc/UTC",
        "format": "onlycomma",
        "report_type": ["3", "4"],
        "direct": "1",
    }
    # report_type must repeat -> encode as list
    query = urlencode(params, doseq=True)
    return f"{IEM_ASOS_DOWNLOAD}?{query}"


def fetch_archive(city, start: datetime, end: datetime, out_dir: Path) -> Path:
    start_s, end_s = start.strftime("%Y%m%d"), end.strftime("%Y%m%d")
    dest = out_dir / f"{city.iem_sid}_{start_s}_{end_s}.csv"
    if dest.exists() and dest.stat().st_size > 0:
        print(f"  cache hit  {dest} ({dest.stat().st_size} bytes)")
        return dest
    url = iem_url(city, start, end)
    print(f"[{city.key}] fetching IEM ASOS {city.iem_sid} "
          f"{start.strftime('%Y-%m-%d')}..{end.strftime('%Y-%m-%d')}")
    text = http_get_text(url, timeout=300, max_retries=6)
    if text.lstrip().startswith("<!DOCTYPE") or "station,valid" not in text[:2000]:
        raise RuntimeError(f"unexpected IEM response for {city.iem_sid}; "
                           "download may have failed or hit a throttle limit")
    dest.write_text(text)
    print(f"  wrote {dest} ({dest.stat().st_size} bytes)")
    return dest


def parse_archive(path: Path, city, tz_start_offset_hours: int | None = None) -> list[dict]:
    rows: list[dict] = []
    with path.open(newline="", errors="replace") as fh:
        reader = csv.DictReader(fh)
        # IEM headers are lowercase; harmonize
        fieldmap = {k.strip().lower(): k for k in (reader.fieldnames or [])}
        for line in reader:
            if not line or line.get(fieldmap.get("station", "station"), "") == "":
                continue
            valid = (line.get("valid") or "").strip()
            if not valid:
                continue
            try:
                utc_dt = datetime.strptime(valid, "%Y-%m-%d %H:%M").replace(
                    tzinfo=timezone.utc
                )
            except ValueError:
                continue
            raw = (line.get("metar") or "").strip()
            row = {
                "station": (line.get("station") or "").strip(),
                "valid_utc": utc_dt.isoformat().replace("+00:00", "Z"),
                "local_date": utc_dt.astimezone(ZoneInfo(city.tz_name)).date().isoformat(),
                "tmpf": to_float(line.get("tmpf")),
                "dwpf": to_float(line.get("dwpf")),
                "relh": to_float(line.get("relh")),
                "drct": to_float(line.get("drct")),
                "sknt": to_float(line.get("sknt")),
                "gust": to_float(line.get("gust")),
                "p01i": to_float(line.get("p01i")),
                "alti": to_float(line.get("alti")),
                "mslp": to_float(line.get("mslp")),
                "vsby": to_float(line.get("vsby")),
                "skyc1": line.get("skyc1") or "",
                "skyc2": line.get("skyc2") or "",
                "skyc3": line.get("skyc3") or "",
                "skyc4": line.get("skyc4") or "",
                "skyl1": to_float(line.get("skyl1")),
                "skyl2": to_float(line.get("skyl2")),
                "skyl3": to_float(line.get("skyl3")),
                "skyl4": to_float(line.get("skyl4")),
                "wxcodes": line.get("wxcodes") or "",
                "ice_accretion_1hr": to_float(line.get("ice_accretion_1hr")),
                "ice_accretion_3hr": to_float(line.get("ice_accretion_3hr")),
                "ice_accretion_6hr": to_float(line.get("ice_accretion_6hr")),
                "peak_wind_gust": to_float(line.get("peak_wind_gust")),
                "peak_wind_drct": to_float(line.get("peak_wind_drct")),
                "peak_wind_time": (line.get("peak_wind_time") or "").strip(),
                "feel": to_float(line.get("feel")),
                "snowdepth": to_float(line.get("snowdepth")),
                "raw_metar": raw,
            }
            row.update(parse_remarks(raw))
            rows.append(row)
    return rows


def daily_aggregates(rows: list[dict], city) -> list[dict]:
    by_day: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_day[r["local_date"]].append(r)

    out: list[dict] = []
    for day in sorted(by_day):
        obs = by_day[day]
        temps = [(r["valid_utc"], r["tmpf"]) for r in obs if r["tmpf"] is not None]
        missing = sum(1 for r in obs if r["tmpf"] is None)
        tmax_utc = tmin_utc = ""
        tmax_f = tmin_f = None
        if temps:
            tmax_dt, tmax_f = max(temps, key=lambda t: t[1])
            tmin_dt, tmin_f = min(temps, key=lambda t: t[1])
            tmax_utc, tmin_utc = tmax_dt, tmin_dt
        times = sorted(r["valid_utc"] for r in obs)
        # A "complete" climate day would have ~24 hourly reports; allow a
        # tolerance but flag heavily-sparse days.
        approx_complete = len(obs) >= 18
        out.append({
            "station": city.iem_sid,
            "city": city.key,
            "local_date": day,
            "obs_count": len(obs),
            "tmax_f": tmax_f,
            "tmin_f": tmin_f,
            "tmax_utc": tmax_utc,
            "tmin_utc": tmin_utc,
            "first_obs_utc": times[0] if times else "",
            "last_obs_utc": times[-1] if times else "",
            "tmpf_missing_count": missing,
            "is_complete_day_approx": approx_complete,
            "sampled_only_flag": "sampled-obs-extremes, not official daily extremes",
        })
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cities", nargs="*", default=None)
    ap.add_argument("--days", type=int, default=30,
                    help="number of trailing days to fetch (default 30)")
    ap.add_argument("--start", default=None,
                    help="start date YYYY-MM-DD (overrides --days)")
    ap.add_argument("--end", default=None,
                    help="end date YYYY-MM-DD (default: today UTC)")
    args = ap.parse_args()

    dirs = ensure_runtime_dirs()
    raw_dir = dirs["iem_out"] / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    cities = get_cities(args.cities or DEFAULT_CITIES)

    end = (datetime.strptime(args.end, "%Y-%m-%d") if args.end
           else datetime.now(timezone.utc))
    if args.start:
        start = datetime.strptime(args.start, "%Y-%m-%d").replace(
            tzinfo=timezone.utc
        )
    else:
        start = end - timedelta(days=args.days)

    all_obs: list[dict] = []
    for city in cities:
        raw = fetch_archive(city, start, end, raw_dir)
        obs = parse_archive(raw, city)
        print(f"[{city.key}] parsed {len(obs)} METAR observations")
        all_obs.extend(obs)

    parsed_path = dirs["iem_out"] / "asos_parsed.csv"
    with parsed_path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=PARSED_COLUMNS)
        writer.writeheader()
        writer.writerows(all_obs)
    print(f"wrote {parsed_path} ({len(all_obs)} rows)")

    daily: list[dict] = []
    for city in cities:
        obs = [r for r in all_obs if r["station"] == city.iem_sid]
        daily.extend(daily_aggregates(obs, city))

    daily_path = dirs["iem_out"] / "asos_daily.csv"
    with daily_path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=DAILY_COLUMNS)
        writer.writeheader()
        writer.writerows(daily)
    print(f"wrote {daily_path} ({len(daily)} rows)")
    print(f"fetched_at={utcnow()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

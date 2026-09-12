"""Build solar geometry and leakage-safe intraday state for city ASOS data.

This deliberately reads only ``city_asos/asos_parsed.csv`` and never reads
final daily labels.  The output is isolated from the legacy PHX/LAS builders.
"""
from __future__ import annotations

import argparse
import bisect
import csv
import math
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data" / "weather_research"
CITY = {
    "nyc": ("NYC", "New York", "America/New_York", 40.7794, -73.8803),
    "austin": ("AUS", "Austin", "America/Chicago", 30.1945, -97.6699),
    "la": ("LAX", "Los Angeles", "America/Los_Angeles", 33.9425, -118.4081),
}
COLS = [
    "station", "city", "valid_utc", "local_date", "current_temperature_f",
    "current_dew_point_f", "observed_high_so_far_f", "observed_low_so_far_f",
    "best_estimated_official_high_so_far_f", "best_estimated_official_low_so_far_f",
    "minutes_since_daily_high", "minutes_since_daily_low",
    "temperature_change_5m_f", "temperature_change_15m_f", "temperature_change_30m_f",
    "temperature_change_60m_f", "recent_temperature_acceleration_f_per_min2",
    "dewpoint_change_60m_f", "wind_speed_change_60m_kt", "wind_direction_change_60_deg",
    "cloud_change_60m", "minutes_since_sunrise", "minutes_until_sunset", "local_hour",
    "day_of_year", "feature_asof_utc",
]

def solar(d: date, lat: float, lon: float):
    g = 2 * math.pi / 365 * (d.timetuple().tm_yday - 1)
    eq = 229.18 * (0.000075 + 0.001868 * math.cos(g) - 0.032077 * math.sin(g)
                   - 0.014615 * math.cos(2*g) - 0.040849 * math.sin(2*g))
    dec = (0.006918 - 0.399912*math.cos(g) + 0.070257*math.sin(g)
           - 0.006758*math.cos(2*g) + 0.000907*math.sin(2*g)
           - 0.002697*math.cos(3*g) + 0.00148*math.sin(3*g))
    ha = math.degrees(math.acos(math.cos(math.radians(90.833)) /
        (math.cos(math.radians(lat))*math.cos(dec)) -
        math.tan(math.radians(lat))*math.tan(dec)))
    base = datetime(d.year, d.month, d.day, tzinfo=timezone.utc)
    def iso(m): return (base + timedelta(minutes=m)).isoformat().replace("+00:00", "Z")
    return {"solar_noon_utc": iso(720 - 4*lon - eq),
            "sunrise_utc": iso(720 - 4*(lon + ha) - eq),
            "sunset_utc": iso(720 - 4*(lon - ha) - eq),
            "daylength_min": round(8*ha, 3), "declination_deg": round(math.degrees(dec), 5),
            "eqtime_min": round(eq, 4)}

def parse(s):
    if not s: return None
    try: return float(s)
    except (TypeError, ValueError): return None

def dt(s): return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cities", nargs="+", default=list(CITY), choices=list(CITY))
    ap.add_argument("--start", default=None)
    ap.add_argument("--end", default=None)
    args = ap.parse_args()
    selected = {k: CITY[k] for k in args.cities}
    source = DATA / "city_asos" / "asos_parsed.csv"
    rows = [r for r in csv.DictReader(source.open()) if r["station"] in {v[0] for v in selected.values()}]
    if args.start: rows = [r for r in rows if r["local_date"] >= args.start]
    if args.end: rows = [r for r in rows if r["local_date"] <= args.end]
    solar_dir = DATA / "solar_city"; solar_dir.mkdir(parents=True, exist_ok=True)
    dates = sorted({r["local_date"] for r in rows})
    with (solar_dir / "solar_features.csv").open("w", newline="") as fh:
        fields = ["city", "date", "station", "lat", "lon", "solar_noon_utc", "sunrise_utc", "sunset_utc", "sunrise_local", "sunset_local", "daylength_min", "declination_deg", "eqtime_min"]
        w = csv.DictWriter(fh, fieldnames=fields); w.writeheader()
        for dstr in dates:
            d = date.fromisoformat(dstr)
            for key, (sid, name, tz, lat, lon) in selected.items():
                f = solar(d, lat, lon); z = ZoneInfo(tz)
                row = {"city": key, "date": dstr, "station": sid, "lat": lat, "lon": lon, **f}
                row["sunrise_local"] = dt(f["sunrise_utc"]).astimezone(z).isoformat()
                row["sunset_local"] = dt(f["sunset_utc"]).astimezone(z).isoformat(); w.writerow(row)
    sol = {(r["city"], r["date"]): r for r in csv.DictReader((solar_dir / "solar_features.csv").open())}
    grouped = {}
    for r in rows: grouped.setdefault((r["station"], r["local_date"]), []).append(r)
    out = []
    for (sid, day), rs in sorted(grouped.items()):
        key = next(k for k,v in selected.items() if v[0] == sid); tz = ZoneInfo(selected[key][2]); rs.sort(key=lambda x:x["valid_utc"])
        seen=set(); rs=[r for r in rs if not (r["valid_utc"] in seen or seen.add(r["valid_utc"]))]; times=[dt(r["valid_utc"]) for r in rs]
        s=sol.get((key,day),{}); sunrise=dt(s["sunrise_utc"]) if s else None; sunset=dt(s["sunset_utc"]) if s else None
        hi=[]; lo=[]
        def prior(i, mins, field):
            j=bisect.bisect_right(times, times[i]-timedelta(minutes=mins))-1
            return parse(rs[j].get(field)) if j >= 0 else None
        for i,r in enumerate(rs):
            at=times[i]; temp=parse(r.get("tmpf")); dew=parse(r.get("dwpf"));
            if temp is not None: hi.append((temp,at)); lo.append((temp,at))
            h=max(hi) if hi else (None,None); l=min(lo) if lo else (None,None)
            def ch(field, mins):
                old=prior(i,mins,field); cur=parse(r.get(field)); return round(cur-old,3) if old is not None and cur is not None else None
            c30=ch("tmpf",30); c60=ch("tmpf",60); oldcloud=rs[bisect.bisect_right(times,at-timedelta(minutes=60))-1].get("skyc1") if bisect.bisect_right(times,at-timedelta(minutes=60)) else None
            local=at.astimezone(tz); out.append({"station":sid,"city":key,"valid_utc":r["valid_utc"],"local_date":day,"current_temperature_f":temp,"current_dew_point_f":dew,"observed_high_so_far_f":h[0],"observed_low_so_far_f":l[0],"best_estimated_official_high_so_far_f":h[0],"best_estimated_official_low_so_far_f":l[0],"minutes_since_daily_high":round((at-h[1]).total_seconds()/60,2) if h[1] else None,"minutes_since_daily_low":round((at-l[1]).total_seconds()/60,2) if l[1] else None,"temperature_change_5m_f":ch("tmpf",5),"temperature_change_15m_f":ch("tmpf",15),"temperature_change_30m_f":c30,"temperature_change_60m_f":c60,"recent_temperature_acceleration_f_per_min2":round((c30-c60)/30,5) if c30 is not None and c60 is not None else None,"dewpoint_change_60m_f":ch("dwpf",60),"wind_speed_change_60m_kt":ch("sknt",60),"wind_direction_change_60_deg":ch("drct",60),"cloud_change_60m":int((r.get("skyc1") or "") != (oldcloud or "")) if oldcloud is not None else None,"minutes_since_sunrise":round((at-sunrise).total_seconds()/60,2) if sunrise else None,"minutes_until_sunset":round((sunset-at).total_seconds()/60,2) if sunset else None,"local_hour":local.hour,"day_of_year":local.timetuple().tm_yday,"feature_asof_utc":r["valid_utc"]})
    dest=DATA/"derived_intraday_state_city"; dest.mkdir(parents=True,exist_ok=True)
    with (dest/"derived_intraday_state.csv").open("w",newline="") as fh: w=csv.DictWriter(fh,fieldnames=COLS); w.writeheader(); w.writerows(out)
    print(f"solar rows={len(dates)*len(selected)} state rows={len(out)} dates={dates[0] if dates else None}..{dates[-1] if dates else None}")
if __name__ == "__main__": main()

"""Normalize selected station-history facts from archived HOMR JSON."""
from __future__ import annotations
import argparse, csv, json
from pathlib import Path

COLS = ["city", "station", "record_type", "id_type", "identifier", "begin_date", "end_date", "detail"]


def parse(path: Path, city: str, station: str) -> list[dict]:
    payload = json.loads(path.read_text())
    stations = payload.get("stationCollection", {}).get("stations", [])
    if len(stations) != 1: raise ValueError(f"expected one HOMR station in {path}")
    obj = stations[0]; out = []
    for item in obj.get("identifiers", []):
        dates = item.get("date", {})
        out.append({"city": city, "station": station, "record_type": "identifier", "id_type": item.get("idType", ""), "identifier": item.get("id", ""), "begin_date": dates.get("beginDate", ""), "end_date": dates.get("endDate", ""), "detail": ""})
    for item in obj.get("relocations", []):
        out.append({"city": city, "station": station, "record_type": "relocation", "id_type": "", "identifier": "", "begin_date": item.get("date", ""), "end_date": "", "detail": item.get("relocation", "")})
    for item in obj.get("remarks", []):
        dates = item.get("date", {})
        out.append({"city": city, "station": station, "record_type": "remark", "id_type": item.get("type", ""), "identifier": "", "begin_date": dates.get("beginDate", ""), "end_date": dates.get("endDate", ""), "detail": item.get("remark", "")})
    location = obj.get("location", {})
    for key, record_type, value_key in (("descriptions", "location_description", "description"), ("latitudes", "latitude", "latitude_dec"), ("longitudes", "longitude", "longitude_dec"), ("elevations", "elevation", "elevationMeters")):
        for item in location.get(key, []):
            dates = item.get("date", {})
            out.append({"city": city, "station": station, "record_type": record_type, "id_type": item.get("precision", ""), "identifier": "", "begin_date": dates.get("beginDate", ""), "end_date": dates.get("endDate", ""), "detail": item.get(value_key, "")})
    for item in obj.get("platforms", []):
        dates = item.get("date", {})
        out.append({"city": city, "station": station, "record_type": "platform", "id_type": item.get("platform", ""), "identifier": "", "begin_date": dates.get("beginDate", ""), "end_date": dates.get("endDate", ""), "detail": ""})
    for item in obj.get("updates", []):
        out.append({"city": city, "station": station, "record_type": "update", "id_type": item.get("updateSource", ""), "identifier": item.get("nativeId", ""), "begin_date": item.get("effectiveDate", ""), "end_date": "", "detail": item.get("description", "")})
    return out


def main() -> None:
    p=argparse.ArgumentParser(description=__doc__); p.add_argument("--input",type=Path,required=True); p.add_argument("--output",type=Path,required=True); a=p.parse_args(); rows=[]
    for path in sorted(a.input.glob("homr_*.json")):
        station=path.stem.removeprefix("homr_"); city={"USW00023183":"phx","USW00023169":"lv","USW00094728":"nyc","USW00023174":"la","USW00013958":"austin"}.get(station, "unknown")
        rows.extend(parse(path,city,station))
    rows.sort(key=lambda r:(r["station"],r["record_type"],r["begin_date"],r["identifier"]))
    a.output.parent.mkdir(parents=True,exist_ok=True)
    with a.output.open("w",newline="") as h: w=csv.DictWriter(h,fieldnames=COLS); w.writeheader(); w.writerows(rows)
    print(f"wrote {a.output} ({len(rows)} rows)")


if __name__ == "__main__": main()

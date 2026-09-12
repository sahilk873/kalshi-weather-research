"""Download point-in-time Open-Meteo historical/previous/single runs.

These APIs are deterministic forecast products, not a substitute for the
live ensemble archive. Raw JSON and request metadata are retained so an
availability or model-version change is visible.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path
from urllib.parse import urlencode

_SELF = Path(__file__).resolve().parent
sys.path.insert(0, str(_SELF))
from common import ensure_runtime_dirs, http_get, utcnow  # noqa: E402
from gefs_ensemble import CITY_LOCATIONS, _member_columns, _write_parquet  # noqa: E402

APIS = {
    "historical": "https://historical-forecast-api.open-meteo.com/v1/forecast",
    "previous-runs": "https://previous-runs-api.open-meteo.com/v1/forecast",
    "single-runs": "https://previous-runs-api.open-meteo.com/v1/forecast",
}


def download(api_name: str, city_key: str, start: str, end: str, model: str,
             ensemble: bool = True) -> tuple[dict, str]:
    _, lat, lon, _ = CITY_LOCATIONS[city_key]
    variables = ["temperature_2m"]
    if api_name == "previous-runs":
        variables = [f"temperature_2m_previous_day{i}" for i in range(1, 8)]
    query = {"latitude": lat, "longitude": lon, "start_date": start,
             "end_date": end, "hourly": ",".join(variables), "models": model,
             "timezone": "UTC", "temperature_unit": "fahrenheit"}
    if api_name == "previous-runs":
        query["past_days"] = 1
    url = APIS[api_name] + "?" + urlencode(query)
    return json.loads(http_get(url)), url


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--api", choices=sorted(APIS), default="historical")
    ap.add_argument("--start", required=True, help="YYYY-MM-DD")
    ap.add_argument("--end", required=True, help="YYYY-MM-DD")
    ap.add_argument("--cities", nargs="+", choices=sorted(CITY_LOCATIONS), default=list(CITY_LOCATIONS))
    ap.add_argument("--model", default="ncep_gefs025")
    args = ap.parse_args()
    d = ensure_runtime_dirs(); out = d["gefs_history"]; out.mkdir(parents=True, exist_ok=True)
    manifest = out / "manifest.csv"
    pred_path = out / ("previous_predictions.csv" if args.api == "previous-runs" else "predictions.csv")
    mf = manifest.open("a", newline=""); pf = pred_path.open("a", newline="")
    mw = csv.DictWriter(mf, fieldnames=["api", "model", "city_key", "start_date", "end_date", "request_url", "raw_path", "sha256", "retrieved_at"])
    prediction_fields = ["model", "run_time", "valid_time", "city_key", "city", "prediction"]
    if args.api == "previous-runs":
        prediction_fields.append("lead_days")
    pw = csv.DictWriter(pf, fieldnames=prediction_fields)
    if manifest.stat().st_size == 0: mw.writeheader()
    if pred_path.stat().st_size == 0: pw.writeheader()
    try:
        for city_key in args.cities:
            payload, url = download(args.api, city_key, args.start, args.end, args.model)
            retrieved = utcnow(); body = json.dumps(payload, sort_keys=True).encode()
            _, lat, lon, tz_name = CITY_LOCATIONS[city_key]
            digest = hashlib.sha256(body).hexdigest()
            raw = out / f"{args.api}_{city_key}_{args.start}_{args.end}_{digest[:12]}.json"
            raw.write_bytes(body)
            mw.writerow({"api": args.api, "model": args.model, "city_key": city_key,
                         "start_date": args.start, "end_date": args.end, "request_url": url,
                         "raw_path": str(raw.relative_to(d["research"])), "sha256": digest,
                         "retrieved_at": retrieved})
            hourly = payload.get("hourly") or {}
            # Historical Forecast responses retain member-suffixed arrays.
            # Archive them in the same long-form contract as live responses.
            member_rows = []
            for member_key, values in _member_columns(hourly, "temperature_2m"):
                member_id = member_key.removeprefix("temperature_2m_")
                for valid_time, value in zip(hourly.get("time", []), values):
                    if value is not None:
                        valid = str(valid_time) + ":00Z"
                        member_rows.append({"forecast_run_time": retrieved, "valid_time": valid,
                            "city": CITY_LOCATIONS[city_key][0], "city_key": city_key,
                            "latitude": lat, "longitude": lon, "timezone": tz_name,
                            "model": args.model, "member_id": member_id,
                            "variable": "temperature_2m", "value": float(value),
                            "retrieved_at": retrieved})
            if member_rows:
                member_path = d["gefs"] / "gefs_members.parquet"
                _write_parquet(member_rows, member_path)
            # Previous-runs and historical deterministic fields are retained
            # as prediction rows for calibration, when present.
            for variable, values in hourly.items():
                if variable == "time" or "member" in variable:
                    continue
                for valid_time, value in zip(hourly.get("time", []), values):
                    if value is not None:
                        prediction = {"model": args.model, "run_time": retrieved,
                                     "valid_time": str(valid_time) + ":00Z", "city_key": city_key,
                                     "city": CITY_LOCATIONS[city_key][0], "prediction": value}
                        if args.api == "previous-runs":
                            prediction["lead_days"] = variable.rsplit("_previous_day", 1)[1]
                        pw.writerow(prediction)
            print(f"{city_key}: archived {args.api} response")
    finally:
        mf.close(); pf.close()


if __name__ == "__main__": main()

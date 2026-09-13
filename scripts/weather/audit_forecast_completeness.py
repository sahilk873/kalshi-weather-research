"""Audit required report-2 forecast fields without treating row counts as coverage."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

REQUIRED = {
    "hrrr": {"temperature_2m", "dewpoint_2m", "wind_speed_10m", "wind_gusts_10m", "cloud_cover", "pressure_surface", "shortwave_radiation", "cape", "cin", "temperature_925hpa", "temperature_850hpa", "temperature_700hpa", "wind_850hpa", "geopotential_height_500hpa"},
    "nbm": {"temperature_2m", "dewpoint_2m"},
    "lamp": {"TMP", "DPT", "WDR", "WSP", "WGS", "SKY", "P01"},
    "gefs": {"temperature_2m", "dew_point_2m", "relative_humidity_2m", "pressure_msl", "cloud_cover", "wind_speed_10m", "wind_direction_10m", "wind_gusts_10m", "shortwave_radiation", "direct_radiation", "diffuse_radiation", "cape", "cin"},
}


def _csv_fields(path: Path, model: str) -> tuple[int, set[str]]:
    if not path.exists():
        return 0, set()
    with path.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    if model == "lamp":
        fields = {str(row.get("field", "")) for row in rows if row.get("field")}
    else:
        rows = [row for row in rows if str(row.get("model", "")).lower() == model]
        fields = {str(row.get("variable", "")) for row in rows if row.get("variable")}
    return len(rows), fields


def _parquet_fields(path: Path) -> tuple[int, set[str]]:
    try:
        import pyarrow.parquet as pq
        if not path.exists():
            return 0, set()
        table = pq.read_table(path, columns=["variable"] if "variable" in pq.read_schema(path).names else None)
        if "variable" in table.column_names:
            variables = {str(value) for value in table.column("variable").to_pylist() if value not in (None, "")}
        else:
            names = set(table.column_names)
            variables = {name.removeprefix("temperature_2m_member").strip("_") or "temperature_2m" for name in names if "temperature_2m_member" in name}
        return pq.read_metadata(path).num_rows, variables
    except (ImportError, OSError, ValueError):
        return 0, set()


def audit(root: Path) -> dict:
    rows, fields = _csv_fields(root / "forecasts" / "model_forecasts_points.csv", "hrrr")
    nbm_rows, nbm_fields = _csv_fields(root / "forecasts" / "model_forecasts_points.csv", "nbm")
    lamp_rows, lamp_fields = _csv_fields(root / "lamp" / "station_forecasts.csv", "lamp")
    gefs_rows, gefs_fields = _parquet_fields(root / "gefs" / "gefs_members.parquet")
    observed = {"hrrr": fields, "nbm": nbm_fields, "lamp": lamp_fields, "gefs": gefs_fields}
    counts = {"hrrr": rows, "nbm": nbm_rows, "lamp": lamp_rows, "gefs": gefs_rows}
    models = []
    for model in ("hrrr", "nbm", "lamp", "gefs"):
        missing = sorted(REQUIRED[model] - observed[model])
        models.append({"model": model, "rows": counts[model], "observed_fields": sorted(observed[model]), "required_fields": sorted(REQUIRED[model]), "missing_fields": missing, "complete": bool(counts[model]) and not missing})
    return {"version": "report2-forecast-completeness-v1", "models": models, "complete": all(item["complete"] for item in models)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument("--root", type=Path, default=Path("data/weather_research")); parser.add_argument("--output", type=Path, default=Path("data/weather_research/reports/forecast_completeness.json")); args = parser.parse_args()
    result = audit(args.root); args.output.parent.mkdir(parents=True, exist_ok=True); args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n"); print(json.dumps({"complete": result["complete"], "models": len(result["models"])}))


if __name__ == "__main__": main()

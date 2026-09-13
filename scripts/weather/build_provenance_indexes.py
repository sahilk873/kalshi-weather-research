"""Build fail-closed provenance indexes for prediction manifests.

The builder never invents receipt clocks or hashes. Rows without a stable
source/observation identity, a raw hash, and an availability timestamp are
written to an explicit rejection report and cannot authorize a prediction.
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


def _first(row: dict, fields: tuple[str, ...]) -> str:
    for field in fields:
        value = str(row.get(field, "")).strip()
        if value:
            return value
    return ""


def build(forecasts: list[dict], observations: list[dict], *, stations: set[str] | None = None) -> tuple[list[dict], list[dict], list[dict]]:
    """Return ``(source_index, observation_index, rejections)``."""
    sources: dict[str, dict] = {}
    obs_index: dict[str, dict] = {}
    rejected: list[dict] = []
    for row_number, row in enumerate(forecasts, 2):
        run_id = _first(row, ("source_run_id",))
        if not run_id:
            initialization = _first(row, ("initialization_time_utc", "forecast_run_time"))
            model = _first(row, ("model",)); city = _first(row, ("city", "city_key"))
            digest = _first(row, ("raw_sha256", "sha256"))
            run_id = ":".join(part for part in (model, city, initialization, digest) if part)
        receipt = _first(row, ("source_receipt_time", "retrieved_at_utc", "ingested_at_utc"))
        digest = _first(row, ("raw_sha256", "sha256"))
        raw_path = _first(row, ("raw_path", "source_raw_path"))
        if raw_path.startswith("raw/"):
            # Point-forecast rows are relative to the forecasts archive.
            # Preserve that namespace so downstream integrity checks resolve
            # the immutable file rather than an ambiguous research-root path.
            raw_path = "forecasts/" + raw_path
        missing = [name for name, value in (("source_run_id", run_id), ("availability_time", receipt), ("raw_sha256", digest), ("raw_path", raw_path)) if not value]
        if missing:
            rejected.append({"kind": "source", "row": row_number, "reason": "missing_" + "+".join(missing)})
            continue
        candidate = {"source_run_id": run_id, "source_receipt_time": receipt,
                     "initialization_time_utc": _first(row, ("initialization_time_utc", "forecast_run_time")),
                     "raw_path": raw_path, "raw_sha256": digest}
        prior = sources.get(run_id)
        if prior is not None:
            identity = ("source_run_id", "initialization_time_utc", "raw_path", "raw_sha256")
            if any(prior[field] != candidate[field] for field in identity):
                rejected.append({"kind": "source", "row": row_number, "reason": "conflicting_source_run_metadata", "source_run_id": run_id})
            elif candidate["source_receipt_time"] < prior["source_receipt_time"]:
                sources[run_id] = candidate
        else:
            sources[run_id] = candidate
    for row_number, row in enumerate(observations, 2):
        station = _first(row, ("station", "station_id")); valid = _first(row, ("valid_utc", "observation_time_utc"))
        if stations is not None and station not in stations:
            rejected.append({"kind": "observation", "row": row_number, "reason": "non_target_station", "station": station})
            continue
        digest = _first(row, ("raw_sha256", "sha256")); receipt = _first(row, ("receipt_utc", "available_ts", "retrieved_at_utc", "ingested_at_utc"))
        raw_path = _first(row, ("raw_path", "source_raw_path"))
        missing = [name for name, value in (("station", station), ("valid_utc", valid), ("raw_sha256", digest), ("availability_time", receipt), ("raw_path", raw_path)) if not value]
        if missing:
            rejected.append({"kind": "observation", "row": row_number, "reason": "missing_" + "+".join(missing)})
            continue
        observation_id = f"{station}:{valid}:{digest}"
        candidate = {"observation_id": observation_id, "station": station, "valid_utc": valid,
                     "available_ts": receipt, "raw_path": raw_path, "raw_sha256": digest}
        prior = obs_index.get(observation_id)
        if prior is not None:
            # The same immutable payload may be re-retrieved. Keep the
            # earliest receipt because it is the strongest PIT availability
            # bound; differing identity fields remain a hard conflict.
            identity = ("station", "valid_utc", "raw_sha256")
            if any(prior[field] != candidate[field] for field in identity):
                rejected.append({"kind": "observation", "row": row_number, "reason": "conflicting_observation_metadata", "observation_id": observation_id})
            elif candidate["available_ts"] < prior["available_ts"]:
                obs_index[observation_id] = candidate
        else:
            obs_index[observation_id] = candidate
    return sorted(sources.values(), key=lambda row: row["source_run_id"]), sorted(obs_index.values(), key=lambda row: row["observation_id"]), rejected


def _read(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def _write(path: Path, fields: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields); writer.writeheader(); writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--forecasts", type=Path, required=True)
    parser.add_argument("--observations", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--station", action="append", dest="stations", default=None,
                        help="exact station allow-list; repeat for multiple stations")
    args = parser.parse_args()
    stations = set(args.stations) if args.stations else None
    sources, observations, rejected = build(_read(args.forecasts), _read(args.observations), stations=stations)
    _write(args.output_dir / "source_index.csv", ["source_run_id", "source_receipt_time", "initialization_time_utc", "raw_path", "raw_sha256"], sources)
    _write(args.output_dir / "observation_index.csv", ["observation_id", "station", "valid_utc", "available_ts", "raw_path", "raw_sha256"], observations)
    scoped_out = sum(row.get("reason") == "non_target_station" for row in rejected)
    hard_rejected = len(rejected) - scoped_out
    status = {"version": "provenance-indexes-v1", "station_scope": sorted(stations) if stations is not None else None, "source_rows": len(sources), "observation_rows": len(observations), "rejected_rows": len(rejected), "scoped_out_rows": scoped_out, "hard_rejected_rows": hard_rejected, "rejections": rejected, "pass": bool(sources and observations) and hard_rejected == 0}
    (args.output_dir / "provenance_index_status.json").write_text(json.dumps(status, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"source_rows": len(sources), "observation_rows": len(observations), "rejected_rows": len(rejected), "pass": status["pass"]}, sort_keys=True))


if __name__ == "__main__":
    main()

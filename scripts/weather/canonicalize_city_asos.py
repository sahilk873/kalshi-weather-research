"""Choose a deterministic canonical row for duplicate city ASOS observations.

Raw monthly IEM files and the original parsed table are never deleted. When
the same station/time is delivered twice, the row with the most populated
meteorological fields is retained in a separate feature table and every
decision is recorded in a resolution manifest.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
from collections import defaultdict
from pathlib import Path


def _score(row: dict[str, str]) -> tuple[int, str]:
    identity = {"station", "valid_utc", "local_date", "raw_metar"}
    populated = sum(bool(value.strip()) for key, value in row.items()
                    if key not in identity and value.strip() not in {"M", "NA", "null"})
    digest = hashlib.sha256(row.get("raw_metar", "").encode()).hexdigest()
    return populated, digest


def canonicalize(rows: list[dict[str, str]]) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    groups: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        groups[(row.get("station", ""), row.get("valid_utc", ""))].append(row)
    canonical, decisions = [], []
    for key in sorted(groups):
        group = groups[key]
        ranked = sorted(group, key=_score, reverse=True)
        winner = ranked[0]
        canonical.append(winner)
        for rank, row in enumerate(ranked):
            decisions.append({
                "station": key[0], "valid_utc": key[1],
                "row_sha256": hashlib.sha256(row.get("raw_metar", "").encode()).hexdigest(),
                "decision": "retained" if rank == 0 else "superseded",
                "score": str(_score(row)[0]),
                "reason": "most_populated_fields_then_raw_metar_hash",
            })
    canonical.sort(key=lambda row: (row.get("station", ""), row.get("valid_utc", "")))
    return canonical, decisions


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path(__file__).resolve().parents[2] / "data" / "weather_research" / "city_asos" / "asos_parsed.csv")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--decisions", type=Path)
    args = parser.parse_args()
    output = args.output or args.input.with_name("asos_parsed_canonical.csv")
    decisions_path = args.decisions or args.input.with_name("asos_duplicate_resolution.csv")
    with args.input.open(newline="") as fh:
        reader = csv.DictReader(fh); rows = list(reader); fields = reader.fieldnames or []
    canonical, decisions = canonicalize(rows)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields); writer.writeheader(); writer.writerows(canonical)
    with decisions_path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["station", "valid_utc", "row_sha256", "decision", "score", "reason"])
        writer.writeheader(); writer.writerows(decisions)
    print(f"wrote {len(canonical)} canonical rows and {len(decisions)} decision rows")


if __name__ == "__main__":
    main()

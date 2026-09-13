"""Audit auxiliary NYC/Los Angeles/Austin daily market identity and sources.

This is deliberately an evidence inventory, not a settlement resolver. The
catalog's event-specific Weather Company rules remain authoritative and may
not be reconstructed from the GHCN proxy labels in this repository.
"""
from __future__ import annotations

import argparse
import ast
import csv
import json
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path

SERIES = {
    "KXHIGHNY": ("nyc", "high"), "KXLOWTNYC": ("nyc", "low"),
    "KXHIGHLAX": ("la", "high"), "KXLOWTLAX": ("la", "low"),
    "KXHIGHAUS": ("austin", "high"), "KXLOWTAUS": ("austin", "low"),
}


def _source(value: str) -> tuple[str, str]:
    if not value:
        return "", ""
    try:
        parsed = ast.literal_eval(value)
    except (ValueError, SyntaxError):
        return value, ""
    if isinstance(parsed, dict):
        return str(parsed.get("name", "")), str(parsed.get("url", ""))
    return value, ""


def _event_date(ticker: str) -> str:
    match = re.search(r"-(\d{2})([A-Z]{3})(\d{2})(?:-|$)", ticker)
    if not match:
        return ""
    try:
        return datetime.strptime("".join(match.groups()), "%y%b%d").date().isoformat()
    except ValueError:
        return ""


def audit(rows: list[dict]) -> dict:
    groups: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        series = row.get("series_ticker", "")
        if series in SERIES:
            groups[series].append(row)
    out = {"scope": "auxiliary_forecast_research_only", "series": {}, "pass": True}
    for series, (city, temp_type) in SERIES.items():
        selected = groups.get(series, [])
        names, urls, dates = set(), set(), []
        resolved = 0
        for row in selected:
            name, url = _source(row.get("settlement_sources", ""))
            if name:
                names.add(name)
            if url:
                urls.add(url)
            if row.get("result", "").strip():
                resolved += 1
            if (day := _event_date(row.get("event_ticker", ""))):
                dates.append(day)
        out["series"][series] = {
            "city": city, "temp_type": temp_type,
            "market_rows": len(selected),
            "event_rows": len({r.get("event_ticker") for r in selected}),
            "resolved_market_rows": resolved,
            "unresolved_market_rows": len(selected) - resolved,
            "event_date_min": min(dates) if dates else "",
            "event_date_max": max(dates) if dates else "",
            "settlement_source_names": sorted(names),
            "settlement_source_urls": sorted(urls),
            "rules_reproduced": False,
        }
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path,
                        default=Path(__file__).resolve().parents[2] / "data" / "kalshi_weather_markets_flattened.csv")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    with args.catalog.open(newline="") as fh:
        report = audit(list(csv.DictReader(fh)))
    text = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text)
    else:
        print(text, end="")


if __name__ == "__main__":
    main()

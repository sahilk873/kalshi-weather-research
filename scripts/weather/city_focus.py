"""Registry and read-only audit for the active NYC/LA/Austin research layer.

This is deliberately separate from ``stations.py``: it does not change the
four-market PHX/LV settlement configuration.  The retained city archive now
includes hourly and daily catalog series; their event-specific Weather Company
rules must be audited before treating them as labels.
"""
from __future__ import annotations

import argparse
import csv
import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class FocusCity:
    key: str
    display_name: str
    timezone: str
    settlement_station: str
    ghcn_station: str
    cli_product: str
    kalshi_series: str
    daily_high_series: str
    daily_low_series: str
    role: str = "forecast_research_only"


CITIES = {
    "nyc": FocusCity("nyc", "New York City", "America/New_York", "KNYC", "USW00094728", "CLINYC", "KXTEMPNYCH", "KXHIGHNY", "KXLOWTNYC"),
    "la": FocusCity("la", "Los Angeles", "America/Los_Angeles", "KLAX", "USW00023174", "CLILAX", "KXTEMPLAXH", "KXHIGHLAX", "KXLOWTLAX"),
    "austin": FocusCity("austin", "Austin", "America/Chicago", "KAUS", "USW00013904", "CLIAUS", "KXTEMPAUSH", "KXHIGHAUS", "KXLOWTAUS"),
}


def _rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="") as fh:
        return list(csv.DictReader(fh))


def audit_inputs(research_root: Path) -> dict:
    """Audit source coverage and key integrity without changing any files."""
    labels = _rows(research_root / "ghcn_city" / "labels_daily.csv")
    cli = _rows(research_root / "city_nws_cli" / "daily_climate_cli.csv")
    asos = _rows(research_root / "city_asos" / "asos_parsed.csv")
    markets = _rows(research_root / "kalshi_historical_city" / "markets.csv")
    report = {"cities": {}, "scope_warning": "City hourly and daily lines are catalog/market inputs; event-level Weather Company settlement rules are not verified labels."}
    for key, city in CITIES.items():
        city_labels = [r for r in labels if r.get("city") == key]
        city_cli = [r for r in cli if r.get("city") == key]
        city_asos = [r for r in asos if r.get("station") == city.settlement_station.removeprefix("K")]
        city_markets = [r for r in markets if r.get("city") == key]
        duplicate_label_keys = _duplicates(city_labels, ("station_id", "date", "source"))
        duplicate_obs_keys = _duplicates(city_asos, ("station", "valid_utc"))
        report["cities"][key] = {
            **asdict(city),
            "label_rows": len(city_labels),
            "cli_product_versions": len(city_cli),
            "asos_rows": len(city_asos),
            "market_rows": len(city_markets),
            "daily_high_market_rows": sum(r.get("series_ticker") == city.daily_high_series for r in city_markets),
            "daily_low_market_rows": sum(r.get("series_ticker") == city.daily_low_series for r in city_markets),
            "label_duplicate_keys": duplicate_label_keys,
            "asos_duplicate_keys": duplicate_obs_keys,
            "label_available_timestamps": sum(bool(r.get("label_available_ts")) for r in city_labels),
            "cli_publication_timestamps": sum(bool(r.get("publication_time_utc")) for r in city_cli),
            "market_series": sorted({r.get("series_ticker", "") for r in city_markets if r.get("series_ticker")}),
        }
    return report


def _duplicates(rows: list[dict], fields: tuple[str, ...]) -> int:
    seen: set[tuple[str, ...]] = set()
    duplicates = 0
    for row in rows:
        key = tuple(row.get(field, "") for field in fields)
        if key in seen:
            duplicates += 1
        seen.add(key)
    return duplicates


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--research-root", type=Path, default=Path(__file__).resolve().parents[2] / "data" / "weather_research")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = audit_inputs(args.research_root)
    text = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(text)
    else:
        print(text, end="")


if __name__ == "__main__":
    main()

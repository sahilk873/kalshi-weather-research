"""Audit KXTEMPNYCH source-era metadata against the captured transition notice."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo


EXPECTED_BEFORE = "The Weather Company"
EXPECTED_AFTER = "Synoptic Data"


def _parse_ts(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def _transition_from_notice(notice: str, reference_year: int) -> datetime | None:
    """Parse the first effective month/day and market start hour in the notice."""
    date_match = re.search(r"(?:Effective|effective)\s+(?:[A-Za-z]+,\s*)?([A-Za-z]+)\s+(\d{1,2})(?:st|nd|rd|th)?", notice)
    hour_match = re.search(r"for the\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)\s*[-–]\s*\d{1,2}(?::\d{2})?\s*(?:am|pm)?\s*ET", notice, re.I)
    if not date_match or not hour_match:
        return None
    try:
        month = datetime.strptime(date_match.group(1)[:3], "%b").month
        hour = int(hour_match.group(1)) % 12
        if hour_match.group(3).lower() == "pm":
            hour += 12
        local = datetime(reference_year, month, int(date_match.group(2)), hour, int(hour_match.group(2) or 0), tzinfo=ZoneInfo("America/New_York"))
        return local.astimezone(timezone.utc)
    except (ValueError, TypeError):
        return None


def audit(series_path: Path, contracts_path: Path) -> dict:
    series_wrapper = json.loads(series_path.read_text())
    series = series_wrapper.get("series", series_wrapper)
    info = (series.get("product_metadata") or {}).get("important_info") or {}
    notice = str(info.get("markdown") or "")
    notice_hash = hashlib.sha256(notice.encode()).hexdigest()
    reference = _parse_ts(series.get("last_updated_ts", "")) or datetime.now(timezone.utc)
    transition_utc = _transition_from_notice(notice, reference.year)
    with contracts_path.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    before = after = 0
    mismatches: list[dict] = []
    for row in rows:
        target = _parse_ts(row.get("target_time_utc", ""))
        if target is None:
            continue
        expected = EXPECTED_AFTER if transition_utc and target >= transition_utc else EXPECTED_BEFORE
        if transition_utc and target >= transition_utc:
            after += 1
        else:
            before += 1
        actual = row.get("settlement_source_name", "")
        if actual != expected:
            mismatches.append({"market_ticker": row.get("market_ticker", ""), "target_time_utc": row.get("target_time_utc", ""), "expected": expected, "actual": actual})
    transition_present = bool(re.search(r"transition.*Synoptic|Synoptic.*transition", notice, re.I))
    return {
        "version": "report2-settlement-source-transition-v1",
        "transition_effective_utc": transition_utc.isoformat().replace("+00:00", "Z") if transition_utc else None,
        "before_rows": before,
        "after_rows": after,
        "expected_sources": {"before": EXPECTED_BEFORE, "after": EXPECTED_AFTER},
        "notice_present": transition_present,
        "notice_hash": notice_hash,
        "notice": notice,
        "mismatches": mismatches,
        "pass": transition_present and transition_utc is not None and not mismatches,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    root = Path("data/weather_research/kalshi_hourly")
    parser.add_argument("--series", type=Path, default=root / "series.json")
    parser.add_argument("--contracts", type=Path, default=root / "contracts.csv")
    parser.add_argument("--output", type=Path, default=Path("data/weather_research/reports/settlement_source_transition.json"))
    args = parser.parse_args()
    result = audit(args.series, args.contracts)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"before": result["before_rows"], "after": result["after_rows"], "mismatches": len(result["mismatches"]), "pass": result["pass"]}))


if __name__ == "__main__":
    main()

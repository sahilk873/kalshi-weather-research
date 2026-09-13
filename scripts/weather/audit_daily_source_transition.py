"""Audit daily temperature source-era expectations without filling missing history."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import date, datetime, timezone
from pathlib import Path

TRANSITION_DATE = date(2026, 8, 14)
PRODUCT_BY_SERIES = {
    "KXHIGHNY": "CLINYC", "KXLOWTNYC": "CLINYC", "KXHIGHLAX": "CLILAX",
    "KXLOWTLAX": "CLILAX", "KXHIGHAUS": "CLIAUS", "KXLOWTAUS": "CLIAUS",
}


def _target_date(event_ticker: str) -> date | None:
    try:
        return datetime.strptime(event_ticker.rsplit("-", 1)[-1], "%y%b%d").date()
    except (TypeError, ValueError):
        return None


def audit(payload: dict, *, receipt_ts: str = "") -> dict:
    rows = []; reasons: dict[str, int] = {}
    for series, body in payload.items():
        expected_product = PRODUCT_BY_SERIES.get(series)
        for market in body.get("markets") or []:
            ticker = market.get("ticker", ""); target = _target_date(market.get("event_ticker", ""))
            reason = ""
            if not expected_product or target is None:
                reason = "invalid_daily_market_identity"
            elif target < TRANSITION_DATE:
                reason = "historical_source_metadata_not_retained"
            elif expected_product not in str(market.get("rules_primary", "")):
                reason = "settlement_product_mismatch"
            elif "The Weather Company" not in str(market.get("rules_primary", "")):
                reason = "settlement_source_mismatch"
            status = "rejected" if reason else "verified_post_transition_twc"
            rows.append({"market_ticker": ticker, "series_ticker": series,
                         "target_date": "" if target is None else target.isoformat(),
                         "expected_product": expected_product or "", "expected_source": "The Weather Company",
                         "status": status, "reason": reason})
            if reason: reasons[reason] = reasons.get(reason, 0) + 1
    return {"version": "daily-source-transition-audit-v1", "transition_effective_date": TRANSITION_DATE.isoformat(),
            "transition_notice": "Effective Friday, August 14th, daily temperature markets transition NWS to The Weather Company.",
            "retrieved_at_utc": receipt_ts, "rows": rows, "verified_rows": sum(r["status"].startswith("verified") for r in rows),
            "rejected_rows": sum(r["status"] == "rejected" for r in rows), "rejection_reasons": reasons,
            "pass": bool(rows) and not reasons}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--markets", type=Path, required=True); parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(); payload = json.loads(args.markets.read_text())
    receipt = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"); result = audit(payload, receipt_ts=receipt)
    raw_hash = hashlib.sha256(args.markets.read_bytes()).hexdigest(); result["input_sha256"] = raw_hash
    args.output.parent.mkdir(parents=True, exist_ok=True); args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({k: result[k] for k in ("verified_rows", "rejected_rows", "pass")}, sort_keys=True))


if __name__ == "__main__": main()

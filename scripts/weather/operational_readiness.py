"""Fail-closed research/paper-trading readiness and kill-switch evaluator.

This module evaluates a supplied health snapshot only.  It never connects to
Kalshi and never submits orders.  Missing critical telemetry is treated as an
unsafe condition rather than silently assumed healthy.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Mapping

DEFAULT_THRESHOLDS = {
    "max_feed_age_seconds": 300.0,
    "max_model_run_age_seconds": 21600.0,
    "max_clock_drift_seconds": 2.0,
    "max_calibration_error": 0.10,
    "max_daily_drawdown": 0.05,
}

def evaluate(snapshot: Mapping[str, object], thresholds: Mapping[str, object] | None = None) -> dict:
    """Return deterministic readiness JSON with ``allow_trading`` and reasons."""
    limits = dict(DEFAULT_THRESHOLDS)
    if thresholds:
        limits.update(thresholds)
    reasons: list[dict[str, object]] = []

    def fail(code: str, detail: str) -> None:
        reasons.append({"code": code, "detail": detail})

    feeds = snapshot.get("feed_age_seconds")
    if not isinstance(feeds, Mapping) or not feeds:
        fail("missing_feed_age", "feed_age_seconds telemetry is missing")
    else:
        for name in sorted(feeds):
            try: age = float(feeds[name])
            except (TypeError, ValueError):
                fail("invalid_feed_age", f"{name} is not numeric"); continue
            if age < 0 or age > float(limits["max_feed_age_seconds"]):
                fail("stale_feed", f"{name} age_seconds={age:g}")

    runs = snapshot.get("model_run_age_seconds")
    if not isinstance(runs, Mapping) or not runs:
        fail("missing_model_run_age", "model_run_age_seconds telemetry is missing")
    else:
        for name in sorted(runs):
            try: age = float(runs[name])
            except (TypeError, ValueError):
                fail("invalid_model_run_age", f"{name} is not numeric"); continue
            if age < 0 or age > float(limits["max_model_run_age_seconds"]):
                fail("stale_model_run", f"{name} age_seconds={age:g}")

    if snapshot.get("probability_consistent") is not True:
        fail("probability_inconsistent", "probability consistency check is false or missing")
    try: drift = float(snapshot["clock_drift_seconds"])
    except (KeyError, TypeError, ValueError): drift = None
    if drift is None or abs(drift) > float(limits["max_clock_drift_seconds"]):
        fail("clock_drift", "clock drift is missing or exceeds threshold")
    if snapshot.get("orderbook_sequence_gap_resolved") is not True:
        fail("orderbook_gap", "order-book sequence gap is unresolved or telemetry is missing")
    if snapshot.get("settlement_rules_verified") is not True:
        fail("rules_unverified", "settlement rules are not verified")
    try: calibration = float(snapshot["calibration_error"])
    except (KeyError, TypeError, ValueError): calibration = None
    if calibration is None or calibration > float(limits["max_calibration_error"]):
        fail("calibration_drift", "calibration error is missing or exceeds threshold")
    try: drawdown = float(snapshot["daily_drawdown"])
    except (KeyError, TypeError, ValueError): drawdown = None
    if drawdown is None or drawdown < 0 or drawdown > float(limits["max_daily_drawdown"]):
        fail("drawdown_limit", "daily drawdown is missing or exceeds threshold")

    reasons.sort(key=lambda item: (str(item["code"]), str(item["detail"])))
    return {"allow_trading": not reasons, "reason_codes": [r["code"] for r in reasons],
            "reasons": reasons, "thresholds": {k: limits[k] for k in sorted(limits)}}

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    snapshot = json.loads(args.snapshot.read_text())
    result = evaluate(snapshot, snapshot.get("thresholds") if isinstance(snapshot, Mapping) else None)
    text = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True); args.output.write_text(text)
    else: print(text, end="")

if __name__ == "__main__": main()

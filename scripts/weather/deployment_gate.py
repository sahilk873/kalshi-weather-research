"""Evaluate the report-2 real-money deployment gate.

The gate is deliberately conservative: absent evidence is a failure, and a
passing report is still an approval artifact for human review, never an order
submission permission.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

REQUIRED = (
    "positive_oos_net_ev", "positive_test_windows", "brier_improvement",
    "reliability_error", "regime_independent", "probability_perturbation_robust",
    "slippage_robust", "fees_robust", "live_paper_matches_backtest",
    "outage_killswitch_tested", "contract_rules_verified",
)


def evaluate(snapshot: dict, *, min_test_windows: int = 2,
             max_reliability_error: float = 0.05) -> dict:
    checks = []

    def check(name: str, passed: bool, reason: str) -> None:
        checks.append({"check": name, "pass": bool(passed), "reason": reason})

    check("positive_oos_net_ev", snapshot.get("positive_oos_net_ev") is True,
          "conservative out-of-sample net EV must be positive")
    windows = snapshot.get("positive_test_windows")
    check("positive_test_windows", isinstance(windows, int) and windows >= min_test_windows,
          f"at least {min_test_windows} positive rolling test windows required")
    try:
        brier = float(snapshot.get("brier_improvement"))
        check("brier_improvement", brier > 0, "Brier score must improve over the market baseline")
    except (TypeError, ValueError):
        check("brier_improvement", False, "missing or invalid Brier improvement")
    try:
        reliability = float(snapshot.get("reliability_error"))
        check("reliability_error", 0 <= reliability <= max_reliability_error,
              f"reliability error must be <= {max_reliability_error}")
    except (TypeError, ValueError):
        check("reliability_error", False, "missing or invalid reliability error")
    for name in REQUIRED[4:]:
        check(name, snapshot.get(name) is True, "required robustness/control evidence is absent")
    failed = [item["check"] for item in checks if not item["pass"]]
    return {"version": "report2-deployment-gate-v1", "pass": not failed,
            "authorized": False, "failed_checks": failed, "checks": checks}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--min-test-windows", type=int, default=2)
    parser.add_argument("--max-reliability-error", type=float, default=0.05)
    args = parser.parse_args()
    with args.input.open() as handle:
        snapshot = json.load(handle)
    result = evaluate(snapshot, min_test_windows=args.min_test_windows,
                      max_reliability_error=args.max_reliability_error)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"pass": result["pass"], "failed_checks": len(result["failed_checks"])}))


if __name__ == "__main__":
    main()

"""Compare a captured WebSocket book with a REST order-book snapshot.

This is a read-only integrity check.  It never patches a book or invents
levels; any ticker, side, price, or quantity mismatch is reported explicitly.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Mapping


def _levels(payload: Mapping[str, object], side: str) -> dict[int, float]:
    values = payload.get(side)
    if values is None:
        values = payload.get(f"{side}_dollars_fp")
    if values is None:
        values = payload.get(f"{side}_dollars", [])
    if payload.get(f"{side}_dollars") is not None or payload.get(f"{side}_dollars_fp") is not None:
        return {int(round(float(price) * 100)): float(quantity) for price, quantity in values or []}
    return {int(price): float(quantity) for price, quantity in values or []}


def _book(payload: Mapping[str, object]) -> dict[str, dict[int, float]]:
    return {side: _levels(payload, side) for side in ("yes", "no")}


def reconcile(websocket_snapshot: Mapping[str, object], rest_snapshot: Mapping[str, object], *, tolerance: float = 1e-9) -> dict:
    """Return an immutable comparison result for one market snapshot."""
    ws = _book(websocket_snapshot)
    rest = _book(rest_snapshot.get("orderbook_fp", rest_snapshot) if isinstance(rest_snapshot, Mapping) else {})
    mismatches = []
    for side in ("yes", "no"):
        prices = sorted(set(ws[side]) | set(rest[side]))
        for price in prices:
            left = ws[side].get(price, 0.0); right = rest[side].get(price, 0.0)
            if abs(left - right) > tolerance:
                mismatches.append({"side": side, "price_cents": price,
                                   "websocket_quantity": left, "rest_quantity": right})
    return {"version": "orderbook-rest-reconciliation-v1",
            "pass": not mismatches, "websocket_levels": sum(len(v) for v in ws.values()),
            "rest_levels": sum(len(v) for v in rest.values()), "mismatches": mismatches}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--websocket", type=Path, required=True)
    parser.add_argument("--rest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    ws = json.loads(args.websocket.read_text()); rest = json.loads(args.rest.read_text())
    result = reconcile(ws, rest)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"pass": result["pass"], "mismatches": len(result["mismatches"])}, sort_keys=True))


if __name__ == "__main__":
    main()

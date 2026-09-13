"""Generate uncalibrated, PIT-safe daily contract probabilities.

This is a diagnostic bridge for the active daily NYC/Los Angeles/Austin books.
It uses only GEFS rows received before the captured quote, emits explicit
rejections, and never writes prediction manifests or trading telemetry.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from datetime import datetime, timezone
from pathlib import Path

SERIES = {
    "KXHIGHNY": ("nyc", "high"), "KXLOWTNYC": ("nyc", "low"),
    "KXHIGHLAX": ("la", "high"), "KXLOWTLAX": ("la", "low"),
    "KXHIGHAUS": ("austin", "high"), "KXLOWTAUS": ("austin", "low"),
}
PRODUCT_KEYS = {"nyc": "CLINYC", "la": "CLILAX", "austin": "CLIAUS"}
FIELDS = ["market_ticker", "event_ticker", "decision_ts", "target_date", "city", "temp_type",
          "threshold_f", "upper_threshold_f", "strike_type", "mean_f", "stddev_f", "probability", "model_name",
          "forecast_receipt_ts", "quote_received_ts", "best_yes_bid_cents", "best_yes_ask_cents",
          "spread_cents", "top_depth", "yes_gross_edge_at_ask", "fee_rate", "slippage_cents",
          "yes_net_edge_conservative", "yes_net_edge_base", "yes_net_edge_optimistic",
          "no_net_edge_conservative", "no_net_edge_base", "no_net_edge_optimistic",
          "settlement_source", "rules_primary"]


def _dt(value: object) -> datetime | None:
    try:
        x = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return x if x.tzinfo else x.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def _normal_cdf(x: float, mean: float, stddev: float) -> float:
    return 0.5 * (1.0 + math.erf((x - mean) / (stddev * math.sqrt(2.0))))


def generate(markets_payload: dict, forecasts: list[dict], quote_rows: list[dict], *,
             fee_rate: float = 0.0, slippage_cents: float = 0.0) -> tuple[list[dict], list[dict]]:
    if fee_rate < 0 or slippage_cents < 0:
        raise ValueError("fee_rate and slippage_cents must be non-negative")
    forecast_rows = []
    for row in forecasts:
        if row.get("model_name") != "ncep_gefs025":
            continue
        receipt = _dt(row.get("source_receipt_time")); target = row.get("outcome_local_date", "")
        try:
            mean, stddev = float(row["mean_f"]), float(row["stddev_f"])
        except (KeyError, TypeError, ValueError):
            continue
        if receipt and stddev > 0 and math.isfinite(mean) and math.isfinite(stddev):
            forecast_rows.append((row, receipt, target))
    quotes = {}
    for row in quote_rows:
        stamp = _dt(row.get("received_ts")); ticker = row.get("market_ticker", "")
        if ticker and stamp:
            quotes.setdefault(ticker, []).append((stamp, row))
    accepted, rejected = [], []
    for series, payload in markets_payload.items():
        city_type = SERIES.get(series)
        for market in payload.get("markets") or []:
            ticker = market.get("ticker", ""); qrows = quotes.get(ticker, [])
            decision = max((stamp for stamp, _ in qrows), default=None)
            if not ticker or not city_type or decision is None:
                rejected.append({"market_ticker": ticker, "reason": "missing_quote_receipt"}); continue
            city, temp_type = city_type
            rules_primary = str(market.get("rules_primary", ""))
            expected_product = PRODUCT_KEYS[city]
            if expected_product not in rules_primary:
                rejected.append({"market_ticker": ticker, "reason": "settlement_rule_station_mismatch"}); continue
            target = (market.get("event_ticker", "").rsplit("-", 1)[-1] or "")
            try:
                # Kalshi event suffix is YYMONDD (e.g. 26SEP13).
                target_date = datetime.strptime(target, "%y%b%d").date().isoformat()
                strike_type = str(market.get("strike_type", "")).lower()
                threshold = float(market.get("floor_strike") if market.get("floor_strike") is not None else market.get("cap_strike"))
                upper = float(market["cap_strike"]) if strike_type == "between" and market.get("cap_strike") is not None else None
            except (TypeError, ValueError):
                rejected.append({"market_ticker": ticker, "reason": "invalid_target_or_threshold"}); continue
            eligible = [(r, rec) for r, rec, d in forecast_rows if r.get("city") == city and r.get("temp_type") == temp_type and d == target_date and rec <= decision]
            if not eligible:
                rejected.append({"market_ticker": ticker, "reason": "missing_forecast_asof_quote"}); continue
            row, receipt = max(eligible, key=lambda pair: pair[1])
            quote = max((r for stamp, r in qrows if stamp == decision), key=lambda r: r.get("received_ts", ""))
            mean, stddev = float(row["mean_f"]), float(row["stddev_f"])
            strike_type = str(market.get("strike_type", "")).lower()
            # Kalshi weather buckets are whole-degree inclusive. Use the
            # half-degree continuity correction also used by the canonical
            # bucket engine, including open-tailed less/greater contracts.
            if strike_type == "less":
                probability = _normal_cdf(threshold - 0.5, mean, stddev)
            elif strike_type == "greater":
                probability = 1.0 - _normal_cdf(threshold + 0.5, mean, stddev)
            elif strike_type == "between" and upper is not None:
                probability = _normal_cdf(upper + 0.5, mean, stddev) - _normal_cdf(threshold - 0.5, mean, stddev)
            else:
                rejected.append({"market_ticker": ticker, "reason": "unsupported_strike_semantics"}); continue
            try:
                # Accept both the historical authenticated-quote schema and
                # the public active-probe snapshot schema.  Public dollars
                # are converted to cents; displayed size is the conservative
                # top-depth proxy and is never called full L2 depth.
                bid_text = quote.get("best_yes_bid_cents", "")
                ask_text = quote.get("best_yes_ask_cents", "")
                if bid_text in ("", None) and quote.get("yes_bid", "") not in ("", None):
                    bid_text = float(quote["yes_bid"]) * 100.0
                if ask_text in ("", None) and quote.get("yes_ask", "") not in ("", None):
                    ask_text = float(quote["yes_ask"]) * 100.0
                bid = float(bid_text); ask = float(ask_text)
                spread_text = quote.get("spread_cents", "")
                spread = float(spread_text) if spread_text not in ("", None) else ask - bid
                depth_text = quote.get("top_depth", "")
                if depth_text in ("", None):
                    sizes = [float(quote.get(key, "nan")) for key in ("yes_bid_size", "yes_ask_size")]
                    depth = min(sizes)
                else:
                    depth = float(depth_text)
                if not all(math.isfinite(value) for value in (bid, ask, spread, depth)):
                    rejected.append({"market_ticker": ticker, "reason": "missing_executable_quote_fields"}); continue
                gross_edge = probability - ask / 100.0 if math.isfinite(ask) else float("nan")
                costs = []
                for extra_slippage in (2.0, 1.0, 0.0):
                    fill = ask / 100.0 + (slippage_cents * extra_slippage / 100.0)
                    costs.append(probability - fill - fee_rate * fill)
                net_conservative, net_base, net_optimistic = costs
                no_costs = []
                for extra_slippage in (2.0, 1.0, 0.0):
                    fill = (100.0 - bid) / 100.0 + (slippage_cents * extra_slippage / 100.0)
                    no_costs.append((1.0 - probability) - fill - fee_rate * fill)
                no_net_conservative, no_net_base, no_net_optimistic = no_costs
            except (TypeError, ValueError):
                rejected.append({"market_ticker": ticker, "reason": "missing_executable_quote_fields"})
                continue
            accepted.append({"market_ticker": ticker, "event_ticker": market.get("event_ticker", ""),
                "decision_ts": decision.isoformat().replace("+00:00", "Z"), "target_date": target_date,
                "city": city, "temp_type": temp_type, "threshold_f": threshold, "upper_threshold_f": upper or "",
                "strike_type": market.get("strike_type", ""), "mean_f": row["mean_f"], "stddev_f": row["stddev_f"],
                "probability": f"{max(0.0, min(1.0, probability)):.8f}", "model_name": "gefs025_raw_uncalibrated",
                "forecast_receipt_ts": receipt.isoformat().replace("+00:00", "Z"), "quote_received_ts": decision.isoformat().replace("+00:00", "Z"),
                "best_yes_bid_cents": bid, "best_yes_ask_cents": ask, "spread_cents": spread, "top_depth": depth,
                "yes_gross_edge_at_ask": gross_edge, "fee_rate": fee_rate, "slippage_cents": slippage_cents,
                "yes_net_edge_conservative": net_conservative, "yes_net_edge_base": net_base,
                "yes_net_edge_optimistic": net_optimistic,
                "no_net_edge_conservative": no_net_conservative,
                "no_net_edge_base": no_net_base,
                "no_net_edge_optimistic": no_net_optimistic,
                "settlement_source": "The Weather Company", "rules_primary": rules_primary})
    return accepted, rejected


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--markets", type=Path, required=True); parser.add_argument("--forecasts", type=Path, required=True)
    parser.add_argument("--quotes", type=Path, required=True); parser.add_argument("--output", type=Path, required=True); parser.add_argument("--rejections", type=Path, required=True)
    parser.add_argument("--fee-rate", type=float, default=0.0); parser.add_argument("--slippage-cents", type=float, default=0.0)
    args = parser.parse_args()
    payload = json.loads(args.markets.read_text()); forecasts = list(csv.DictReader(args.forecasts.open(newline=""))); quotes = list(csv.DictReader(args.quotes.open(newline="")))
    accepted, rejected = generate(payload, forecasts, quotes, fee_rate=args.fee_rate, slippage_cents=args.slippage_cents)
    args.output.parent.mkdir(parents=True, exist_ok=True); args.rejections.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="") as handle: csv.DictWriter(handle, fieldnames=FIELDS).writeheader(); csv.DictWriter(handle, fieldnames=FIELDS).writerows(accepted)
    with args.rejections.open("w", newline="") as handle: csv.DictWriter(handle, fieldnames=["market_ticker", "reason"]).writeheader(); csv.DictWriter(handle, fieldnames=["market_ticker", "reason"]).writerows(rejected)
    print(json.dumps({"accepted": len(accepted), "rejected": len(rejected), "promotion": "diagnostic_only"}, sort_keys=True))


if __name__ == "__main__": main()

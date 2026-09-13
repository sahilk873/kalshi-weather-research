"""Conservative, research-only execution scenarios from Kalshi candles.

The signal uses the last fully closed candle at or before ``decision_time``;
the fill uses only a later candle.  This prevents using the decision candle's
future high/low/close and keeps optimistic fills separate from headline
conservative/base results.
"""
from __future__ import annotations

import argparse, csv, math
from datetime import datetime
from pathlib import Path

def _ts(value: object) -> float | None:
    try:
        if isinstance(value, (int, float)) or str(value).replace(".", "", 1).isdigit(): return float(value)
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError, OverflowError): return None

def simulate(probabilities: list[dict], candles: list[dict], outcomes: list[dict], fee_rate: float = 0.0, slippage_rate: float = 0.0) -> list[dict]:
    books: dict[str, list[dict]] = {}
    for candle in candles:
        ticker = candle.get("market_ticker", candle.get("ticker", "")); stamp = _ts(candle.get("end_period_ts", candle.get("end_period")))
        if ticker and stamp is not None: books.setdefault(ticker, []).append({**candle, "_ts": stamp})
    for rows in books.values(): rows.sort(key=lambda row: row["_ts"])
    labels = {row.get("market_ticker", row.get("ticker", "")): str(row.get("settled_yes", row.get("result", ""))).lower() in {"yes", "true", "1"} for row in outcomes}
    output = []
    for signal in probabilities:
        ticker = signal.get("market_ticker", signal.get("ticker", "")); decision = _ts(signal.get("decision_time_utc", signal.get("decision_time")))
        try: fair = float(signal.get("bucket_probability", signal.get("fair_probability", signal.get("probability"))))
        except (TypeError, ValueError): continue
        if not ticker or decision is None or not 0 <= fair <= 1: continue
        rows = books.get(ticker, []); prior = [row for row in rows if row["_ts"] <= decision]; later = [row for row in rows if row["_ts"] > decision]
        if not prior or not later: continue
        quote, execution = prior[-1], later[0]
        try: ask = float(quote.get("yes_ask_close", "")); nxt_open = float(execution.get("yes_ask_open", "")); nxt_close = float(execution.get("yes_ask_close", "")); nxt_high = float(execution.get("yes_ask_high", ""))
        except (TypeError, ValueError): continue
        if not all(math.isfinite(value) and 0 < value < 1 for value in (ask, nxt_open, nxt_close, nxt_high)): continue
        bid = float(quote.get("yes_bid_close", ask)) if quote.get("yes_bid_close", "") not in ("", None) else ask
        spread = max(0.0, ask - bid)
        for scenario, fill, slip in (("conservative", nxt_high, 0.0), ("base", nxt_close, slippage_rate * spread), ("optimistic", nxt_open, 0.0)):
            price = min(1.0, fill + slip); fee = fee_rate * price; settled = labels.get(ticker)
            payoff = "" if ticker not in labels else ((1.0 - price - fee) if settled else (-price - fee))
            output.append({"market_ticker": ticker, "decision_time_utc": signal.get("decision_time_utc", signal.get("decision_time", "")), "scenario": scenario, "signal_candle_end": int(quote["_ts"]), "execution_candle_end": int(execution["_ts"]), "fair_probability": f"{fair:.8f}", "signal_yes_ask": f"{ask:.8f}", "signal_yes_bid": f"{bid:.8f}", "fill_price": f"{price:.8f}", "fee": f"{fee:.8f}", "gross_edge": f"{fair-price:.8f}", "no_side_executable_cost": f"{1.0-bid:.8f}", "no_side_gross_edge": f"{bid-fair:.8f}", "settled_yes": "" if settled is None else str(settled).lower(), "one_contract_net_payoff": "" if payoff == "" else f"{payoff:.8f}"})
    return output

def summarize(rows: list[dict], signal_count: int | None = None) -> dict[str, dict[str, float]]:
    """Return scenario-level financial diagnostics without inventing missing fills.

    Sharpe and Sortino are per-trade diagnostics (no annualization is implied);
    ``fill_rate`` is the fraction of input signal rows represented by a
    scenario when ``signal_count`` is available, otherwise it is explicitly
    reported as the observed-row fraction.
    """
    result: dict[str, dict[str, float]] = {}
    if signal_count is None:
        signal_count = len({row.get("market_ticker", "") + "|" + row.get("decision_time_utc", "") for row in rows})
    if signal_count < 0:
        raise ValueError("signal_count cannot be negative")
    for scenario in {row["scenario"] for row in rows}:
        subset = [row for row in rows if row["scenario"] == scenario and row["one_contract_net_payoff"] != ""]
        payoffs = [float(row["one_contract_net_payoff"]) for row in subset]
        mean = sum(payoffs) / len(payoffs) if payoffs else 0.0
        variance = sum((value - mean) ** 2 for value in payoffs) / (len(payoffs) - 1) if len(payoffs) > 1 else 0.0
        downside = [min(0.0, value) for value in payoffs]
        downside_dev = math.sqrt(sum(value * value for value in downside) / len(downside)) if downside else 0.0
        running = peak = drawdown = 0.0
        for value in payoffs:
            running += value; peak = max(peak, running); drawdown = max(drawdown, peak - running)
        wins = sum(value > 0 for value in payoffs)
        turnover = sum(float(row.get("fill_price", 0.0) or 0.0) for row in subset)
        result[scenario] = {"rows": len(subset), "net_payoff": sum(payoffs),
                            "mean_payoff": mean, "std_payoff": math.sqrt(variance),
                            "sharpe_per_trade": mean / math.sqrt(variance) if variance > 0 else 0.0,
                            "sortino_per_trade": mean / downside_dev if downside_dev > 0 else 0.0,
                            "max_drawdown": drawdown, "wins": wins,
                            "win_rate": wins / len(payoffs) if payoffs else 0.0,
                            "turnover": turnover,
                            "fill_rate": len(subset) / signal_count if signal_count else 0.0}
    return result

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument("--probabilities", type=Path, required=True); parser.add_argument("--candles", type=Path, required=True); parser.add_argument("--outcomes", type=Path, required=True); parser.add_argument("--fee-rate", type=float, default=0.0); parser.add_argument("--slippage-rate", type=float, default=0.0); parser.add_argument("--output", type=Path, required=True); args = parser.parse_args()
    def read(path):
        with path.open(newline="") as handle: return list(csv.DictReader(handle))
    probabilities = read(args.probabilities)
    rows = simulate(probabilities, read(args.candles), read(args.outcomes), args.fee_rate, args.slippage_rate); args.output.parent.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0]) if rows else ["market_ticker", "scenario"]
    with args.output.open("w", newline="") as handle: writer = csv.DictWriter(handle, fieldnames=fields); writer.writeheader(); writer.writerows(rows)
    print(summarize(rows, signal_count=len(probabilities)))

if __name__ == "__main__": main()

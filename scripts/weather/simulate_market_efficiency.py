"""Research-only market-efficiency analysis from PIT probabilities and candles.

This module never submits orders. It estimates executable ask-side edge and
settled payoff using the last candle available at each decision timestamp.
"""
from __future__ import annotations
import argparse, csv
from datetime import datetime, timezone
from pathlib import Path

def _ts(value: str) -> float | None:
    try: return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except (ValueError, TypeError, AttributeError): return None

def analyze(probabilities: list[dict], candles: list[dict], outcomes: list[dict], *,
            min_edge: float = 0.0, fee_rate: float = 0.0,
            slippage_reserve: float = 0.0) -> list[dict]:
    by_market: dict[str, list[dict]] = {}
    for row in candles:
        market = row.get("market_ticker", ""); end = _ts(row.get("end_period_ts", ""))
        if end is None:
            try: end = float(row["end_period_ts"])
            except (KeyError, TypeError, ValueError): continue
        row = {**row, "_end": end}; by_market.setdefault(market, []).append(row)
    for rows in by_market.values(): rows.sort(key=lambda r: r["_end"])
    settled = {r.get("market_ticker", ""): str(r.get("settled_yes", "")).lower() in {"yes", "true", "1"} for r in outcomes}
    result=[]
    for row in probabilities:
        market=row.get("market_ticker", ""); decision=_ts(row.get("decision_time_utc", ""));
        try: fair=float(row["bucket_probability"])
        except (KeyError,TypeError,ValueError): continue
        if not market or decision is None: continue
        prior=[c for c in by_market.get(market, []) if c["_end"] <= decision]
        if not prior: continue
        candle=prior[-1]
        try:
            ask=float(candle.get("yes_ask_close", ""))
            bid=float(candle.get("yes_bid_close", ask) or ask)
        except (TypeError,ValueError): continue
        if not 0 < ask < 1: continue
        outcome=settled.get(market)
        yes_cost = min(1.0, ask + slippage_reserve + fee_rate * ask)
        no_cost = max(0.0, 1.0 - bid + slippage_reserve + fee_rate * (1.0 - bid))
        yes_edge, no_edge = fair - yes_cost, (1.0 - fair) - no_cost
        result.append({"market_ticker":market,"event_ticker":row.get("event_ticker", ""),"city":row.get("city", ""),"temp_type":row.get("temp_type", ""),"decision_time_utc":row.get("decision_time_utc", ""),"fair_probability":f"{fair:.8f}","yes_ask":f"{ask:.8f}","yes_bid":f"{bid:.8f}","gross_edge":f"{fair-ask:.8f}","yes_edge_after_cost":f"{yes_edge:.8f}","no_edge_after_cost":f"{no_edge:.8f}","triggered":str(max(yes_edge, no_edge) >= min_edge).lower(),"settled_yes": "" if outcome is None else str(outcome).lower(),"candle_end_period_ts":str(int(candle["_end"]))})
    return result

def summarize(rows: list[dict], fee_rate: float = 0.0) -> dict[str, float]:
    settled = [r for r in rows if r.get("settled_yes") in {"true", "false"}]
    edges = [float(r["gross_edge"]) for r in rows]
    payoff = []
    for row in settled:
        ask = float(row["yes_ask"]); won = row["settled_yes"] == "true"
        payoff.append((1 - ask if won else -ask) - fee_rate * ask)
    triggered = [r for r in rows if r.get("triggered", "true") == "true"]
    return {"candidates": float(len(rows)), "triggered_candidates": float(len(triggered)), "settled_candidates": float(len(settled)), "hit_rate": sum(r["settled_yes"] == "true" for r in settled) / len(settled) if settled else float("nan"), "mean_gross_edge": sum(edges) / len(edges) if edges else float("nan"), "mean_yes_edge_after_cost": sum(float(r.get("yes_edge_after_cost", 0.0)) for r in rows) / len(rows) if rows else float("nan"), "mean_no_edge_after_cost": sum(float(r.get("no_edge_after_cost", 0.0)) for r in rows) / len(rows) if rows else float("nan"), "one_contract_net_payoff": sum(payoff) if payoff else float("nan")}

def main() -> None:
    p=argparse.ArgumentParser(description=__doc__); p.add_argument("--probabilities",type=Path,required=True); p.add_argument("--candles",type=Path,required=True); p.add_argument("--outcomes",type=Path,required=True); p.add_argument("--output",type=Path,required=True); p.add_argument("--min-edge",type=float,default=0.0); p.add_argument("--fee-rate",type=float,default=0.0); p.add_argument("--slippage-reserve",type=float,default=0.0); a=p.parse_args()
    def read(path):
        with path.open(newline="") as f: return list(csv.DictReader(f))
    rows=analyze(read(a.probabilities),read(a.candles),read(a.outcomes), min_edge=a.min_edge, fee_rate=a.fee_rate, slippage_reserve=a.slippage_reserve); a.output.parent.mkdir(parents=True,exist_ok=True)
    fields=list(rows[0]) if rows else ["market_ticker"]
    with a.output.open("w",newline="") as f: w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(rows)
    print(f"wrote {a.output} ({len(rows)} rows)")
if __name__ == "__main__": main()

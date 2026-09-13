"""Research-only capped fractional-Kelly sizing for binary contracts."""
from __future__ import annotations
import argparse, csv, math, random
from pathlib import Path

def size(probability: float, price: float, bankroll: float, fraction: float = 0.25, max_loss_fraction: float = 0.01, max_allocation_fraction: float = 0.05, fee_rate: float = 0.0) -> dict[str, float]:
    if not 0 < probability < 1 or not 0 < price < 1 or bankroll <= 0 or fee_rate < 0 or price * (1 + fee_rate) >= 1 or not 0 <= fraction <= 1 or not 0 <= max_loss_fraction <= max_allocation_fraction:
        raise ValueError("invalid probability, price, bankroll, or risk limits")
    net_price = price + fee_rate * price
    b = (1 - net_price) / net_price
    kelly = max(0.0, (probability * b - (1 - probability)) / b)
    allocation = min(bankroll * fraction * kelly, bankroll * max_allocation_fraction)
    contracts = math.floor(allocation / net_price)
    loss = contracts * net_price
    contracts = min(contracts, math.floor(bankroll * max_loss_fraction / net_price))
    return {"kelly_fraction": kelly, "allocation_dollars": contracts * net_price,
            "contracts": float(contracts), "max_loss_dollars": bankroll * max_loss_fraction,
            "position_loss_dollars": contracts * net_price,
            "edge": probability - price, "net_edge": probability - net_price}

def allocate_event(candidates: list[dict[str, float]], bankroll: float, max_loss_fraction: float = 0.01) -> list[dict[str, float]]:
    """Allocate mutually exclusive contracts under one shared event loss cap."""
    cap = bankroll * max_loss_fraction
    scored = []
    for candidate in candidates:
        result = size(candidate["probability"], candidate["price"], bankroll, fraction=1.0, max_loss_fraction=max_loss_fraction, max_allocation_fraction=1.0, fee_rate=candidate.get("fee_rate", 0.0))
        result["market_ticker"] = candidate.get("market_ticker", "")
        scored.append((result, candidate))
    total = sum(result["allocation_dollars"] for result, _ in scored)
    if total > cap and total > 0:
        scale = cap / total
        for result, candidate in scored:
            result["allocation_dollars"] *= scale
            net_price = candidate["price"] * (1 + candidate.get("fee_rate", 0.0))
            result["contracts"] = float(math.floor(result["allocation_dollars"] / net_price))
            result["allocation_dollars"] = result["contracts"] * net_price
            result["position_loss_dollars"] = result["allocation_dollars"]
    return [result for result, _ in scored]


def max_drawdown(returns: list[float]) -> float:
    """Return the fractional peak-to-trough drawdown of a return path."""
    equity = peak = 1.0
    drawdown = 0.0
    for value in returns:
        equity *= 1.0 + value
        peak = max(peak, equity)
        if peak > 0:
            drawdown = max(drawdown, 1.0 - equity / peak)
    return drawdown


def block_bootstrap(
    returns: list[float], simulations: int = 1000, block_size: int = 5,
    seed: int = 0,
) -> dict[str, float]:
    """Estimate terminal-return and drawdown tails with moving blocks.

    This is an inference diagnostic, not a backtest. Returns must already be
    point-in-time and aligned to settled trades; no missing values are
    imputed. The deterministic seed makes the report reproducible.
    """
    if not returns or simulations <= 0 or block_size <= 0:
        raise ValueError("returns must be non-empty; simulations/block_size must be positive")
    if any(not math.isfinite(value) or value <= -1 for value in returns):
        raise ValueError("returns must be finite and greater than -1")
    rng = random.Random(seed)
    n = len(returns)
    terminal: list[float] = []
    drawdowns: list[float] = []
    for _ in range(simulations):
        sample: list[float] = []
        while len(sample) < n:
            start = rng.randrange(n)
            sample.extend(returns[start:start + block_size])
            if len(sample) < n and start + block_size > n:
                sample.extend(returns[:block_size - (n - start)])
        sample = sample[:n]
        equity = math.prod(1.0 + value for value in sample)
        terminal.append(equity - 1.0)
        drawdowns.append(max_drawdown(sample))
    terminal.sort(); drawdowns.sort()
    def quantile(values: list[float], q: float) -> float:
        return values[min(len(values) - 1, max(0, int(q * (len(values) - 1))))]
    return {
        "observations": float(n), "simulations": float(simulations),
        "block_size": float(block_size), "terminal_return_p05": quantile(terminal, .05),
        "terminal_return_median": quantile(terminal, .50),
        "max_drawdown_p95": quantile(drawdowns, .95),
        "probability_of_loss": sum(value < 0 for value in terminal) / simulations,
    }

def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--probability", type=float)
    p.add_argument("--price", type=float)
    p.add_argument("--bankroll", type=float)
    p.add_argument("--fraction", type=float, default=.25)
    p.add_argument("--max-loss-fraction", type=float, default=.01)
    p.add_argument("--max-allocation-fraction", type=float, default=.05)
    p.add_argument("--fee-rate", type=float, default=0.0)
    p.add_argument("--returns", type=Path, help="CSV containing settled returns for block bootstrap")
    p.add_argument("--return-field", default="return")
    p.add_argument("--simulations", type=int, default=1000)
    p.add_argument("--block-size", type=int, default=5)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    if a.returns:
        with a.returns.open(newline="") as fh:
            values = [float(row[a.return_field]) for row in csv.DictReader(fh)]
        result = block_bootstrap(values, a.simulations, a.block_size, a.seed)
    else:
        if a.probability is None or a.price is None or a.bankroll is None:
            p.error("--probability, --price, and --bankroll are required unless --returns is used")
        result = size(a.probability, a.price, a.bankroll, a.fraction,
                      a.max_loss_fraction, a.max_allocation_fraction, a.fee_rate)
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(__import__('json').dumps(result, indent=2) + "\n")
    print(result)
if __name__ == "__main__": main()

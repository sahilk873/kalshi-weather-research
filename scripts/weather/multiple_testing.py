"""Dependence-aware max-statistic checks for comparing many strategies.

This is a transparent White-Reality-Check-style diagnostic: returns are
centered under the no-positive-edge null, then resampled in moving blocks and
the maximum studentized mean is retained on every draw. It is not a formal
implementation of Hansen's SPA or the Deflated Sharpe Ratio.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import random
from pathlib import Path


def _stat(values: list[float]) -> float:
    mean = sum(values) / len(values)
    variance = sum((value - mean) ** 2 for value in values) / max(1, len(values) - 1)
    deviation = math.sqrt(variance)
    return mean / deviation * math.sqrt(len(values)) if deviation else (math.inf if mean > 0 else 0.0)


def reality_check(
    strategies: dict[str, list[float]], simulations: int = 2000,
    block_size: int = 5, seed: int = 0,
) -> dict[str, object]:
    """Return observed best strategy and a block-bootstrap max-stat p-value."""
    if not strategies or simulations <= 0 or block_size <= 0:
        raise ValueError("strategies must be non-empty; simulations/block_size must be positive")
    names = list(strategies)
    lengths = {len(values) for values in strategies.values()}
    if len(lengths) != 1 or not next(iter(lengths), 0):
        raise ValueError("all strategies must have the same non-empty length")
    n = next(iter(lengths))
    if any(not math.isfinite(value) for values in strategies.values() for value in values):
        raise ValueError("strategy returns must be finite")
    observed = {name: _stat(list(values)) for name, values in strategies.items()}
    best_name = max(names, key=lambda name: observed[name])
    best_stat = observed[best_name]
    centered = {name: [value - sum(values) / n for value in values]
                for name, values in strategies.items()}
    rng = random.Random(seed)
    exceed = 0
    for _ in range(simulations):
        indices: list[int] = []
        while len(indices) < n:
            start = rng.randrange(n)
            indices.extend((start + offset) % n for offset in range(block_size))
        indices = indices[:n]
        simulated = max(_stat([centered[name][index] for index in indices]) for name in names)
        if simulated >= best_stat:
            exceed += 1
    return {
        "strategies": names, "observations": n, "simulations": simulations,
        "block_size": block_size, "best_strategy": best_name,
        "observed_studentized_mean": best_stat,
        "observed_studentized_means": observed,
        "max_statistic_p_value": exceed / simulations,
        "method": "centered_moving_block_max_statistic",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True,
                        help="CSV with strategy and return columns")
    parser.add_argument("--strategy-field", default="strategy")
    parser.add_argument("--return-field", default="return")
    parser.add_argument("--simulations", type=int, default=2000)
    parser.add_argument("--block-size", type=int, default=5)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    strategies: dict[str, list[float]] = {}
    with args.input.open(newline="") as handle:
        for row in csv.DictReader(handle):
            strategies.setdefault(row[args.strategy_field], []).append(float(row[args.return_field]))
    result = reality_check(strategies, args.simulations, args.block_size, args.seed)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()

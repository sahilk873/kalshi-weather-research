"""Build GEFS distribution features and optional Kalshi price joins."""
from __future__ import annotations

import argparse
import csv
import math
import sys
from collections import defaultdict
from pathlib import Path

_SELF = Path(__file__).resolve().parent
sys.path.insert(0, str(_SELF))
from common import ensure_runtime_dirs  # noqa: E402

DEFAULT_THRESHOLDS = (78, 80, 82, 85, 90)
KEY = ("forecast_run_time", "valid_time", "city_key", "model")


def read_members(path: Path) -> list[dict]:
    import pyarrow.parquet as pq
    return pq.read_table(path).to_pylist()


def _quantile(values: list[float], q: float) -> float:
    values = sorted(values)
    if len(values) == 1:
        return values[0]
    pos = (len(values) - 1) * q
    lo, hi = math.floor(pos), math.ceil(pos)
    return values[lo] + (values[hi] - values[lo]) * (pos - lo)


def build_features(rows: list[dict], thresholds=DEFAULT_THRESHOLDS) -> list[dict]:
    groups: dict[tuple, dict[str, float]] = defaultdict(dict)
    city_names: dict[tuple, str] = {}
    for row in rows:
        if row.get("variable") != "temperature_2m":
            continue
        group_key = tuple(row.get(k) for k in KEY)
        groups[group_key][row["member_id"]] = float(row["value"])
        city_names[group_key] = row.get("city", "")
    output = []
    for key, members in sorted(groups.items()):
        values = list(members.values())
        mean = sum(values) / len(values)
        spread = math.sqrt(sum((v - mean) ** 2 for v in values) / len(values))
        row = dict(zip(KEY, key))
        row.update({"city": city_names[key], "variable": "temperature_2m",
                    "member_count": len(values), "ensemble_mean": mean,
                    "ensemble_spread": spread, "p10": _quantile(values, .10),
                    "p25": _quantile(values, .25), "median": _quantile(values, .50),
                    "p75": _quantile(values, .75), "p90": _quantile(values, .90)})
        # Keep each threshold as a stable, queryable column for contract joins.
        for threshold in thresholds:
            row[f"prob_ge_{threshold:g}"] = sum(v >= threshold for v in values) / len(values)
        output.append(row)
    return output


def write_parquet(rows: list[dict], path: Path) -> None:
    import pyarrow as pa
    import pyarrow.parquet as pq
    pq.write_table(pa.Table.from_pylist(rows), path, compression="zstd")


def join_kalshi(features: list[dict], markets_path: Path, output: Path) -> int:
    """Join a market snapshot by exact ticker/time when available.

    This deliberately does not infer historical order-book probabilities from
    closing prices.  ``market_probability`` must come from an observed YES
    price column in the supplied file.
    """
    with markets_path.open(newline="") as fh:
        market_rows = list(csv.DictReader(fh))
    out = []
    for market in market_rows:
        price = market.get("yes_price_dollars") or market.get("yes_price")
        if not price:
            continue
        floor = market.get("bucket_floor_f")
        if floor in (None, ""):
            continue
        for feature in features:
            if feature["city"].lower() != market.get("city", "").lower():
                continue
            threshold = float(floor)
            column = f"prob_ge_{threshold:g}"
            if column not in feature:
                continue
            probability = float(feature[column])
            market_probability = float(price)
            out.append({"timestamp": market.get("created_time") or market.get("timestamp"),
                        "ticker": market.get("market_ticker") or market.get("ticker"),
                        "gefs_probability": probability,
                        "market_probability": market_probability,
                        "edge": probability - market_probability,
                        "forecast_run_time": feature["forecast_run_time"],
                        "valid_time": feature["valid_time"], "threshold": threshold})
    if out:
        with output.open("w", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(out[0]))
            writer.writeheader(); writer.writerows(out)
    return len(out)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input", type=Path, default=None)
    ap.add_argument("--output", type=Path, default=None)
    ap.add_argument("--markets", type=Path, default=None)
    ap.add_argument("--join-output", type=Path, default=None)
    ap.add_argument("--thresholds", nargs="+", type=float, default=list(DEFAULT_THRESHOLDS))
    args = ap.parse_args()
    d = ensure_runtime_dirs()
    source = args.input or d["gefs"] / "gefs_members.parquet"
    output = args.output or d["gefs"] / "gefs_features.parquet"
    features = build_features(read_members(source), args.thresholds)
    write_parquet(features, output)
    print(f"wrote {len(features)} ensemble feature rows to {output}")
    if args.markets:
        joined = args.join_output or d["gefs"] / "kalshi_gefs_edges.csv"
        print(f"wrote {join_kalshi(features, args.markets, joined)} Kalshi joins to {joined}")


if __name__ == "__main__":
    main()

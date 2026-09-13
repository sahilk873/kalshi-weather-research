"""Compare GHCNh and IEM ASOS temperatures at matching station/times."""
from __future__ import annotations
import argparse, csv, json, math
from pathlib import Path

STATION_ALIASES = {
    "USW00023183": "PHX", "USW00023169": "LAS", "USW00094728": "NYC",
    "USW00023174": "LAX", "USW00013958": "AUS",
}


def compare(ghcnh_path: Path, asos_path: Path) -> dict:
    with ghcnh_path.open(newline="") as handle:
        gh = {(STATION_ALIASES.get(r["station"], r["station"]), r["valid_utc"]): r for r in csv.DictReader(handle)}
    with asos_path.open(newline="") as handle:
        ao = {(r["station"], r["valid_utc"]): r for r in csv.DictReader(handle)}
    deltas = []
    for key in sorted(set(gh) & set(ao)):
        try:
            a = float(ao[key]["tmpf"]); g = float(gh[key]["temperature_f"])
        except (TypeError, ValueError):
            continue
        if math.isfinite(a) and math.isfinite(g):
            deltas.append(g - a)
    summary = {
        "ghcnh_rows": len(gh), "asos_rows": len(ao),
        "matching_keys": len(set(gh) & set(ao)), "numeric_matches": len(deltas),
        "ghcnh_only": len(set(gh) - set(ao)), "asos_only": len(set(ao) - set(gh)),
        "mean_delta_f": None, "mae_delta_f": None, "max_abs_delta_f": None,
    }
    if deltas:
        summary["mean_delta_f"] = round(sum(deltas) / len(deltas), 4)
        summary["mae_delta_f"] = round(sum(abs(x) for x in deltas) / len(deltas), 4)
        summary["max_abs_delta_f"] = round(max(abs(x) for x in deltas), 4)
    return summary


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--ghcnh", type=Path, required=True)
    p.add_argument("--asos", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args(); result = compare(a.ghcnh, a.asos)
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__": main()

"""Join archived forecast predictions to timestamped actual temperatures."""
from __future__ import annotations
import argparse, csv
from pathlib import Path


def calibrate(predictions: Path, actuals: Path, output: Path) -> int:
    with predictions.open(newline="") as fh: preds = list(csv.DictReader(fh))
    with actuals.open(newline="") as fh: obs = {(r["city_key"], r["valid_time"]): r for r in csv.DictReader(fh)}
    out = []
    for row in preds:
        actual = obs.get((row["city_key"], row["valid_time"]))
        if not actual or not actual.get("temperature"):
            continue
        prediction, observed = float(row["prediction"]), float(actual["temperature"])
        out.append({"model": row["model"], "run_time": row["run_time"],
                    "valid_time": row["valid_time"], "city_key": row["city_key"],
                    "prediction": prediction, "actual": observed,
                    "error": observed - prediction})
    if out:
        with output.open("w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(out[0])); w.writeheader(); w.writerows(out)
    return len(out)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--predictions", type=Path, required=True)
    ap.add_argument("--actuals", type=Path, required=True,
                    help="CSV with city_key,valid_time,temperature")
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    print(f"wrote {calibrate(args.predictions, args.actuals, args.output)} calibrated rows")


if __name__ == "__main__": main()

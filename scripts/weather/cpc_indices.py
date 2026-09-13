"""Fetch and normalize public NOAA CPC ONI climate-regime indices."""
from __future__ import annotations
import argparse, csv
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

URL = "https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt"

def fetch(raw: Path, output: Path) -> int:
    payload = urlopen(Request(URL, headers={"User-Agent": "kalshi-weather-research/1.0"}), timeout=30).read()
    raw.parent.mkdir(parents=True, exist_ok=True); raw.write_bytes(payload)
    rows = []
    for line in payload.decode("ascii", "replace").splitlines():
        parts = line.split()
        if len(parts) != 4 or parts[0] == "SEAS": continue
        try: year = int(parts[1]); total = float(parts[2]); anomaly = float(parts[3])
        except ValueError: continue
        rows.append({"season": parts[0], "year": year, "nino34_3mo_mean_c": total, "oni_anomaly_c": anomaly, "source_url": URL, "retrieved_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")})
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="") as fh:
        fields = list(rows[0]); w = csv.DictWriter(fh, fieldnames=fields); w.writeheader(); w.writerows(rows)
    return len(rows)

def main() -> None:
    p = argparse.ArgumentParser(); p.add_argument("--raw", type=Path, required=True); p.add_argument("--output", type=Path, required=True); a = p.parse_args(); print(f"wrote {fetch(a.raw, a.output)} CPC ONI rows")
if __name__ == "__main__": main()

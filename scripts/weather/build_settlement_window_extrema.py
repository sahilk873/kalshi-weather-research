"""Derive PHX/LV extrema over the NWS local-standard-time settlement window."""
from __future__ import annotations
import argparse, csv
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from settlement_semantics import settlement_standard_time_window

STATIONS = {"USW00023183": "phx", "USW00023169": "lv"}
FIELDS = ["city", "outcome_local_date", "window_start_utc", "window_end_utc", "observation_count", "tmax_f", "tmax_utc", "tmin_f", "tmin_utc", "raw_hashes"]

def build(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    grouped = defaultdict(list)
    for row in rows:
        city = STATIONS.get(row.get("station", ""))
        try: dt = datetime.fromisoformat(row["valid_utc"].replace("Z", "+00:00")); temp = float(row["temperature_f"])
        except (KeyError, ValueError, TypeError): continue
        if not city or dt.tzinfo is None: continue
        # Candidate local-standard dates are adjacent to the observation date.
        for candidate in (dt.date(), dt.date() - timedelta(days=1)):
            day = candidate.isoformat()
            window = settlement_standard_time_window(city, day)
            if window.start_utc <= dt.astimezone(timezone.utc) < window.end_utc:
                grouped[(city, day)].append({**row, "_dt": dt, "_temp": temp})
                break
    out = []
    for (city, day), values in sorted(grouped.items()):
        window = settlement_standard_time_window(city, day)
        high = max(values, key=lambda r: (r["_temp"], r["_dt"])); low = min(values, key=lambda r: (r["_temp"], r["_dt"]))
        out.append({"city": city, "outcome_local_date": day, "window_start_utc": window.start_utc.isoformat().replace("+00:00", "Z"), "window_end_utc": window.end_utc.isoformat().replace("+00:00", "Z"), "observation_count": str(len(values)), "tmax_f": f"{high['_temp']:.3f}", "tmax_utc": high["valid_utc"], "tmin_f": f"{low['_temp']:.3f}", "tmin_utc": low["valid_utc"], "raw_hashes": "|".join(sorted({r.get("sha256", "") for r in values}))})
    return out

def main() -> None:
    p=argparse.ArgumentParser(description=__doc__); p.add_argument("--input",type=Path,required=True); p.add_argument("--output",type=Path,required=True); a=p.parse_args()
    with a.input.open(newline="") as f: rows=list(csv.DictReader(f))
    out=build(rows); a.output.parent.mkdir(parents=True,exist_ok=True)
    with a.output.open("w",newline="") as f: w=csv.DictWriter(f,fieldnames=FIELDS); w.writeheader(); w.writerows(out)
    print(f"wrote {a.output} ({len(out)} rows)")
if __name__ == "__main__": main()

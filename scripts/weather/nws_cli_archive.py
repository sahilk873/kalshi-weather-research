"""Retrieve timestamped, revision-preserving NWS Daily Climate Reports.

IEM's AFOS archive is the historical text-product source for the older Kalshi
NWS-settlement era.  It returns every CLIPHX or CLILAS issuance in the request
window, including corrected/reissued products.  The ZIP itself is retained;
the normalized CSV records the WMO header timestamp as publication_time_utc.

Examples:
  python3 scripts/weather/nws_cli_archive.py --start 2021-01-01 --end 2026-01-01
  python3 scripts/weather/nws_cli_archive.py --start 2026-08-01 --end 2026-09-11
"""
from __future__ import annotations

import argparse, csv, io, re, sys, zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode

_SELF = Path(__file__).resolve().parent; sys.path.insert(0, str(_SELF))
from common import ensure_runtime_dirs, http_get, utcnow  # noqa: E402
from stations import DEFAULT_CITIES, get_cities  # noqa: E402

BASE = "https://mesonet.agron.iastate.edu/cgi-bin/afos/retrieve.py"
COLS = ["city", "station", "pil", "climate_date", "official_daily_high_f",
        "official_daily_low_f", "publication_time_utc", "revision_timestamp_utc",
        "source", "source_url", "raw_filename"]

def url(pil, start, end):
    return BASE + "?" + urlencode({"pil": pil, "fmt": "zip", "sdate": start, "edate": end, "limit": 100, "order": "asc"})

def parse(text: str, city, pil: str, source_url: str, filename: str) -> dict | None:
    # Header WMO DDHHMM is only day/time; IEM filename supplies full UTC date.
    match = re.search(r"_(\d{12})(?:\d{2})?\.txt$", filename)
    pub = ""
    if match:
        pub = datetime.strptime(match.group(1), "%Y%m%d%H%M").replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")
    date_match = re.search(r"SUMMARY FOR ([A-Z]+ \d{1,2} \d{4})", text)
    climate_date = ""
    if date_match:
        climate_date = datetime.strptime(date_match.group(1), "%B %d %Y").date().isoformat()
    # CLI line styles vary but both labels immediately follow MAXIMUM/MINIMUM.
    def value(label):
        m = re.search(r"^\s*" + label + r"\s+(-?\d+|MM)\b", text, re.M)
        return int(m.group(1)) if m and m.group(1) != "MM" else None
    hi, lo = value("MAXIMUM"), value("MINIMUM")
    if not climate_date or (hi is None and lo is None): return None
    return {"city": city.key, "station": city.iem_sid, "pil": pil,
            "climate_date": climate_date, "official_daily_high_f": hi,
            "official_daily_low_f": lo, "publication_time_utc": pub,
            # A second product for a climate date is a revision candidate; retain all.
            "revision_timestamp_utc": pub, "source": "NWS CLI via IEM AFOS archive",
            "source_url": source_url, "raw_filename": filename}

def main():
    ap=argparse.ArgumentParser(description=__doc__); ap.add_argument("--start", required=True); ap.add_argument("--end", required=True); ap.add_argument("--cities", nargs="*", default=None); ap.add_argument("--chunk-days",type=int,default=90); args=ap.parse_args()
    dirs=ensure_runtime_dirs(); outdir=dirs["research"] / "nws_cli"; rawdir=outdir / "raw"; rawdir.mkdir(parents=True, exist_ok=True)
    rows=[]
    for city in get_cities(args.cities or DEFAULT_CITIES):
        pil="CLI"+city.nws_cli_issuedby; cursor=datetime.fromisoformat(args.start).date(); end=datetime.fromisoformat(args.end).date()
        while cursor < end:
            stop=min(end,cursor+timedelta(days=args.chunk_days)); request=url(pil,cursor.isoformat(),stop.isoformat()); dest=rawdir/f"{pil}_{cursor}_{stop}.zip"
            if not dest.exists(): dest.write_bytes(http_get(request, timeout=300))
            with zipfile.ZipFile(dest) as z:
                for name in z.namelist():
                    text=z.read(name).decode("ascii", "replace")
                    row=parse(text,city,pil,request,name)
                    if row: rows.append(row)
            cursor=stop
    # Merge with any previously retained products instead of overwriting:
    # a narrower later window must never destroy earlier issuances from the
    # rolling IEM archive. Existing rows take precedence on filename clashes.
    existing=[]
    out=outdir/"daily_climate_cli.csv"
    if out.exists():
        with out.open(newline="") as fh:
            existing=list(csv.DictReader(fh))
    merged={}
    for r in existing:
        merged[(r["city"],r["raw_filename"])]=r
    for r in rows:
        merged.setdefault((r["city"],r["raw_filename"]),r)
    merged_rows=sorted(merged.values(),
                       key=lambda r:(r["city"],r["climate_date"],
                                     r["publication_time_utc"]))
    with out.open("w",newline="") as fh:
        w=csv.DictWriter(fh,fieldnames=COLS); w.writeheader(); w.writerows(merged_rows)
    print(f"wrote {out} ({len(merged_rows)} product versions; "
          f"{len(rows)} new in this run); fetched_at={utcnow()}")
if __name__ == "__main__": main()

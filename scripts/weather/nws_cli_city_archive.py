"""Retrieve official NWS Daily Climate Report (CLI) products for new cities.

IEM AFOS is a public archive mirror.  Raw ZIPs are retained because its
rolling retention window is limited; rerun regularly for a durable archive.
"""
from __future__ import annotations
import argparse, csv, re, sys, zipfile
from datetime import date, timedelta, datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
_SELF=Path(__file__).resolve().parent; sys.path.insert(0,str(_SELF))
from common import ensure_runtime_dirs, http_get, utcnow  # noqa:E402

BASE="https://mesonet.agron.iastate.edu/cgi-bin/afos/retrieve.py"
CITIES={"nyc":("KNYC","CLINYC"),"la":("KLAX","CLILAX"),"austin":("KAUS","CLIAUS")}
COLS=["city","station","pil","climate_date","official_daily_high_f","official_daily_low_f","publication_time_utc","source","source_url","raw_filename"]

def parse(text, city, station, pil, source, filename):
    dm=re.search(r"SUMMARY FOR\s+[A-Z]+\s+(\d{1,2})\s+(\d{4})",text)
    # Month is often written in full; accept numeric fallback from filename.
    mname=re.search(r"SUMMARY FOR\s+([A-Z]+)\s+(\d{1,2})\s+(\d{4})",text)
    climate=""
    if mname:
        try: climate=datetime.strptime(" ".join(mname.groups()),"%B %d %Y").date().isoformat()
        except ValueError: pass
    if not climate:
        fm=re.search(r"_(\d{8})\d{4}",filename)
        if fm: climate=fm.group(1)[:4]+"-"+fm.group(1)[4:6]+"-"+fm.group(1)[6:8]
    def val(label):
        hit=re.search(r"^\s*"+label+r"\s+(-?\d+|MM)\b",text,re.M)
        return "" if not hit or hit.group(1)=="MM" else int(hit.group(1))
    if not climate: return None
    fm=re.search(r"_(\d{12})(?:\d{2})?\.txt$",filename)
    pub=""
    if fm:
        pub=datetime.strptime(fm.group(1),"%Y%m%d%H%M").replace(tzinfo=timezone.utc).isoformat().replace("+00:00","Z")
    return {"city":city,"station":station,"pil":pil,"climate_date":climate,"official_daily_high_f":val("MAXIMUM"),"official_daily_low_f":val("MINIMUM"),"publication_time_utc":pub,"source":"NWS CLI via IEM AFOS archive","source_url":source,"raw_filename":filename}

def main():
    ap=argparse.ArgumentParser(description=__doc__); ap.add_argument("--start",required=True); ap.add_argument("--end",required=True); ap.add_argument("--cities",nargs="*",default=list(CITIES)); ap.add_argument("--chunk-days",type=int,default=7); a=ap.parse_args()
    bad=[c for c in a.cities if c not in CITIES]
    if bad: raise SystemExit(f"unknown city {bad}")
    d=ensure_runtime_dirs(); root=d["research"]/"city_nws_cli"; raw=root/"raw"; raw.mkdir(parents=True,exist_ok=True)
    rows=[]
    for city in a.cities:
        station,pil=CITIES[city]; cur=date.fromisoformat(a.start); end=date.fromisoformat(a.end)
        while cur<end:
            stop=min(end,cur+timedelta(days=a.chunk_days)); params={"pil":pil,"fmt":"zip","sdate":cur.isoformat(),"edate":stop.isoformat(),"limit":100,"order":"asc"}; source=BASE+"?"+urlencode(params); dest=raw/f"{city}_{pil}_{cur}_{stop}.zip"
            if not dest.exists(): dest.write_bytes(http_get(source,timeout=300))
            with zipfile.ZipFile(dest) as z:
                for name in z.namelist():
                    row=parse(z.read(name).decode("ascii","replace"),city,station,pil,source,name)
                    if row: rows.append(row)
            cur=stop
    out=root/"daily_climate_cli.csv"; merged={}
    if out.exists():
        with out.open(newline="") as fh:
            for r in csv.DictReader(fh): merged[(r["city"],r["raw_filename"])]=r
    for r in rows: merged.setdefault((r["city"],r["raw_filename"]),r)
    result=sorted(merged.values(),key=lambda r:(r["city"],r["climate_date"],r["publication_time_utc"]))
    with out.open("w",newline="") as fh:
        w=csv.DictWriter(fh,fieldnames=COLS); w.writeheader(); w.writerows(result)
    print(f"wrote {out} ({len(result)} product versions); fetched_at={utcnow()}")
if __name__=="__main__": main()

"""Bounded historical IEM ASOS backfill preserving raw and parsed data.

Unlike the trailing sample downloader, this writes a separate backfill tree
and never overwrites `data/weather_research/iem/`. Monthly chunks keep requests
retryable and avoid enormous responses. Example: five years is 120 chunks per
station.
"""
from __future__ import annotations
import argparse,csv,sys
from datetime import date,timedelta,datetime,timezone
from pathlib import Path
_SELF=Path(__file__).resolve().parent;sys.path.insert(0,str(_SELF))
from common import ensure_runtime_dirs,utcnow  # noqa:E402
from iem_asos import fetch_archive,parse_archive,PARSED_COLUMNS  # noqa:E402
from stations import DEFAULT_CITIES,get_cities  # noqa:E402
def month_end(d):
    n=(d.replace(day=28)+timedelta(days=4)).replace(day=1)
    return n-timedelta(days=1)
def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--start',required=True);ap.add_argument('--end',required=True);ap.add_argument('--cities',nargs='*',default=None);a=ap.parse_args(); start=date.fromisoformat(a.start);end=date.fromisoformat(a.end)
 if end<start: raise SystemExit('--end before --start')
 d=ensure_runtime_dirs(); root=d['research']/'iem_backfill'; raw=root/'raw';raw.mkdir(parents=True,exist_ok=True); parsed=[]
 for city in get_cities(a.cities or DEFAULT_CITIES):
  cur=start
  while cur<=end:
   stop=min(month_end(cur),end); s=datetime(cur.year,cur.month,cur.day,tzinfo=timezone.utc); e=datetime(stop.year,stop.month,stop.day,tzinfo=timezone.utc)
   p=fetch_archive(city,s,e,raw); parsed.extend(parse_archive(p,city)); cur=stop+timedelta(days=1)
 out=root/'asos_parsed.csv'; parsed.sort(key=lambda r:(r['station'],r['valid_utc']))
 with out.open('w',newline='') as f: w=csv.DictWriter(f,fieldnames=PARSED_COLUMNS);w.writeheader();w.writerows(parsed)
 print(f'wrote {out} ({len(parsed)} rows); fetched_at={utcnow()}')
if __name__=='__main__':main()

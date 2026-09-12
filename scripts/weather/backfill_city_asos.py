"""Backfill raw/parsed IEM ASOS data for comparison cities.

These stations are observational proxies for Kalshi's NYC/Austin/LA hourly
contracts; verify each contract's settlement source before using as labels.
"""
from __future__ import annotations
import argparse,csv,sys
from dataclasses import replace
from datetime import date,datetime,timedelta,timezone
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from iem_asos import fetch_archive,parse_archive,PARSED_COLUMNS
from stations import City

CONFIG={
 'nyc': City('nyc','New York','America/New_York','NY_ASOS','NYC','USW00094728',40.7789,-73.9692,'KXTEMPNYCH','',5,'NYC','OKX'),
 'austin': City('austin','Austin','America/Chicago','TX_ASOS','AUS','USW00013904',30.1945,-97.6699,'KXTEMPAUSH','',6,'AUS','EWX'),
 'la': City('la','Los Angeles','America/Los_Angeles','CA_ASOS','LAX','USW00023174',33.9382,-118.3886,'KXTEMPLAXH','',8,'LAX','LOX'),
}
def mend(d):
 n=(d.replace(day=28)+timedelta(days=4)).replace(day=1); return n-timedelta(days=1)
def main():
 ap=argparse.ArgumentParser(); ap.add_argument('--start',default='2024-01-01'); ap.add_argument('--end',default='2026-09-11'); ap.add_argument('--cities',nargs='+',choices=CONFIG,default=list(CONFIG)); a=ap.parse_args(); start=date.fromisoformat(a.start); end=date.fromisoformat(a.end)
 root=Path(__file__).resolve().parents[2]/'data/weather_research/city_asos'; raw=root/'raw'; raw.mkdir(parents=True,exist_ok=True); rows=[]
 for key in a.cities:
  c=CONFIG[key]; cur=start
  while cur<=end:
   stop=min(mend(cur),end); s=datetime.combine(cur,datetime.min.time(),tzinfo=timezone.utc); e=datetime.combine(stop,datetime.min.time(),tzinfo=timezone.utc)
   p=fetch_archive(c,s,e,raw); rows.extend(parse_archive(p,c)); cur=stop+timedelta(days=1)
 rows.sort(key=lambda r:(r['station'],r['valid_utc'])); out=root/'asos_parsed.csv';
 with out.open('w',newline='') as f: w=csv.DictWriter(f,fieldnames=PARSED_COLUMNS); w.writeheader(); w.writerows(rows)
 print(f'wrote {len(rows)} rows to {out}')
if __name__=='__main__': main()

"""Collect a deliberately small nearby ASOS network (three non-settlement sites/city).

Raw IEM CSVs are retained; this avoids indiscriminate regional downloads while
providing spatial-gradient inputs for PHX and LV intraday research.
"""
from __future__ import annotations
import argparse,sys
from datetime import datetime,timedelta,timezone
from pathlib import Path
from urllib.parse import urlencode
_SELF=Path(__file__).resolve().parent;sys.path.insert(0,str(_SELF))
from common import ensure_runtime_dirs,http_get_text,utcnow  # noqa:E402
BASE='https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py'
SITES={'phx':('AZ_ASOS',['SDL','CHD','FFZ']),'lv':('NV_ASOS',['HND','VGT','LSV'])}
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--days',type=int,default=30);a=ap.parse_args();d=ensure_runtime_dirs();out=d['research']/'nearby_asos'/'raw';out.mkdir(parents=True,exist_ok=True);e=datetime.now(timezone.utc);s=e-timedelta(days=a.days);n=0
 for city,(network,sites) in SITES.items():
  for station in sites:
   p={'network':network,'station':station,'data':'all','year1':s.year,'month1':s.month,'day1':s.day,'year2':e.year,'month2':e.month,'day2':e.day,'tz':'Etc/UTC','format':'onlycomma','report_type':['3','4'],'direct':'1'};dest=out/f'{city}_{station}_{s:%Y%m%d}_{e:%Y%m%d}.csv'
   if not dest.exists():
    text=http_get_text(BASE+'?'+urlencode(p,doseq=True),timeout=300)
    if not text.startswith('station,valid,'): raise RuntimeError(f'unexpected IEM response {station}')
    dest.write_text(text)
   n+=1
 print(f'wrote/cached {n} nearby raw archives; fetched_at={utcnow()}')
if __name__=='__main__':main()

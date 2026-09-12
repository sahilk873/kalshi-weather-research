"""Bounded extractor for Kalshi's archived PHX/LV temperature markets."""
from __future__ import annotations
import argparse, csv, json, time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
try:
    from stations import CITIES
except ImportError:
    from scripts.weather.stations import CITIES

BASE = "https://external-api.kalshi.com/trade-api/v2"
SERIES = {c.kalshi_high_series: (k, "high") for k,c in CITIES.items()} | {c.kalshi_low_series: (k, "low") for k,c in CITIES.items()}
SERIES.update({"KXTEMPNYCH": ("nyc", "hourly"), "KXTEMPAUSH": ("austin", "hourly"), "KXTEMPLAXH": ("la", "hourly")})
ROOT = Path(__file__).resolve().parents[2] / "data/weather_research/kalshi_historical_city"
def event_date(m):
    code=m.get('event_ticker','').split('-')[-1]
    try: return datetime.strptime(code,'%y%b%d').date().isoformat()
    except ValueError: return ''

def api(path, params, raw_path, retries=3):
    q = urlencode({k:v for k,v in params.items() if v is not None})
    url = BASE + path + ("?" + q if q else "")
    for i in range(retries):
        try:
            req = Request(url, headers={"User-Agent":"kalshi-weather-research/1.0"})
            with urlopen(req, timeout=60) as r: payload=json.load(r)
            raw_path.parent.mkdir(parents=True, exist_ok=True); raw_path.write_text(json.dumps({"request_url":url,"retrieved_at":datetime.now(timezone.utc).isoformat(),"response":payload}, indent=2))
            return payload
        except Exception:
            if i == retries-1: raise
            time.sleep(2**i)

def pages(path, params, raw_dir, key, response_key=None, limit=1000):
    cur=None
    while True:
        p=dict(params, limit=limit, cursor=cur)
        d=api(path,p,raw_dir/f"{key}_{cur or 'first'}.json"); yield from (d.get(response_key or key,[]) or [])
        cur=d.get("cursor")
        if not cur: break

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--series', nargs='+', choices=sorted(SERIES), default=['KXTEMPNYCH','KXTEMPAUSH','KXTEMPLAXH']); ap.add_argument('--start'); ap.add_argument('--end'); ap.add_argument('--interval', choices=['1m','1h','1d'], default='1h'); ap.add_argument('--max-markets',type=int,default=1000); ap.add_argument('--max-requests',type=int,default=5000); ap.add_argument('--markets-only',action='store_true'); ap.add_argument('--dry-run',action='store_true'); args=ap.parse_args()
    ROOT.mkdir(parents=True,exist_ok=True); print('cutoff:', api('/historical/cutoff',{},ROOT/'raw'/'cutoff.json'))
    if args.dry_run: print('series:',args.series,'interval:',args.interval); return
    requests=1; markets=[]
    for s in args.series:
        for m in pages('/historical/markets',{'series_ticker':s},ROOT/'raw'/'markets',s,response_key='markets'):
            date=event_date(m)
            if args.start and date < args.start: continue
            if args.end and date > args.end: continue
            markets.append(m)
            if len(markets)>=args.max_markets: break
        if len(markets)>=args.max_markets: break
    mf=ROOT/'markets.csv'; fields=['ticker','event_ticker','series_ticker','city','variable','result','floor_strike','cap_strike','open_time','close_time','expiration_time','volume','open_interest']
    with mf.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields); w.writeheader()
        for m in markets:
            s=m.get('series_ticker') or m.get('event_ticker','').rsplit('-',1)[0]; city,var=SERIES.get(s,('', '')); w.writerow({'ticker':m.get('ticker'),'event_ticker':m.get('event_ticker'),'series_ticker':s,'city':city,'variable':var,'result':m.get('result'),'floor_strike':m.get('floor_strike'),'cap_strike':m.get('cap_strike'),'open_time':m.get('open_time'),'close_time':m.get('close_time'),'expiration_time':m.get('expiration_time'),'volume':m.get('volume_fp',m.get('volume')),'open_interest':m.get('open_interest_fp',m.get('open_interest'))})
    if args.markets_only:
        print(f'markets={len(markets)} (market metadata only)'); return
    trade_rows=[]; candle_rows=[]
    for m in markets:
        ticker=m.get('ticker'); requests+=2
        if requests>args.max_requests: break
        for t in pages('/historical/trades',{'ticker':ticker},ROOT/'raw'/'trades',ticker,response_key='trades',limit=1000): trade_rows.append({'ticker':ticker,'trade_id':t.get('trade_id'),'timestamp':t.get('created_time'),'price':t.get('yes_price_dollars'),'no_price':t.get('no_price_dollars'),'size':t.get('count_fp'),'side':t.get('taker_side'),'is_block_trade':t.get('is_block_trade')})
        start=int(datetime.fromisoformat(m['open_time'].replace('Z','+00:00')).timestamp()) if m.get('open_time') else None; end=int(datetime.fromisoformat(m['expiration_time'].replace('Z','+00:00')).timestamp()) if m.get('expiration_time') else None
        period={'1m':1,'1h':60,'1d':1440}[args.interval]
        d=api(f'/historical/markets/{ticker}/candlesticks',{'start_ts':start,'end_ts':end,'period_interval':period},ROOT/'raw'/'candles'/f'{ticker}_{period}.json')
        for c in d.get('candlesticks',[]): candle_rows.append({'ticker':ticker,'end_period_ts':c.get('end_period_ts'),'period_minutes':period,'volume':c.get('volume'),'open_interest':c.get('open_interest'),'price_open':(c.get('price') or {}).get('open'),'price_high':(c.get('price') or {}).get('high'),'price_low':(c.get('price') or {}).get('low'),'price_close':(c.get('price') or {}).get('close'),'yes_bid_close':(c.get('yes_bid') or {}).get('close'),'yes_ask_close':(c.get('yes_ask') or {}).get('close')})
    def write(name, rows):
        if not rows:return
        with (ROOT/name).open('w',newline='') as f: w=csv.DictWriter(f,fieldnames=rows[0]); w.writeheader(); w.writerows(rows)
    write('trades.csv',trade_rows); write('candles.csv',candle_rows); print(f'markets={len(markets)} trades={len(trade_rows)} candles={len(candle_rows)} requests<={requests}')
if __name__=='__main__': main()

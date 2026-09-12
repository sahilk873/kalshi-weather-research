"""Point-in-time HRRR/NBM raw-archive collector for PHX/LV.

Downloads only selected model run/lead raw GRIB2 files plus an immutable
manifest containing model initialization, valid time, URI, SHA-256 and
ingestion timestamp. This keeps provenance correct even when a GRIB decoder is
not installed; raw files remain the authority. A later decoder stage must
write station/grid coordinates and extracted variables, never replace raw.
"""
from __future__ import annotations
import argparse, csv, hashlib, sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.request import Request, urlopen
_SELF=Path(__file__).resolve().parent; sys.path.insert(0,str(_SELF))
from common import ensure_runtime_dirs, utcnow  # noqa: E402

def hrrr_uri(init, lead):
    d=init.strftime("%Y%m%d"); h=init.strftime("%H")
    return f"https://noaa-hrrr-bdp-pds.s3.amazonaws.com/hrrr.{d}/conus/hrrr.t{h}z.wrfsfcf{lead:02d}.grib2"
def nbm_uri(init, lead):
    d=init.strftime("%Y%m%d"); h=init.strftime("%H")
    return f"https://noaa-nbm-grib2-pds.s3.amazonaws.com/blend.{d}/{h}/core/blend.t{h}z.core.f{lead:03d}.co.grib2"
def fetch(uri,path, max_bytes):
    if path.exists(): return hashlib.sha256(path.read_bytes()).hexdigest()
    req=Request(uri,headers={"User-Agent":"kalshi-weather-research/1.0"})
    with urlopen(req,timeout=300) as r:
        size=int(r.headers.get("Content-Length", "0") or 0)
        if size and size > max_bytes:
            raise RuntimeError(f"refusing {size:,}-byte GRIB: exceeds --max-bytes {max_bytes:,}; use a GRIB filter/range extractor, not a global download")
        data=r.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise RuntimeError("response exceeded --max-bytes")
    path.write_bytes(data); return hashlib.sha256(data).hexdigest()
def main():
    ap=argparse.ArgumentParser(description=__doc__); ap.add_argument("--model",choices=["hrrr","nbm"],required=True); ap.add_argument("--init",required=True,help="UTC YYYY-mm-ddTHH"); ap.add_argument("--leads",nargs="+",type=int,default=[0,1,2]); ap.add_argument("--max-bytes",type=int,default=128*1024*1024); args=ap.parse_args()
    init=datetime.strptime(args.init,"%Y-%m-%dT%H").replace(tzinfo=timezone.utc); dirs=ensure_runtime_dirs(); out=dirs["research"]/"models"/args.model; out.mkdir(parents=True,exist_ok=True); manifest=[]
    for lead in args.leads:
        uri=(hrrr_uri if args.model=="hrrr" else nbm_uri)(init,lead); file=out/f"{args.model}_{init.strftime('%Y%m%dT%HZ')}_f{lead:03d}.grib2"
        sha=fetch(uri,file,args.max_bytes); manifest.append({"model":args.model,"initialization_time_utc":init.isoformat().replace("+00:00","Z"),"valid_time_utc":(init+timedelta(hours=lead)).isoformat().replace("+00:00","Z"),"lead_hours":lead,"uri":uri,"raw_path":str(file.relative_to(dirs["research"])),"sha256":sha,"ingested_at":utcnow(),"grid_location":"PHX/LV extraction pending GRIB decoder"})
    p=out/"manifest.csv"; exists=p.exists()
    with p.open("a",newline="") as fh:
        w=csv.DictWriter(fh,fieldnames=manifest[0]);
        if not exists:w.writeheader()
        w.writerows(manifest)
    print(f"wrote {len(manifest)} {args.model} raw files and {p}")
if __name__=="__main__": main()

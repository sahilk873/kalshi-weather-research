"""Decode ECMWF IFS ensemble 2-m temperatures at registered points."""
from __future__ import annotations
import argparse,csv,hashlib
from datetime import datetime,timezone
from pathlib import Path
POINTS={"phx":(33.4343,-112.0116),"lv":(36.0719,-115.1633),"nyc":(40.7789,-73.9692),"la":(33.9382,-118.3866),"austin":(30.1945,-97.6699)}
FIELDS=["model","city","member_id","initialization_time_utc","valid_time_utc","lead_hours","source_receipt_time","variable","value","unit","grid_latitude","grid_longitude","raw_path","sha256","message_index"]
def decode(path:Path,init_text:str,receipt:str,out:Path,cities:list[str])->int:
 try:
  from eccodes import codes_get,codes_grib_find_nearest,codes_grib_new_from_file,codes_release
 except ImportError as e: raise RuntimeError("eccodes is required") from e
 digest=hashlib.sha256(path.read_bytes()).hexdigest(); init=datetime.fromisoformat(init_text.replace("Z","+00:00")); rows=[]
 with path.open("rb") as h:
  idx=0
  while (gid:=codes_grib_new_from_file(h)) is not None:
   idx+=1
   try:
    if codes_get(gid,"shortName")!="2t": continue
    date=int(codes_get(gid,"validityDate")); tm=int(codes_get(gid,"validityTime")); valid=datetime.strptime(f"{date}{tm:04d}","%Y%m%d%H%M").replace(tzinfo=timezone.utc); lead=int((valid-init).total_seconds()//3600); member=str(codes_get(gid,"perturbationNumber"))
    for city in cities:
     n=codes_grib_find_nearest(gid,*POINTS[city])[0]; rows.append({"model":"ECMWF_IFS_ENFO","city":city,"member_id":member,"initialization_time_utc":init_text,"valid_time_utc":valid.isoformat().replace("+00:00","Z"),"lead_hours":lead,"source_receipt_time":receipt,"variable":"temperature_2m","value":round((float(n["value"])-273.15)*9/5+32,6),"unit":"F","grid_latitude":n["lat"],"grid_longitude":n["lon"],"raw_path":str(path),"sha256":digest,"message_index":idx})
   finally: codes_release(gid)
 out.parent.mkdir(parents=True,exist_ok=True)
 with out.open("w",newline="") as h: w=csv.DictWriter(h,fieldnames=FIELDS); w.writeheader(); w.writerows(rows)
 return len(rows)
def main()->None:
 p=argparse.ArgumentParser(description=__doc__); p.add_argument("--input",type=Path,required=True); p.add_argument("--initialization",required=True); p.add_argument("--receipt",required=True); p.add_argument("--output",type=Path,required=True); p.add_argument("--cities",nargs="*",default=list(POINTS)); a=p.parse_args(); print(f"wrote {decode(a.input,a.initialization,a.receipt,a.output,a.cities)} rows")
if __name__=="__main__": main()

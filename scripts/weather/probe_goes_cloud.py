"""Probe public GOES ABI cloud-product availability without downloading imagery."""
from __future__ import annotations

import argparse
import json
import time
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlencode, parse_qs, urlparse
from urllib.request import Request, urlopen
from xml.etree import ElementTree

PRODUCTS = ("ABI-L2-MCMIPF", "ABI-L2-MCMIPC")
BUCKETS = {"G16": "noaa-goes16", "G18": "noaa-goes18"}


def listing_url(satellite: str, product: str, day: date, hour: int) -> str:
    prefix = f"{product}/{day:%Y}/{day.timetuple().tm_yday:03d}/{hour:02d}/"
    return f"https://{BUCKETS[satellite]}.s3.amazonaws.com/?" + urlencode({"list-type": "2", "prefix": prefix, "max-keys": 1000})


def probe(satellite: str, product: str, day: date, hour: int) -> dict:
    url = listing_url(satellite, product, day, hour)
    try:
        keys = []
        next_token = None
        for _ in range(5):
            params = {k: v[-1] for k, v in parse_qs(urlparse(url).query).items()}
            if next_token: params["continuation-token"] = next_token
            page_url = url.split("?", 1)[0] + "?" + urlencode(params)
            for attempt in range(3):
                try:
                    with urlopen(Request(page_url, headers={"User-Agent": "kalshi-weather-research/1.0"}), timeout=30) as response:
                        root = ElementTree.fromstring(response.read())
                    break
                except Exception:
                    if attempt == 2: raise
                    time.sleep(0.5 * (attempt + 1))
            ns = "{http://s3.amazonaws.com/doc/2006-03-01/}"
            keys.extend(element.text for element in root.findall(f"{ns}Contents/{ns}Key") if element.text)
            if root.findtext(f"{ns}IsTruncated") != "true": break
            next_token = root.findtext(f"{ns}NextContinuationToken")
            if not next_token: break
        return {"satellite": satellite, "product": product, "day": day.isoformat(), "hour_utc": hour, "listing_url": url, "status": "ok", "object_count": len(keys), "object_keys": keys, "probed_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")}
    except Exception as exc:
        return {"satellite": satellite, "product": product, "day": day.isoformat(), "hour_utc": hour, "listing_url": url, "status": "error", "error": str(exc), "object_count": 0, "object_keys": [], "probed_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", default=date.today().isoformat()); parser.add_argument("--hour", type=int, default=12); parser.add_argument("--output", type=Path, required=True); parser.add_argument("--satellites", nargs="+", choices=sorted(BUCKETS), default=["G16", "G18"]); parser.add_argument("--products", nargs="+", choices=PRODUCTS, default=list(PRODUCTS))
    args = parser.parse_args(); day = date.fromisoformat(args.date)
    report = [probe(satellite, product, day, args.hour) for satellite in args.satellites for product in args.products]
    args.output.parent.mkdir(parents=True, exist_ok=True); args.output.write_text(json.dumps(report, indent=2) + "\n"); print(f"wrote {len(report)} GOES availability probes")


if __name__ == "__main__": main()

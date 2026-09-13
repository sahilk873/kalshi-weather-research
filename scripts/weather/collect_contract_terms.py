"""Archive Kalshi contract/terms PDFs referenced by a series payload."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen


def collect(series_path: Path, output_dir: Path) -> dict:
    wrapper = json.loads(series_path.read_text())
    series = wrapper.get("series", wrapper)
    urls = {name: series.get(name, "") for name in ("contract_url", "contract_terms_url")}
    receipt = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    rows = []
    output_dir.mkdir(parents=True, exist_ok=True)
    for name, url in urls.items():
        if not url:
            rows.append({"kind": name, "url": "", "status": "missing", "retrieved_at_utc": receipt})
            continue
        request = Request(url, headers={"User-Agent": "kalshi-weather-research/1.0"})
        with urlopen(request, timeout=60) as response:
            body = response.read()
            content_type = response.headers.get("Content-Type", "")
        digest = hashlib.sha256(body).hexdigest()
        path = output_dir / f"{name}_{digest[:16]}.pdf"
        path.write_bytes(body)
        rows.append({"kind": name, "url": url, "path": str(path), "sha256": digest, "bytes": len(body), "content_type": content_type, "retrieved_at_utc": receipt, "status": "ok"})
    manifest = {"version": "kalshi-contract-terms-v1", "series_ticker": series.get("ticker", ""), "retrieved_at_utc": receipt, "files": rows}
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--series", type=Path, default=Path("data/weather_research/kalshi_hourly/series.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("data/weather_research/kalshi_hourly/terms"))
    args = parser.parse_args()
    result = collect(args.series, args.output_dir)
    print(json.dumps({"files": len(result["files"]), "ok": sum(row.get("status") == "ok" for row in result["files"])}))


if __name__ == "__main__":
    main()

"""Capture authenticated Kalshi REST order-book snapshots (read only).

Each response is archived with receipt time and SHA-256 provenance.  This
module never submits orders and deliberately does not infer asks or fills.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import urllib.parse
import urllib.request
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from kalshi_auth import parse_credential_file, sign_access_request
from stations import KALSHI_API_BASE


def _receipt() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def collect_rest_orderbooks(
    tickers: list[str],
    *,
    credential_file: Path,
    output_dir: Path,
    api_base: str = KALSHI_API_BASE,
    depth: int = 0,
    opener: Callable[..., object] | None = None,
) -> dict:
    """Fetch and archive one current REST book per ticker.

    ``opener`` is injectable for deterministic tests.  The returned manifest
    is also written to disk; raw response bytes are never rewritten.
    """
    if not tickers:
        raise ValueError("at least one ticker is required")
    if len(tickers) > 100 or any(not t or len(t) > 200 for t in tickers):
        raise ValueError("tickers must contain 1-100 non-empty values of <=200 characters")
    key_id, private_key = parse_credential_file(credential_file)
    output_dir.mkdir(parents=True, exist_ok=True)
    open_url = opener or urllib.request.urlopen
    captured_at = _receipt()
    rows = []
    for ticker in tickers:
        query = urllib.parse.urlencode({"depth": depth})
        path = f"/trade-api/v2/markets/{urllib.parse.quote(ticker, safe='')}/orderbook?{query}"
        url = f"{api_base}/markets/{urllib.parse.quote(ticker, safe='')}/orderbook?{query}"
        headers = {"User-Agent": "kalshi-weather-research/1.0"}
        headers.update(sign_access_request(key_id, private_key, method="GET", path=path))
        req = urllib.request.Request(url, headers=headers, method="GET")
        with open_url(req, timeout=60) as response:  # type: ignore[attr-defined]
            raw = response.read()
        digest = hashlib.sha256(raw).hexdigest()
        stamp = captured_at.replace(":", "").replace("-", "")
        safe_ticker = re.sub(r"[^A-Za-z0-9_.-]+", "_", ticker)
        raw_path = output_dir / f"{stamp}_{safe_ticker}.json"
        raw_path.write_bytes(raw)
        rows.append({"ticker": ticker, "receipt_ts": captured_at,
                     "sha256": digest, "path": str(raw_path),
                     "request_path": path, "depth": depth})
    manifest = {"version": "rest-orderbook-manifest-v1", "captured_at": captured_at,
                "read_only": True, "source_publication_time_observed": False,
                "availability_basis": "receipt_upper_bound", "rows": rows}
    manifest_path = output_dir / f"manifest_{captured_at.replace(':', '').replace('-', '')}.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    manifest["manifest_path"] = str(manifest_path)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ticker", action="append", dest="tickers", required=True)
    parser.add_argument("--credential-file", type=Path,
                        default=Path(os.environ.get("KALSHI_CREDENTIAL_FILE", "Sahil_BOT.txt")))
    parser.add_argument("--output-dir", type=Path,
                        default=Path("data/weather_research/kalshi/rest_orderbook"))
    parser.add_argument("--depth", type=int, default=0)
    args = parser.parse_args()
    result = collect_rest_orderbooks(args.tickers, credential_file=args.credential_file,
                                     output_dir=args.output_dir, depth=args.depth)
    print(json.dumps({"manifest_path": result["manifest_path"], "count": len(result["rows"])}, sort_keys=True))


if __name__ == "__main__":
    main()

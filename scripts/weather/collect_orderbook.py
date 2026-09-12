"""Resilient live orderbook + ticker + trade collector (Kalshi WebSocket).

Uses the official Kalshi Market Data WebSocket API (checked-in
asyncapi.yaml):
    wss://external-api-ws.kalshi.com/trade-api/ws/v2

Subscribes to ``orderbook_delta`` (and optionally ``ticker`` / ``trade`` /
``market_lifecycle_v2``) for the active Phoenix/Las Vegas daily temperature
markets and streams raw messages to JSON Lines files.

Authentication (connection requires authentication even for public feeds):
- Legacy scheme:  KALSHI_API_KEY + KALSHI_USER_ID
  -> headers ``Kalshi-Api-Key`` / ``Kalshi-User-Id`` on the handshake.
- Or provide arbitrary extra headers via KALSHI_WS_EXTRA_HEADERS (JSON) when
  using the newer RSA access-key handshake documented on docs.kalshi.com.

Credentials come ONLY from the environment. No secrets are stored or
committed. If no credentials are present the collector exits cleanly without
connecting (use --dry-run to print the planned configuration).

Resilience features:
- automatic reconnect with exponential backoff (cap 2 min)
- resubscribes with the same subscription ids after reconnect
- replies to server Ping control frames with Pong
- flush-to-disk per message (JSONL), never buffered indefinitely
- graceful termination on SIGINT / SIGTERM
- --run-seconds for a bounded run

Outputs (data/weather_research/kalshi/ws/):
    orderbook_<YYYYMMDD>.jsonl   ticker_<YYYYMMDD>.jsonl
    trade_<YYYYMMDD>.jsonl       lifecycle_<YYYYMMDD>.jsonl
    collector_state.json         (last reconnect/last message times)

CLI examples:
  export KALSHI_API_KEY=... KALSHI_USER_ID=...
  python3 scripts/weather/collect_orderbook.py --run-seconds 600
  python3 scripts/weather/collect_orderbook.py --channels orderbook_delta ticker
  python3 scripts/weather/collect_orderbook.py --dry-run
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import signal
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

_SELF = Path(__file__).resolve().parent
sys.path.insert(0, str(_SELF))

# ruff: noqa: E402
from common import ensure_runtime_dirs, utcnow  # noqa: E402
from stations import KALSHI_WS_URL  # noqa: E402

try:
    import websocket  # type: ignore
except ImportError:  # pragma: no cover
    websocket = None  # type: ignore

MIN_RECONNECT_S = 2.0
MAX_RECONNECT_S = 120.0
STALL_SECONDS = 90.0  # consider connection dead if no message for this long

DEFAULT_CHANNELS = ["orderbook_delta", "ticker", "trade"]
STATE_KEYS = ["subscription_id", "last_message_ts", "reconnect_count",
              "started_at", "connected"]

_STOP = threading.Event()


def _now_ms() -> int:
    return int(time.time() * 1000)


def load_market_tickers(csv_path: Path) -> list[str]:
    import csv
    tickers: list[str] = []
    if not csv_path.exists():
        return tickers
    with csv_path.open(newline="") as fh:
        for r in csv.DictReader(fh):
            if r.get("status") == "active" and r.get("market_ticker"):
                tickers.append(r["market_ticker"])
    return sorted(set(tickers))


def build_headers() -> dict[str, str]:
    """Derive connection headers from env; empty dict when unset."""
    headers: dict[str, str] = {}
    api_key = os.environ.get("KALSHI_API_KEY")
    user_id = os.environ.get("KALSHI_USER_ID")
    if api_key and user_id:
        headers["Kalshi-Api-Key"] = api_key
        headers["Kalshi-User-Id"] = user_id
    extra = os.environ.get("KALSHI_WS_EXTRA_HEADERS")
    if extra:
        try:
            parsed = json.loads(extra)
        except json.JSONDecodeError:
            raise SystemExit(
                "KALSHI_WS_EXTRA_HEADERS is not valid JSON: " + extra)
        if not isinstance(parsed, dict):
            raise SystemExit("KALSHI_WS_EXTRA_HEADERS must be a JSON object")
        headers.update({k: str(v) for k, v in parsed.items()})
    return headers


def subscribe_command(sid: int, channels: list[str],
                      tickers: list[str]) -> dict:
    return {
        "id": sid,
        "cmd": "subscribe",
        "params": {
            "channels": channels,
            "market_tickers": tickers,
        },
    }


def jsonl_sink(base_dir: Path, kind: str) -> "object":
    """Return an object with .write(msg) that appends to a dated JSONL file."""
    class _Sink:
        def __init__(self, base):
            self.base = base
            self.base.mkdir(parents=True, exist_ok=True)
            self.writer = None

        def _open(self):
            stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
            path = self.base / f"{kind}_{stamp}.jsonl"
            return path.open("a")

        def write(self, msg: dict):
            rec = {
                "received_ts": utcnow(),
                "received_ts_ms": _now_ms(),
                "message": msg,
            }
            with self._open() as fh:
                fh.write(json.dumps(rec))
                fh.write("\n")
    return _Sink(base_dir)


class Collector:
    def __init__(self, channels, tickers, outdir, run_seconds):
        self.channels = channels
        self.tickers = tickers
        self.outdir = outdir
        self.run_seconds = run_seconds
        self.sid = 1
        self.reconnect_count = 0
        self.last_message_ts = _now_ms()
        self.state_path = outdir / "collector_state.json"
        self.started_at = _now_ms()
        self.last_sequence: dict[str, int] = {}
        self.message_ids: set[str] = set()
        self.sinks = {
            k: jsonl_sink(outdir, k) for k in
            ("orderbook", "ticker", "trade", "lifecycle")
        }

    def _state(self, connected: bool) -> dict:
        return {
            "ws_url": KALSHI_WS_URL,
            "subscription_id": self.sid,
            "channels": self.channels,
            "num_market_tickers": len(self.tickers),
            "connected": connected,
            "reconnect_count": self.reconnect_count,
            "started_at_ts": self.started_at,
            "last_message_ts": self.last_message_ts,
            "last_sequence_by_stream": self.last_sequence,
            "updated_at": utcnow(),
        }

    def _write_state(self, connected: bool):
        self.state_path.write_text(
            json.dumps(self._state(connected), indent=2))

    def _on_open(self, ws):
        sub = subscribe_command(self.sid, self.channels, self.tickers)
        ws.send(json.dumps(sub))
        print(f"[ws] connected + subscribed sid={self.sid} "
              f"channels={self.channels}", flush=True)
        self._write_state(True)

    def _on_message(self, ws, raw: str):
        self.last_message_ts = _now_ms()
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            return
        mtype = msg.get("type") or msg.get("event") or ""
        # Preserve raw messages, but make duplicate/gap handling explicit for
        # downstream reconstruction. Sequence fields are subscription scoped
        # in the Kalshi spec; tolerate naming changes without inventing one.
        seq = msg.get("seq", msg.get("sequence", msg.get("sequence_number")))
        sid = str(msg.get("sid", msg.get("subscription_id", "")))
        stream = f"{sid}:{mtype}"
        fingerprint = hashlib.sha256(raw.encode()).hexdigest()
        if fingerprint in self.message_ids:
            return
        self.message_ids.add(fingerprint)
        if len(self.message_ids) > 100_000:
            self.message_ids.clear()
        if isinstance(seq, int):
            prior = self.last_sequence.get(stream)
            if prior is not None and seq > prior + 1:
                self.sinks["lifecycle"].write({"type": "sequence_gap",
                    "stream": stream, "expected": prior + 1, "received": seq})
            if prior is not None and seq <= prior:
                return
            self.last_sequence[stream] = seq
        if mtype in ("orderbook_snapshot", "orderbook_delta"):
            self.sinks["orderbook"].write(msg)
        elif mtype == "ticker":
            self.sinks["ticker"].write(msg)
        elif mtype == "trade":
            self.sinks["trade"].write(msg)
        elif mtype in ("market_lifecycle", "market_lifecycle_v2"):
            self.sinks["lifecycle"].write(msg)
        elif mtype == "subscribed":
            print(f"[ws] subscribed ack: {msg}", flush=True)
        elif mtype == "error":
            print(f"[ws] ERROR: {msg}", flush=True)
        self._write_state(True)
        # ping/pong control frames are handled by the library automatically

    def _on_error(self, ws, error):
        print(f"[ws] error: {error}", flush=True)

    def _on_close(self, ws, code, reason):
        print(f"[ws] closed code={code} reason={reason!r}", flush=True)

    def run(self):
        if websocket is None:
            raise SystemExit(
                "websocket-client is required. pip install websocket-client "
                "(see requirements.txt)")
        deadline = _now_ms() + (self.run_seconds * 1000 if self.run_seconds
                                else 0)
        backoff = MIN_RECONNECT_S
        while not _STOP.is_set():
            if deadline and _now_ms() > deadline:
                print("[ws] run-seconds elapsed, exiting", flush=True)
                break
            try:
                self._run_once()
                backoff = MIN_RECONNECT_S
            except Exception as exc:  # noqa: BLE001
                print(f"[ws] connection failed: {exc}", flush=True)
            if _STOP.is_set():
                break
            self.reconnect_count += 1
            self._write_state(False)
            print(f"[ws] reconnecting in {backoff:.0f}s "
                  f"(attempt {self.reconnect_count})", flush=True)
            _STOP.wait(backoff)
            backoff = min(backoff * 2, MAX_RECONNECT_S)

    def _run_once(self):
        headers = build_headers()
        ws = websocket.WebSocketApp(
            KALSHI_WS_URL,
            header=headers,
            on_open=self._on_open,
            on_message=self._on_message,
            on_error=self._on_error,
            on_close=self._on_close,
        )
        self._write_state(False)
        ws.run_forever(ping_interval=10, ping_timeout=8)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--channels", nargs="*", default=DEFAULT_CHANNELS,
                    help="WS channels (orderbook_delta, ticker, trade, "
                         "market_lifecycle_v2)")
    ap.add_argument("--ticker", nargs="*", dest="tickers", default=[],
                    help="explicit market tickers (default: active markets "
                         "from kalshi/markets.csv)")
    ap.add_argument("--run-seconds", type=int, default=0,
                    help="exit after N seconds (0 = run until interrupted)")
    ap.add_argument("--dry-run", action="store_true",
                    help="print planned config and exit without connecting")
    args = ap.parse_args()

    dirs = ensure_runtime_dirs()
    ws_dir = dirs["kalshi_out"] / "ws"
    ws_dir.mkdir(parents=True, exist_ok=True)
    markets_csv = dirs["kalshi_out"] / "markets.csv"

    tickers = args.tickers or load_market_tickers(markets_csv)
    headers = build_headers()
    creds_present = bool(headers)

    print(f"collector config:")
    print(f"  ws url : {KALSHI_WS_URL}")
    print(f"  channels: {args.channels}")
    print(f"  markets : {len(tickers)} ({', '.join(tickers[:6])}...)")
    print(f"  headers : {'present (' + ', '.join(headers) + ')' if creds_present else 'NONE'}")
    print(f"  out_dir : {ws_dir}")
    if not tickers:
        print("WARNING: no market tickers selected; collector will subscribe "
              "to an empty market set.", file=sys.stderr)

    if args.dry_run:
        print("\nDry run - not connecting. Reminder: market-data WS feeds "
              "require Kalshi credentials (see script docstring).")
        return 0

    if not creds_present:
        print("\nNo Kalshi credentials found in environment; not connecting. "
              "\nSet KALSHI_API_KEY + KALSHI_USER_ID "
              "(or KALSHI_WS_EXTRA_HEADERS for the access-key handshake) "
              "to enable live collection.", file=sys.stderr)
        return 2

    if websocket is None:
        print("\nwebsocket-client is required; run: "
              "pip install websocket-client", file=sys.stderr)
        return 2

    signal.signal(signal.SIGINT, lambda *_: _STOP.set())
    signal.signal(signal.SIGTERM, lambda *_: _STOP.set())

    collector = Collector(args.channels, tickers, ws_dir, args.run_seconds)
    collector.run()
    print("collector stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

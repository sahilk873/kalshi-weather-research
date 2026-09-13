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
- RSA access-key scheme: set ``KALSHI_CREDENTIAL_FILE`` to a local file
  containing a PEM private key and ``API KEY ID: ...``. A fresh handshake
  signature is generated on every reconnect.
- Or provide arbitrary extra headers via KALSHI_WS_EXTRA_HEADERS (JSON).

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
from kalshi_auth import parse_credential_file, sign_access_request  # noqa: E402
from replay_orderbook import ReplayState  # noqa: E402
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


def _iso_from_ms(value: int) -> str:
    return datetime.fromtimestamp(value / 1000, timezone.utc).isoformat().replace("+00:00", "Z")


def exchange_timestamp(message: dict) -> tuple[str | None, int | None]:
    """Return the explicit exchange event time without guessing from lifecycle dates."""
    body = message.get("msg", message)
    if not isinstance(body, dict):
        return None, None
    value = body.get("ts_ms")
    if isinstance(value, (int, float)):
        milliseconds = int(value)
        return _iso_from_ms(milliseconds), milliseconds
    value = body.get("ts")
    if isinstance(value, (int, float)):
        milliseconds = int(value * 1000 if value < 10_000_000_000 else value)
        return _iso_from_ms(milliseconds), milliseconds
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            milliseconds = int(parsed.timestamp() * 1000)
            return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"), milliseconds
        except ValueError:
            pass
    return None, None


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
    credential_file = os.environ.get("KALSHI_CREDENTIAL_FILE")
    if credential_file:
        key_id, private_key = parse_credential_file(Path(credential_file))
        headers.update(sign_access_request(key_id, private_key))
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
            self.connection_epoch = 0

        def set_connection_epoch(self, epoch: int) -> None:
            self.connection_epoch = epoch

        def _open(self):
            stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
            path = self.base / f"{kind}_{stamp}.jsonl"
            return path.open("a")

        def write(self, msg: dict, *, metadata: dict | None = None):
            rec = metadata or {
                "received_ts": utcnow(), "received_ts_ms": _now_ms(),
                "connection_epoch": self.connection_epoch,
            }
            rec = {**rec, "message": msg}
            with self._open() as fh:
                fh.write(json.dumps(rec, sort_keys=True, separators=(",", ":")))
                fh.write("\n")

        def append(self, record: dict):
            with self._open() as fh:
                fh.write(json.dumps(record, sort_keys=True, separators=(",", ":")))
                fh.write("\n")
    return _Sink(base_dir)


class Collector:
    def __init__(self, channels, tickers, outdir, run_seconds,
                 checkpoint_every: int = 1000):
        self.channels = channels
        self.tickers = tickers
        self.outdir = outdir
        self.run_seconds = run_seconds
        self.sid = 1
        self.reconnect_count = 0
        self.last_message_ts = _now_ms()
        self.state_path = outdir / "collector_state.json"
        self.started_at = _now_ms()
        self.connection_epoch = 0
        self.replay = ReplayState()
        self.last_sequence: dict[str, int] = {}
        self.sequence_gaps = 0
        self.checkpoint_every = checkpoint_every
        self.book_events = 0
        self.channel_sids: dict[str, int] = {}
        self.next_command_id = 2
        self.message_ids: set[str] = set()
        self.sinks = {
            k: jsonl_sink(outdir, k) for k in
            ("raw", "orderbook", "ticker", "trade", "lifecycle", "health",
             "checkpoints")
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
            "sequence_gaps": self.sequence_gaps,
            "quarantined_market_tickers": sorted(
                ticker for ticker, book in self.replay.books.items()
                if book.quarantined),
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
        self._health("connected", channels=self.channels,
                     market_ticker_count=len(self.tickers))
        self._write_state(True)

    def _health(self, event: str, **details) -> None:
        self.sinks["health"].append({
            "version": "kalshi-ws-health-v1", "event": event,
            "recorded_at": utcnow(), "recorded_at_ms": _now_ms(),
            "connection_epoch": self.connection_epoch, **details,
        })

    def _request_resnapshot(self, ws, *, expected: int, received: int) -> None:
        orderbook_sid = self.channel_sids.get("orderbook_delta")
        if orderbook_sid is None:
            self._health("resnapshot_unavailable", reason="orderbook_sid_unknown",
                         expected_sequence=expected, received_sequence=received)
            return
        command = {
            "id": self.next_command_id, "cmd": "update_subscription",
            "params": {"sid": orderbook_sid, "action": "get_snapshot",
                       "market_tickers": self.tickers},
        }
        self.next_command_id += 1
        ws.send(json.dumps(command))
        self._health("resnapshot_requested", subscription_id=orderbook_sid,
                     command_id=command["id"], expected_sequence=expected,
                     received_sequence=received,
                     market_ticker_count=len(self.tickers))

    def _checkpoint(self) -> None:
        if not self.replay.books:
            return
        self.sinks["checkpoints"].append(self.replay.checkpoint())

    def _on_message(self, ws, raw: str):
        received_ms = _now_ms()
        received_at = _iso_from_ms(received_ms)
        self.last_message_ts = received_ms
        parse_error = None
        try:
            msg = json.loads(raw)
            if not isinstance(msg, dict):
                raise ValueError("top-level WebSocket payload is not an object")
        except (json.JSONDecodeError, ValueError) as exc:
            msg = {}
            parse_error = str(exc)
        body = msg.get("msg", msg)
        if not isinstance(body, dict):
            body = {}
        mtype = msg.get("type") or msg.get("event") or ""
        seq = msg.get("seq", msg.get("sequence", msg.get("sequence_number")))
        sid_value = msg.get("sid", msg.get("subscription_id"))
        exchange_at, exchange_ms = exchange_timestamp(msg)
        ticker = body.get("market_ticker") or body.get("ticker")
        metadata = {
            "version": "kalshi-ws-raw-v1", "received_at": received_at,
            "received_ts": received_at, "received_ts_ms": received_ms,
            "processed_at": utcnow(), "connection_epoch": self.connection_epoch,
            "exchange_timestamp": exchange_at,
            "exchange_timestamp_ms": exchange_ms,
            "receive_latency_ms": received_ms - exchange_ms if exchange_ms is not None else None,
            "market_ticker": ticker, "event_ticker": body.get("event_ticker"),
            "channel": mtype, "message_type": mtype,
            "sequence_id": seq, "subscription_id": sid_value,
            "raw_sha256": hashlib.sha256(raw.encode()).hexdigest(),
            "raw_json": raw, "parse_error": parse_error,
        }
        # The exact wire frame is the source of truth and is always appended,
        # including malformed, duplicate, and out-of-order frames.
        self.sinks["raw"].append(metadata)
        if parse_error:
            self._health("parser_failure", error=parse_error,
                         raw_sha256=metadata["raw_sha256"])
            self._write_state(True)
            return
        fingerprint = hashlib.sha256(raw.encode()).hexdigest()
        if fingerprint in self.message_ids:
            self._health("duplicate_frame", raw_sha256=fingerprint,
                         subscription_id=sid_value, sequence_id=seq)
            return
        self.message_ids.add(fingerprint)
        if len(self.message_ids) > 100_000:
            self.message_ids.clear()
        if mtype == "subscribed" and isinstance(msg.get("msg"), dict):
            channel = msg["msg"].get("channel")
            actual_sid = msg["msg"].get("sid")
            if isinstance(channel, str) and isinstance(actual_sid, int):
                self.channel_sids[channel] = actual_sid
        stream = f"{self.connection_epoch}:{sid_value if sid_value is not None else ''}"
        prior = self.last_sequence.get(stream)
        gap = isinstance(seq, int) and prior is not None and seq > prior + 1
        if isinstance(seq, int) and prior is not None and seq <= prior:
            self._health("out_of_order_frame", subscription_id=sid_value,
                         prior_sequence=prior, received_sequence=seq)
            return
        if gap:
            self.sequence_gaps += 1
            self._health("sequence_gap", subscription_id=sid_value,
                         expected_sequence=prior + 1, received_sequence=seq,
                         affected_market_tickers=self.tickers)
        if isinstance(seq, int):
            self.last_sequence[stream] = seq
        if mtype in ("orderbook_snapshot", "orderbook_delta"):
            applied_ticker = self.replay.apply_record(metadata)
            if applied_ticker:
                self.book_events += 1
                if mtype == "orderbook_snapshot":
                    self._health("book_snapshot_applied", market_ticker=applied_ticker,
                                 sequence_id=seq,
                                 quarantine_cleared=not self.replay.books[applied_ticker].quarantined)
                if self.checkpoint_every and self.book_events % self.checkpoint_every == 0:
                    self._checkpoint()
            if gap:
                self._request_resnapshot(ws, expected=prior + 1, received=seq)
        if mtype in ("orderbook_snapshot", "orderbook_delta"):
            self.sinks["orderbook"].write(msg, metadata=metadata)
        elif mtype == "ticker":
            self.sinks["ticker"].write(msg, metadata=metadata)
        elif mtype == "trade":
            self.sinks["trade"].write(msg, metadata=metadata)
        elif mtype in ("market_lifecycle", "market_lifecycle_v2"):
            self.sinks["lifecycle"].write(msg, metadata=metadata)
        elif mtype == "subscribed":
            print(f"[ws] subscribed ack: {msg}", flush=True)
        elif mtype == "error":
            print(f"[ws] ERROR: {msg}", flush=True)
        self._write_state(True)
        # ping/pong control frames are handled by the library automatically

    def _on_error(self, ws, error):
        print(f"[ws] error: {error}", flush=True)
        self._health("websocket_error", error=str(error))

    def _on_close(self, ws, code, reason):
        print(f"[ws] closed code={code} reason={reason!r}", flush=True)
        self._health("disconnected", close_code=code, reason=str(reason))

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
        self.connection_epoch += 1
        self.replay.connection_epoch = self.connection_epoch
        self.replay.last_sequence.clear()
        self.last_sequence.clear()
        for book in self.replay.books.values():
            book.quarantined = True
        self.channel_sids.clear()
        for sink in self.sinks.values():
            sink.set_connection_epoch(self.connection_epoch)
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
        timer = None
        if self.run_seconds:
            # ``run_forever`` blocks while the socket is healthy, so the
            # outer deadline alone cannot stop a bounded capture. Set the
            # shared stop event from a daemon timer and let websocket-client
            # return through its normal close path.
            def _stop_socket():
                _STOP.set()
                ws.close()
            timer = threading.Timer(self.run_seconds, _stop_socket)
            timer.daemon = True
            timer.start()
        try:
            ws.run_forever(ping_interval=10, ping_timeout=8)
        finally:
            if timer is not None:
                timer.cancel()


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
    ap.add_argument("--checkpoint-every", type=int, default=1000,
                    help="append a deterministic book checkpoint every N book events (0 disables)")
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
              "(or KALSHI_CREDENTIAL_FILE/KALSHI_WS_EXTRA_HEADERS for the access-key handshake) "
              "to enable live collection.", file=sys.stderr)
        return 2

    if websocket is None:
        print("\nwebsocket-client is required; run: "
              "pip install websocket-client", file=sys.stderr)
        return 2

    _STOP.clear()
    signal.signal(signal.SIGINT, lambda *_: _STOP.set())
    signal.signal(signal.SIGTERM, lambda *_: _STOP.set())

    if args.checkpoint_every < 0:
        ap.error("--checkpoint-every must be non-negative")
    collector = Collector(args.channels, tickers, ws_dir, args.run_seconds,
                          checkpoint_every=args.checkpoint_every)
    collector.run()
    print("collector stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

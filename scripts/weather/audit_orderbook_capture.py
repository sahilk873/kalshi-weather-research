"""Audit captured Kalshi WebSocket JSONL without inventing book history."""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


def _dt(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def _epoch(record: dict) -> int:
    try:
        return int(record.get("connection_epoch", 0) or 0)
    except (TypeError, ValueError):
        return 0


def audit(input_path: Path) -> dict:
    digest = hashlib.sha256(input_path.read_bytes()).hexdigest()
    counts = Counter(); tickers: set[str] = set(); snapshots = 0; populated = 0
    rows = 0; invalid = 0; receipts: list[datetime] = []; prior_seq: dict[str, int] = {}
    gaps = 0; resets = 0
    exchange_timestamps = 0; negative_latencies = 0
    # A daily file may contain multiple reconnect sessions. When the collector
    # supplies connection epochs, audit only the newest epoch for executable
    # continuity; older epochs remain immutable evidence but cannot be mixed
    # into one reconstructed book.
    epoch_values = []
    with input_path.open() as handle:
        for line in handle:
            if line.strip():
                try:
                    epoch_values.append(_epoch(json.loads(line)))
                except (json.JSONDecodeError, TypeError, ValueError):
                    pass
    latest_epoch = max(epoch_values) if epoch_values else 0
    ignored_prior_rows = 0
    with input_path.open() as handle:
        for line in handle:
            if not line.strip():
                continue
            rows += 1
            try:
                record = json.loads(line)
                message = record.get("message")
                if not isinstance(message, dict) and isinstance(record.get("raw_json"), str):
                    message = json.loads(record["raw_json"])
                if not isinstance(message, dict):
                    message = record
            except json.JSONDecodeError:
                invalid += 1; continue
            if record.get("parse_error"):
                invalid += 1
                continue
            if latest_epoch and _epoch(record) != latest_epoch:
                ignored_prior_rows += 1
                continue
            typ = message.get("type", ""); counts[typ] += 1
            receipt = _dt(record.get("received_at", record.get("received_ts", "")))
            if receipt is not None: receipts.append(receipt)
            if record.get("exchange_timestamp") or record.get("exchange_timestamp_ms") is not None:
                exchange_timestamps += 1
            latency = record.get("receive_latency_ms")
            if isinstance(latency, (int, float)) and latency < 0:
                negative_latencies += 1
            body = message.get("msg", message)
            if body.get("market_ticker"): tickers.add(body["market_ticker"])
            seq = message.get("seq", body.get("seq", message.get("sequence")))
            if isinstance(seq, int):
                stream = str(message.get("sid", message.get("subscription_id", "")))
                prior = prior_seq.get(stream)
                if prior is not None:
                    if seq > prior + 1: gaps += 1
                    elif seq <= prior: resets += 1
                prior_seq[stream] = seq
            if typ == "orderbook_snapshot":
                snapshots += 1
                if body.get("yes_dollars_fp") or body.get("no_dollars_fp") or body.get("yes") or body.get("no"):
                    populated += 1
    return {
        "version": "orderbook-capture-audit-v1", "input": str(input_path),
        "sha256": digest, "rows": rows, "invalid_rows": invalid,
        "latest_connection_epoch": latest_epoch, "ignored_prior_session_rows": ignored_prior_rows,
        "message_types": dict(sorted(counts.items())),
        "market_tickers": sorted(tickers), "ticker_count": len(tickers),
        "snapshot_count": snapshots, "populated_snapshot_count": populated,
        "sequence_gaps": gaps, "sequence_resets": resets,
        "exchange_timestamp_count": exchange_timestamps,
        "negative_receive_latency_count": negative_latencies,
        "first_received_ts": min(receipts).isoformat().replace("+00:00", "Z") if receipts else "",
        "last_received_ts": max(receipts).isoformat().replace("+00:00", "Z") if receipts else "",
        "full_depth_evidence": populated > 0 and invalid == 0,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.input)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({k: result[k] for k in ("rows", "ticker_count", "snapshot_count", "populated_snapshot_count", "sequence_gaps", "full_depth_evidence")}, sort_keys=True))


if __name__ == "__main__":
    main()

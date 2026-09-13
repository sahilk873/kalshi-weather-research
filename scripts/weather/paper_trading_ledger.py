"""Append-only research paper-trading ledger; never submits real orders."""
from __future__ import annotations

import argparse, csv, json
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Mapping

from prediction_manifest import validate_manifest

FIELDS = ["record_id", "record_type", "recorded_at_utc", "manifest_path", "market_ticker", "decision_ts", "side", "quantity", "price", "fee", "settled_yes", "net_payoff", "scenario"]
TYPES = {"prediction", "would_have_order", "simulated_fill", "settlement"}


def validate_manifest_file(path: Path) -> list[str]:
    """Validate one immutable prediction manifest before telemetry is emitted."""
    if not path.exists() or not path.is_file():
        return ["manifest does not exist"]
    try:
        payload = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return ["manifest is not valid JSON"]
    if not isinstance(payload, Mapping):
        return ["manifest must be a JSON object"]
    return validate_manifest(payload)

def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

def validate_record(record: Mapping[str, object], manifest_paths: set[str] | None = None) -> list[str]:
    errors = []
    for field in ("record_id", "record_type", "recorded_at_utc", "market_ticker"):
        if not str(record.get(field, "")).strip(): errors.append(f"missing {field}")
    if record.get("record_type") not in TYPES: errors.append("invalid record_type")
    try: datetime.fromisoformat(str(record.get("recorded_at_utc", "")).replace("Z", "+00:00"))
    except ValueError: errors.append("invalid recorded_at_utc")
    if record.get("manifest_path") and manifest_paths is not None and str(record["manifest_path"]) not in manifest_paths:
        errors.append("manifest_path does not reference a known manifest")
    if record.get("record_type") in {"prediction", "would_have_order", "simulated_fill"} and not str(record.get("manifest_path", "")).strip():
        errors.append("manifest_path required for trading records")
    return errors

def append_records(path: Path, records: Iterable[Mapping[str, object]], manifest_paths: set[str] | None = None) -> int:
    existing = set()
    if path.exists():
        for line in path.read_text().splitlines():
            try: existing.add(str(json.loads(line).get("record_id", "")))
            except json.JSONDecodeError: raise ValueError("ledger contains invalid JSON")
    encoded = []
    for record in records:
        errors = validate_record(record, manifest_paths)
        if errors: raise ValueError("invalid ledger record: " + "; ".join(errors))
        rid = str(record["record_id"])
        if rid in existing: raise ValueError(f"duplicate ledger record_id: {rid}")
        existing.add(rid); encoded.append(json.dumps({field: record.get(field, "") for field in FIELDS}, sort_keys=True))
    if encoded:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a") as handle:
            handle.write("\n".join(encoded) + "\n")
    return len(encoded)

def from_execution_rows(rows: Iterable[Mapping[str, object]], manifest_path: str) -> list[dict]:
    """Convert conservative simulator rows into would-have-order/fill records."""
    output = []
    for row in rows:
        ticker = str(row.get("market_ticker", "")); scenario = str(row.get("scenario", "base")); decision = row.get("decision_time_utc", "")
        if not ticker: continue
        base = f"{ticker}|{scenario}|{row.get('execution_candle_end', '')}"
        common = {"recorded_at_utc": _now(), "manifest_path": manifest_path, "market_ticker": ticker, "decision_ts": decision, "side": "yes", "quantity": 1, "scenario": scenario}
        output.append({**common, "record_id": base + "|order", "record_type": "would_have_order", "price": row.get("signal_yes_ask", ""), "fee": "", "settled_yes": "", "net_payoff": ""})
        output.append({**common, "record_id": base + "|fill", "record_type": "simulated_fill", "price": row.get("fill_price", ""), "fee": row.get("fee", ""), "settled_yes": row.get("settled_yes", ""), "net_payoff": row.get("one_contract_net_payoff", "")})
    return output

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument("--execution", type=Path, required=True); parser.add_argument("--manifest-path", required=True); parser.add_argument("--output", type=Path, required=True); args = parser.parse_args()
    manifest = Path(args.manifest_path)
    if not manifest.exists() or not manifest.is_file():
        raise SystemExit(f"manifest does not exist: {args.manifest_path}")
    errors = validate_manifest_file(manifest)
    if errors:
        raise SystemExit("manifest failed validation: " + "; ".join(errors))
    with args.execution.open(newline="") as handle: rows = list(csv.DictReader(handle))
    count = append_records(args.output, from_execution_rows(rows, str(manifest)))
    print(f"appended {count} paper-trading records to {args.output}")

if __name__ == "__main__": main()

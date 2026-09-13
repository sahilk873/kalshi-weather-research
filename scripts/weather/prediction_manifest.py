"""Immutable, reproducible prediction manifests for the report-2 pipeline.

Every prediction must be reproducible from an immutable manifest carrying the
point-in-time decision clock, the market identity (``market_ticker`` and
``target_time_utc`` so the manifest can join its contract), feature/model/
calibrator versions, source run and observation provenance, the settlement
rules hash, and the code commit (deep-research-report (2).md, "Every
prediction should be reproducible from an immutable manifest").

Design constraints (stdlib only):

- Missing or unparseable PIT (``decision_ts``), provenance, rules, or market
  identity fields fail closed: ``write_manifest`` refuses to write and
  returns the validation errors.
- ``prediction`` must be a finite number within ``[0, 1]``.
- ``source_run_ids`` / ``observation_ids`` are resolved against *supplied*
  provenance indexes (optional CSV or in-memory mappings). An id missing from
  an index fails closed; a matching index record whose receipt/issue (or
  availability) timestamp is present but after ``decision_ts`` also fails
  closed. When no index supplies timestamp metadata, no timing claim is made.
- When a contract index is supplied, ``market_ticker`` must resolve,
  ``target_time_utc`` must equal the contract's, and ``rules_hash`` must equal
  the contract row's settlement rules hash.
- ``code_commit`` must be a 7-40 hex git commit (abbreviated or full) or
  ``HEAD``; empty values fail closed.
- Output is deterministic sorted-key JSON so byte-for-byte reproduction is
  possible from identical inputs.
- Writes are immutable and idempotent: identical content at an existing path is
  a no-op, different content at an existing path raises rather than mutating,
  and new files are written atomically via ``os.replace``. Parent directories
  (including nested ``model_version=<version>/`` keys) are created only after
  validation succeeds.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import re
from hashlib import sha256
from pathlib import Path
from typing import Iterable, Mapping

from common import parse_utc_iso
from pit import ISSUE_TIME_FIELDS, RECEIPT_TIME_FIELDS

RESEARCH_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "weather_research"

REQUIRED_FIELDS = (
    "decision_ts",
    "feature_version",
    "model_version",
    "calibrator_version",
    "source_run_ids",
    "observation_ids",
    "rules_hash",
    "code_commit",
    "prediction",
    "market_ticker",
    "target_time_utc",
)

COMMIT_RE = re.compile(r"[0-9a-fA-F]{7,40}")

# Availability fields an observation-index row may carry. These are genuine
# receipt/availability clocks; ``valid_utc`` describes what a record is about
# and is intentionally not treated as availability here (see ``pit``).
OBSERVATION_AVAILABILITY_FIELDS = RECEIPT_TIME_FIELDS + (
    "available_ts",
    "availability_time_utc",
    "label_available_ts",
)

FORECAST_ROW_FIELDS = (
    "market_ticker",
    "target_time_utc",
    "decision_time_utc",
    "prediction",
    "feature_version",
    "model_version",
    "calibrator_version",
    "code_commit",
)


def build_manifest(
    *,
    decision_ts: str,
    feature_version: str,
    model_version: str,
    calibrator_version: str,
    source_run_ids: list[str],
    observation_ids: list[str],
    rules_hash: str,
    code_commit: str,
    prediction: float,
    market_ticker: str,
    target_time_utc: str,
) -> dict:
    """Construct a manifest dict in the report's canonical field order."""
    return {
        "decision_ts": decision_ts,
        "feature_version": feature_version,
        "model_version": model_version,
        "calibrator_version": calibrator_version,
        "source_run_ids": list(source_run_ids),
        "observation_ids": list(observation_ids),
        "rules_hash": rules_hash,
        "code_commit": code_commit,
        "prediction": prediction,
        "market_ticker": market_ticker,
        "target_time_utc": target_time_utc,
    }


def read_index(path: Path | None, id_column: str) -> dict:
    """Load a CSV provenance index keyed by ``id_column``.

    Each row becomes ``{id: row}``; rows with a blank id are skipped. The
    returned mapping is used for fail-closed id resolution and, when a row
    carries receipt/issue/availability timestamp columns, point-in-time
    enforcement against ``decision_ts``.
    """
    index: dict[str, dict] = {}
    if path is None or not path.exists():
        return index
    with path.open(newline="") as fh:
        for row in csv.DictReader(fh):
            rid = row.get(id_column, "")
            rid = rid.strip() if isinstance(rid, str) else ""
            if rid:
                index[rid] = row
    return index


def _contract_index(contracts: Iterable[Mapping] | Mapping | None) -> dict | None:
    """Normalize a contracts supplier to ``{market_ticker: row}``."""
    if contracts is None:
        return None
    if isinstance(contracts, Mapping):
        return {str(key): dict(row) for key, row in contracts.items()}
    index: dict[str, dict] = {}
    for row in contracts:
        ticker = row.get("market_ticker", "")
        ticker = str(ticker).strip() if ticker is not None else ""
        if ticker:
            index[ticker] = dict(row)
    return index


def _split_ids(value: object) -> list[str]:
    if value is None:
        return []
    parts = re.split(r"[;,|]+", str(value).strip())
    return [part.strip() for part in parts if part.strip()]


def validate_manifest(
    manifest: Mapping[str, object],
    *,
    contracts: Iterable[Mapping] | Mapping | None = None,
    source_index: Mapping[str, object] | None = None,
    observation_index: Mapping[str, object] | None = None,
) -> list[str]:
    """Return a list of validation errors; an empty list means the manifest is valid.

    Fails closed on missing/empty PIT, provenance, rules, or market-identity
    fields, unparseable ``decision_ts`` / ``target_time_utc``, malformed id
    lists, code-commit formats, predictions outside ``[0, 1]``, ids that
    cannot be resolved in a supplied provenance index, index records whose
    receipt/issue/availability timestamp is after ``decision_ts``, and
    contract rows whose ``target_time_utc`` or ``rules_hash`` differ.
    """
    errors: list[str] = []
    for field in REQUIRED_FIELDS:
        value = manifest.get(field)
        if value is None or value == "" or (isinstance(value, list) and not value):
            errors.append(f"missing or empty {field}")
            continue
        if isinstance(value, list) and not all(str(item).strip() for item in value):
            errors.append(f"empty entry in {field}")
    if parse_utc_iso(manifest.get("decision_ts")) is None:
        errors.append("decision_ts is not a parseable UTC timestamp")
    if parse_utc_iso(manifest.get("target_time_utc")) is None:
        errors.append("target_time_utc is not a parseable UTC timestamp")
    if not isinstance(manifest.get("source_run_ids"), list):
        errors.append("source_run_ids must be a list")
    if not isinstance(manifest.get("observation_ids"), list):
        errors.append("observation_ids must be a list")
    try:
        prediction = float(manifest.get("prediction"))
        if not math.isfinite(prediction) or not (0.0 <= prediction <= 1.0):
            errors.append("prediction must be a finite probability in [0,1]")
    except (TypeError, ValueError):
        errors.append("prediction must be a finite probability in [0,1]")
    if not _valid_code_commit(manifest.get("code_commit")):
        errors.append("code_commit must be a git commit hash (7-40 hex chars) or HEAD")

    decision = parse_utc_iso(manifest.get("decision_ts"))

    contract_index = _contract_index(contracts)
    if contract_index is not None:
        _check_contract(manifest, contract_index, errors)

    if source_index is not None:
        _resolve_provenance(
            manifest.get("source_run_ids"), source_index, decision,
            "source_run_id", RECEIPT_TIME_FIELDS, ISSUE_TIME_FIELDS, errors,
        )
    if observation_index is not None:
        _resolve_provenance(
            manifest.get("observation_ids"), observation_index, decision,
            "observation_id", OBSERVATION_AVAILABILITY_FIELDS, (), errors,
        )
    return errors


def _valid_code_commit(value: object) -> bool:
    if value is None:
        return False
    text = str(value).strip()
    if not text:
        return False
    return text == "HEAD" or bool(COMMIT_RE.fullmatch(text))


def _check_contract(manifest: Mapping[str, object], contract_index: dict, errors: list[str]) -> None:
    ticker = str(manifest.get("market_ticker", "") or "").strip()
    row = contract_index.get(ticker)
    if row is None:
        errors.append(f"no contract row for market_ticker {ticker}")
        return
    if not row.get("rules_hash"):
        errors.append(f"contract row for {ticker} has no rules_hash")
    elif str(manifest.get("rules_hash", "")).strip() != str(row["rules_hash"]).strip():
        errors.append(f"rules_hash does not match contract row for {ticker}")
    if not row.get("target_time_utc"):
        errors.append(f"contract row for {ticker} has no target_time_utc")
    elif str(manifest.get("target_time_utc", "")).strip() != str(row["target_time_utc"]).strip():
        errors.append(f"target_time_utc does not match contract row for {ticker}")


def _resolve_provenance(
    ids: object,
    index: Mapping[str, object],
    decision,
    label: str,
    receipt_fields: tuple[str, ...],
    issue_fields: tuple[str, ...],
    errors: list[str],
) -> None:
    if not isinstance(ids, list):
        return
    for rid in ids:
        text = str(rid).strip()
        row = index.get(text)
        if row is None:
            errors.append(f"{label} {text} not found in {label}s index")
            continue
        _enforce_before(decision, label, text, row, receipt_fields, "receipt", errors)
        _enforce_before(decision, label, text, row, issue_fields, "issue", errors)


def _enforce_before(
    decision,
    label: str,
    rid: str,
    row: Mapping[str, object],
    fields: tuple[str, ...],
    kind: str,
    errors: list[str],
) -> None:
    """Enforce a present index timestamp is <= decision_ts (fail closed).

    Metadata-absent rows (no candidate field carries a value) are allowed so
    indexes without availability clocks can still be used for id resolution.
    """
    if decision is None:
        return
    for field in fields:
        value = row.get(field)
        if value is None or not str(value).strip():
            continue
        parsed = parse_utc_iso(value)
        if parsed is None:
            errors.append(
                f"{label} {rid} {kind} time {field}={value!r} is not a parseable UTC timestamp"
            )
        elif parsed > decision:
            errors.append(f"{label} {rid} {kind} time is after decision_ts")


def encode_manifest(manifest: Mapping[str, object]) -> str:
    """Deterministic sorted-key JSON (keys sorted, Unix newline terminator)."""
    return json.dumps(dict(manifest), indent=2, sort_keys=True) + "\n"


def manifest_key(manifest: Mapping[str, object]) -> str:
    """Content-derived key so equal manifests map to the same immutable path.

    Callers (including the quality gate) rederive this from the parsed payload
    to detect filename/hash drift and duplicate logical manifests.
    """
    return sha256(encode_manifest(manifest).encode("utf-8")).hexdigest()[:16]


def write_manifest(
    output_dir: Path,
    manifest: Mapping[str, object],
    key: str | None = None,
    *,
    contracts: Iterable[Mapping] | Mapping | None = None,
    source_index: Mapping[str, object] | None = None,
    observation_index: Mapping[str, object] | None = None,
) -> Path:
    """Validate and atomically write one immutable prediction manifest.

    ``key`` overrides the default content-derived filename for callers that
    need to pin a specific path (for example ``model_version=<v>/....json``);
    an existing path with different content raises instead of being
    overwritten. Parent directories are created only after validation
    succeeds, and the file is swapped into place via ``os.replace``.
    """
    errors = validate_manifest(
        manifest,
        contracts=contracts,
        source_index=source_index,
        observation_index=observation_index,
    )
    if errors:
        raise ValueError("invalid prediction manifest: " + "; ".join(errors))
    name = (key or ("manifest_" + manifest_key(manifest) + ".json"))
    if not name.endswith(".json"):
        name += ".json"
    path = output_dir / name
    text = encode_manifest(manifest)
    if path.exists():
        if path.read_text() != text:
            raise ValueError(f"refusing to overwrite existing immutable manifest: {path}")
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.parent / (path.name + ".tmp")
    tmp.write_text(text)
    os.replace(tmp, path)
    return path


def _forecast_row_manifest(row: Mapping[str, object], contract_index: dict | None) -> dict:
    ticker = str(row.get("market_ticker", "") or "").strip()
    rules_hash = row.get("rules_hash") or ""
    if not rules_hash and contract_index is not None and ticker in contract_index:
        rules_hash = str(contract_index[ticker].get("rules_hash", "") or "").strip()
    try:
        prediction = float(row.get("prediction"))
    except (TypeError, ValueError):
        prediction = row.get("prediction")
    return build_manifest(
        decision_ts=row.get("decision_time_utc") or row.get("decision_ts"),
        feature_version=row.get("feature_version"),
        model_version=row.get("model_version"),
        calibrator_version=row.get("calibrator_version"),
        source_run_ids=_split_ids(row.get("source_run_ids") or row.get("source_run_id")),
        observation_ids=_split_ids(row.get("observation_ids") or row.get("observation_id")),
        rules_hash=rules_hash,
        code_commit=row.get("code_commit"),
        prediction=prediction,
        market_ticker=ticker,
        target_time_utc=row.get("target_time_utc"),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=RESEARCH_DIR / "predictions")
    parser.add_argument(
        "--forecasts", type=Path, metavar="CSV",
        help="existing forecast CSV with one row per prediction (market_ticker, "
             "target_time_utc, decision_time_utc, prediction, feature_version, "
             "model_version, calibrator_version, code_commit, plus source_run_id(s) "
             "and observation_id(s)); a row-level rules_hash is used unless "
             "--contracts supplies it",
    )
    parser.add_argument("--contracts", type=Path, metavar="CSV",
                        help="contract CSV (e.g. kalshi_hourly/contracts.csv) keyed by "
                             "market_ticker; target_time_utc and rules_hash are verified "
                             "against each manifest")
    parser.add_argument("--source-index", type=Path, metavar="CSV",
                        help="optional source-run index keyed by source_run_id with "
                             "receipt/issue timestamp columns")
    parser.add_argument("--observation-index", type=Path, metavar="CSV",
                        help="optional observation index keyed by observation_id with "
                             "availability timestamp columns")
    parser.add_argument("--organize-by-model-version", action="store_true",
                        help="write manifests under predictions/model_version=<v>/")
    parser.add_argument("--decision-ts", help="UTC ISO decision clock")
    parser.add_argument("--feature-version")
    parser.add_argument("--model-version")
    parser.add_argument("--calibrator-version")
    parser.add_argument("--rules-hash")
    parser.add_argument("--code-commit")
    parser.add_argument("--prediction", type=float)
    parser.add_argument("--market-ticker")
    parser.add_argument("--target-time-utc")
    parser.add_argument("--source-run-ids", action="extend", nargs="+", default=[], metavar="ID")
    parser.add_argument("--observation-ids", action="extend", nargs="+", default=[], metavar="ID")
    args = parser.parse_args()

    contract_index = read_index(args.contracts, "market_ticker") if args.contracts else None
    source_index = read_index(args.source_index, "source_run_id") if args.source_index else None
    observation_index = read_index(args.observation_index, "observation_id") if args.observation_index else None
    context = dict(contracts=contract_index, source_index=source_index, observation_index=observation_index)

    if args.forecasts:
        with args.forecasts.open(newline="") as fh:
            rows = list(csv.DictReader(fh))
        if not rows:
            raise SystemExit("invalid prediction manifest: forecast CSV is empty")
        missing = set(FORECAST_ROW_FIELDS) - set(rows[0])
        if missing:
            raise SystemExit(f"invalid prediction manifest: forecast CSV missing columns {sorted(missing)}")
        manifests = [_forecast_row_manifest(row, contract_index) for row in rows]
        for manifest in manifests:
            errors = validate_manifest(manifest, **context)
            if errors:
                raise SystemExit("invalid prediction manifest: " + "; ".join(errors))
    else:
        manifests = [build_manifest(
            decision_ts=args.decision_ts,
            feature_version=args.feature_version,
            model_version=args.model_version,
            calibrator_version=args.calibrator_version,
            source_run_ids=[str(x).strip() for x in args.source_run_ids],
            observation_ids=[str(x).strip() for x in args.observation_ids],
            rules_hash=args.rules_hash,
            code_commit=args.code_commit,
            prediction=args.prediction,
            market_ticker=args.market_ticker,
            target_time_utc=args.target_time_utc,
        )]
        errors = validate_manifest(manifests[0], **context)
        if errors:
            raise SystemExit("invalid prediction manifest: " + "; ".join(errors))

    for manifest in manifests:
        key = None
        if args.organize_by_model_version:
            key = f"model_version={manifest['model_version']}/manifest_{manifest_key(manifest)}.json"
        path = write_manifest(args.output_dir, manifest, key, **context)
        print(path)


if __name__ == "__main__":
    main()
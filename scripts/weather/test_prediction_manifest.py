import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from prediction_manifest import (
    REQUIRED_FIELDS,
    build_manifest,
    encode_manifest,
    manifest_key,
    read_index,
    validate_manifest,
    write_manifest,
)
from data_quality_gates import _prediction_manifest_audit, audit
from audit_artifact_inventory import inventory

RULES_HASH = "86cc4935afe7cf34d7f013c25cb56c1e3baa7877baa9be963f2da8a37a0ad8dc"
COMMIT = "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b"
TICKER = "KXTEMPNYCH-26SEP1010-T70.99"
TARGET = "2026-09-10T14:00:00Z"


def sample(**overrides):
    return build_manifest(
        decision_ts=overrides.get("decision_ts", "2026-09-12T12:00:00Z"),
        feature_version=overrides.get("feature_version", "features-v3"),
        model_version=overrides.get("model_version", "climatology-v2"),
        calibrator_version=overrides.get("calibrator_version", "beta-cal-v1"),
        source_run_ids=overrides.get("source_run_ids", ["run-20260912-00z"]),
        observation_ids=overrides.get("observation_ids", ["obs-1000"]),
        rules_hash=overrides.get("rules_hash", RULES_HASH),
        code_commit=overrides.get("code_commit", COMMIT),
        prediction=overrides.get("prediction", 0.6371),
        market_ticker=overrides.get("market_ticker", TICKER),
        target_time_utc=overrides.get("target_time_utc", TARGET),
    )


def contract_row(**overrides):
    return {
        "market_ticker": overrides.get("market_ticker", TICKER),
        "target_time_utc": overrides.get("target_time_utc", TARGET),
        "rules_hash": overrides.get("rules_hash", RULES_HASH),
    }


class PredictionManifestTest(unittest.TestCase):
    def test_well_formed_manifest_validates(self):
        self.assertEqual(validate_manifest(sample()), [])

    def test_each_required_field_fails_closed_when_missing(self):
        for field in REQUIRED_FIELDS:
            manifest = sample()
            manifest.pop(field)
            errors = validate_manifest(manifest)
            self.assertTrue(any(field in error for error in errors),
                            f"{field} should be flagged as missing")

    def test_empty_provenance_lists_fail_closed(self):
        manifest = sample(source_run_ids=[], observation_ids=[])
        errors = validate_manifest(manifest)
        self.assertTrue(any("source_run_ids" in e for e in errors))
        self.assertTrue(any("observation_ids" in e for e in errors))

    def test_missing_rules_hash_fails_closed(self):
        self.assertTrue(any("rules_hash" in e for e in validate_manifest(sample(rules_hash=""))))

    def test_missing_market_identity_fails_closed(self):
        errors = validate_manifest(sample(market_ticker="", target_time_utc=""))
        self.assertTrue(any("market_ticker" in e for e in errors))
        self.assertTrue(any("target_time_utc" in e for e in errors))

    def test_unparseable_decision_ts_fails_closed(self):
        errors = validate_manifest(sample(decision_ts="not-a-time"))
        self.assertTrue(any("decision_ts" in e for e in errors))

    def test_unparseable_target_time_fails_closed(self):
        errors = validate_manifest(sample(target_time_utc="not-a-time"))
        self.assertTrue(any("target_time_utc" in e for e in errors))

    def test_non_finite_and_out_of_range_prediction_fails_closed(self):
        for value in (float("nan"), float("inf"), "bogus", 1.5, -0.1, 1.0001, -0.0001):
            errors = validate_manifest(sample(prediction=value))
            self.assertTrue(any("prediction" in e for e in errors), value)

    def test_boundary_predictions_accepted(self):
        self.assertEqual(validate_manifest(sample(prediction=0.0)), [])
        self.assertEqual(validate_manifest(sample(prediction=1.0)), [])

    def test_code_commit_format(self):
        self.assertEqual(validate_manifest(sample(code_commit="HEAD")), [])
        self.assertEqual(validate_manifest(sample(code_commit="a1b2c3d")), [])
        for bad in ("abc123", "not hex!!", "a" * 41):
            errors = validate_manifest(sample(code_commit=bad))
            self.assertTrue(any("code_commit" in e for e in errors), bad)

    def test_contract_verification(self):
        self.assertEqual(validate_manifest(sample(), contracts=[contract_row()]), [])

    def test_contract_wrong_rules_hash_fails(self):
        errors = validate_manifest(sample(), contracts=[contract_row(rules_hash="0" * 64)])
        self.assertTrue(any("rules_hash" in e for e in errors))

    def test_contract_wrong_target_time_fails(self):
        errors = validate_manifest(sample(), contracts=[contract_row(target_time_utc="2026-09-10T15:00:00Z")])
        self.assertTrue(any("target_time_utc" in e for e in errors))

    def test_contract_missing_row_fails_closed(self):
        errors = validate_manifest(sample(), contracts=[contract_row(market_ticker="KXOTHER-1-T1")])
        self.assertTrue(any("no contract row" in e for e in errors))

    def test_source_index_resolution(self):
        index = {"run-20260912-00z": {"source_receipt_time": "2026-09-12T11:00:00Z",
                                      "initialization_time_utc": "2026-09-12T00:00:00Z"}}
        self.assertEqual(validate_manifest(sample(), source_index=index), [])

    def test_source_index_unknown_id_fails_closed(self):
        errors = validate_manifest(sample(source_run_ids=["unknown-run"]),
                                   source_index={"run-20260912-00z": {}})
        self.assertTrue(any("not found" in e for e in errors))

    def test_source_receipt_after_decision_fails(self):
        index = {"run-20260912-00z": {"source_receipt_time": "2026-09-12T13:00:00Z"}}
        errors = validate_manifest(sample(), source_index=index)
        self.assertTrue(any("after decision_ts" in e for e in errors))

    def test_observation_index_resolution_and_timing(self):
        early = {"obs-1000": {"available_ts": "2026-09-12T11:30:00Z"}}
        self.assertEqual(validate_manifest(sample(), observation_index=early), [])
        late = {"obs-1000": {"available_ts": "2026-09-12T12:30:00Z"}}
        errors = validate_manifest(sample(), observation_index=late)
        self.assertTrue(any("after decision_ts" in e for e in errors))
        missing = validate_manifest(sample(observation_ids=["obs-missing"]), observation_index=early)
        self.assertTrue(any("not found" in e for e in missing))

    def test_provenance_index_without_metadata_still_resolves(self):
        index = {"run-20260912-00z": {"model": "hrrr", "city": "nyc"}}
        self.assertEqual(validate_manifest(sample(), source_index=index), [])

    def test_encode_manifest_is_deterministic_sorted_json(self):
        first = {"prediction": 0.6371, "rules_hash": "x", "decision_ts": "2026-09-12T12:00:00Z", "source_run_ids": ["a"], "observation_ids": ["b"], "feature_version": "f", "model_version": "m", "calibrator_version": "c", "code_commit": "cc", "market_ticker": TICKER, "target_time_utc": TARGET}
        second = {"code_commit": "cc", "calibrator_version": "c", "model_version": "m", "feature_version": "f", "observation_ids": ["b"], "source_run_ids": ["a"], "decision_ts": "2026-09-12T12:00:00Z", "rules_hash": "x", "prediction": 0.6371, "target_time_utc": TARGET, "market_ticker": TICKER}
        self.assertEqual(encode_manifest(first), encode_manifest(second))

    def test_write_manifest_is_idempotent(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            first = write_manifest(root, sample())
            second = write_manifest(root, sample())
            self.assertEqual(first, second)
            self.assertEqual(len(list(root.glob("*.json"))), 1)
            self.assertEqual(list(root.glob("*.tmp")), [])

    def test_write_manifest_rejects_invalid_without_writing(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            with self.assertRaises(ValueError):
                write_manifest(root, sample(rules_hash=""))
            self.assertEqual(list(root.glob("*.json")), [])

    def test_write_manifest_rejects_out_of_range_without_writing(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            with self.assertRaises(ValueError):
                write_manifest(root, sample(prediction=1.5))
            self.assertEqual(list(root.glob("*.json")), [])

    def test_write_manifest_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            write_manifest(root, sample(), key="pinned")
            with self.assertRaises(ValueError):
                write_manifest(root, sample(prediction=0.5), key="pinned")
            self.assertEqual(len(json.loads((root / "pinned.json").read_text())), len(sample()))

    def test_write_manifest_creates_nested_parents_atomically(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            path = write_manifest(root, sample(), key="model_version=climatology-v2/manifest_abc")
            self.assertTrue(path.parent.is_dir())
            self.assertEqual(path.parent.name, "model_version=climatology-v2")
            self.assertTrue(path.exists())
            self.assertEqual(list(root.glob("**/*.tmp")), [])

    def test_manifest_key_derives_from_content(self):
        self.assertEqual(manifest_key(sample()), manifest_key(sample()))
        self.assertNotEqual(manifest_key(sample()), manifest_key(sample(prediction=0.5)))

    def test_write_manifest_honors_provenance_context(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            index = {"run-20260912-00z": {"source_receipt_time": "2026-09-12T13:00:00Z"}}
            with self.assertRaises(ValueError):
                write_manifest(root, sample(), source_index=index)
            self.assertEqual(list(root.glob("*.json")), [])
            write_manifest(root, sample(), source_index={"run-20260912-00z": {"receipt_time_utc": "2026-09-12T11:00:00Z"}})
            self.assertEqual(len(list(root.glob("*.json"))), 1)


class PredictionManifestGateTest(unittest.TestCase):
    def test_empty_predictions_dir_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            result = audit(Path(d))
            self.assertFalse(result["checks"]["prediction_manifest"]["pass"])

    def test_valid_manifest_passes_audit(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            pred_dir = root / "predictions"
            write_manifest(pred_dir, sample())
            row = _prediction_manifest_audit(root, datetime(2026, 9, 12, 13, 0, tzinfo=timezone.utc))
            self.assertTrue(row["pass"])
            self.assertEqual(row["manifests"], 1)

    def test_missing_rules_hash_manifest_fails_asof(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            pred_dir = root / "predictions"
            write_manifest(pred_dir, sample())
            (pred_dir / "bad.json").write_text(json.dumps({"decision_ts": "2026-09-12T12:00:00Z", "prediction": 0.5}))
            row = _prediction_manifest_audit(root, datetime(2026, 9, 12, 13, 0, tzinfo=timezone.utc))
            self.assertFalse(row["pass"])
            self.assertGreater(row["missing_or_invalid_fields"], 0)

    def test_future_decision_fails(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            pred_dir = root / "predictions"
            write_manifest(pred_dir, sample(decision_ts="2026-09-12T14:00:00Z"))
            row = _prediction_manifest_audit(root, datetime(2026, 9, 12, 13, 0, tzinfo=timezone.utc))
            self.assertFalse(row["pass"])
            self.assertEqual(row["future_decision"], 1)

    def test_invalid_json_file_fails(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            pred_dir = root / "predictions"
            write_manifest(pred_dir, sample())
            (pred_dir / "corrupt.json").write_text("{not json")
            row = _prediction_manifest_audit(root, datetime(2026, 9, 12, 13, 0, tzinfo=timezone.utc))
            self.assertFalse(row["pass"])
            self.assertEqual(row["invalid_json"], 1)

    def test_content_hash_mismatch_fails(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            pred_dir = root / "predictions"
            custom = sample(rules_hash="f" * 64)
            write_manifest(pred_dir, custom, key="manifest_deadbeef")
            row = _prediction_manifest_audit(root, datetime(2026, 9, 12, 13, 0, tzinfo=timezone.utc))
            self.assertFalse(row["pass"])
            self.assertEqual(row["hash_mismatch"], 1)

    def test_model_version_subdirectory_audited_recursively(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            pred_dir = root / "predictions"
            write_manifest(pred_dir, sample(), key="model_version=climatology-v2/manifest_%s.json" % manifest_key(sample()))
            row = _prediction_manifest_audit(root, datetime(2026, 9, 12, 13, 0, tzinfo=timezone.utc))
            self.assertTrue(row["pass"])
            self.assertEqual(row["files"], 1)
            self.assertEqual(row["manifests"], 1)

    def test_model_version_directory_mismatch_fails(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            pred_dir = root / "predictions"
            write_manifest(pred_dir, sample(), key="model_version=other-version/manifest_%s.json" % manifest_key(sample()))
            row = _prediction_manifest_audit(root, datetime(2026, 9, 12, 13, 0, tzinfo=timezone.utc))
            self.assertFalse(row["pass"])
            self.assertEqual(row["model_version_mismatch"], 1)

    def test_duplicate_logical_manifests_fail(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            pred_dir = root / "predictions"
            name = "manifest_%s.json" % manifest_key(sample())
            (pred_dir / "a").mkdir(parents=True)
            (pred_dir / "b").mkdir()
            (pred_dir / "a" / name).write_text(encode_manifest(sample()))
            (pred_dir / "b" / name).write_text(encode_manifest(sample()))
            row = _prediction_manifest_audit(root, datetime(2026, 9, 12, 13, 0, tzinfo=timezone.utc))
            self.assertFalse(row["pass"])
            self.assertEqual(row["duplicate_manifests"], 1)

    def test_gate_verifies_contract_rules_hash(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            pred_dir = root / "predictions"
            contracts_dir = root / "kalshi_hourly"
            contracts_dir.mkdir(parents=True)
            contracts_path = contracts_dir / "contracts.csv"
            contracts_path.write_text("market_ticker,target_time_utc,rules_hash\n")
            with contracts_path.open("a") as fh:
                fh.write(f"{TICKER},{TARGET},{'f' * 64}\n")
            write_manifest(pred_dir, sample())
            row = _prediction_manifest_audit(root, datetime(2026, 9, 12, 13, 0, tzinfo=timezone.utc))
            self.assertFalse(row["pass"])

    def test_gate_contract_index_and_source_index_fail_closed(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            pred_dir = root / "predictions"
            pred_dir.mkdir()
            (pred_dir / "source_index.csv").write_text("source_run_id,source_receipt_time\nrun-missing,2026-09-12T11:00:00Z\n")
            write_manifest(pred_dir, sample(source_run_ids=["run-that-does-not-exist"]))
            row = _prediction_manifest_audit(root, datetime(2026, 9, 12, 13, 0, tzinfo=timezone.utc))
            self.assertFalse(row["pass"])
            self.assertGreater(row["missing_or_invalid_fields"], 0)


class PredictionManifestCLITest(unittest.TestCase):
    SCRIPT = str(Path(__file__).with_name("prediction_manifest.py"))

    def test_cli_explicit_flags_writes_manifest(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            out = root / "predictions"
            args = ["--output-dir", str(out), "--decision-ts", "2026-09-12T12:00:00Z",
                    "--feature-version", "f", "--model-version", "m", "--calibrator-version", "c",
                    "--rules-hash", RULES_HASH, "--code-commit", COMMIT, "--prediction", "0.51",
                    "--market-ticker", TICKER, "--target-time-utc", TARGET,
                    "--source-run-ids", "run-1", "--observation-ids", "obs-1", "obs-2"]
            import subprocess
            result = subprocess.run(["python3", self.SCRIPT] + args, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            files = list(out.glob("manifest_*.json"))
            self.assertEqual(len(files), 1)
            payload = json.loads(files[0].read_text())
            self.assertEqual(payload["market_ticker"], TICKER)
            self.assertEqual(payload["observation_ids"], ["obs-1", "obs-2"])
            self.assertEqual(payload["source_run_ids"], ["run-1"])

    def test_cli_forecast_csv_mode_with_contracts_and_indexes(self):
        import csv as csv_module
        import subprocess
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            out = root / "predictions"
            contracts = root / "contracts.csv"
            with contracts.open("w", newline="") as fh:
                w = csv_module.DictWriter(fh, fieldnames=["market_ticker", "target_time_utc", "rules_hash"])
                w.writeheader()
                w.writerow({"market_ticker": TICKER, "target_time_utc": TARGET, "rules_hash": RULES_HASH})
            src = root / "source_index.csv"
            src.write_text("source_run_id,source_receipt_time,initialization_time_utc\nrun-20260912-00z,2026-09-12T11:00:00Z,2026-09-12T00:00:00Z\n")
            obs = root / "obs_index.csv"
            obs.write_text("observation_id,available_ts\nobs-1000,2026-09-12T11:30:00Z\n")
            forecasts = root / "forecasts.csv"
            with forecasts.open("w", newline="") as fh:
                w = csv_module.DictWriter(fh, fieldnames=[
                    "market_ticker", "target_time_utc", "decision_time_utc", "prediction",
                    "feature_version", "model_version", "calibrator_version", "code_commit",
                    "source_run_ids", "observation_ids"])
                w.writeheader()
                w.writerow({"market_ticker": TICKER, "target_time_utc": TARGET,
                            "decision_time_utc": "2026-09-12T12:00:00Z", "prediction": "0.52",
                            "feature_version": "f", "model_version": "m", "calibrator_version": "c",
                            "code_commit": COMMIT, "source_run_ids": "run-20260912-00z",
                            "observation_ids": "obs-1000"})
            args = ["--output-dir", str(out), "--forecasts", str(forecasts),
                    "--contracts", str(contracts), "--source-index", str(src),
                    "--observation-index", str(obs)]
            result = subprocess.run(["python3", self.SCRIPT] + args, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            files = list(out.glob("manifest_*.json"))
            self.assertEqual(len(files), 1)
            payload = json.loads(files[0].read_text())
            self.assertEqual(payload["market_ticker"], TICKER)
            self.assertEqual(payload["rules_hash"], RULES_HASH)
            self.assertEqual(payload["prediction"], 0.52)

    def test_cli_forecast_csv_bad_rules_fails_closed(self):
        import csv as csv_module
        import subprocess
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            out = root / "predictions"
            contracts = root / "contracts.csv"
            with contracts.open("w", newline="") as fh:
                w = csv_module.DictWriter(fh, fieldnames=["market_ticker", "target_time_utc", "rules_hash"])
                w.writeheader()
                w.writerow({"market_ticker": TICKER, "target_time_utc": TARGET, "rules_hash": "0" * 64})
            forecasts = root / "forecasts.csv"
            with forecasts.open("w", newline="") as fh:
                w = csv_module.DictWriter(fh, fieldnames=["market_ticker", "target_time_utc", "decision_time_utc", "prediction", "feature_version", "model_version", "calibrator_version", "code_commit", "rules_hash", "source_run_id", "observation_id"])
                w.writeheader()
                w.writerow({"market_ticker": TICKER, "target_time_utc": TARGET,
                            "decision_time_utc": "2026-09-12T12:00:00Z", "prediction": "0.52",
                            "feature_version": "f", "model_version": "m", "calibrator_version": "c",
                            "code_commit": COMMIT, "rules_hash": RULES_HASH,
                            "source_run_id": "run-1", "observation_id": "obs-1"})
            result = subprocess.run(["python3", self.SCRIPT,
                                     "--output-dir", str(out), "--forecasts", str(forecasts),
                                     "--contracts", str(contracts)],
                                    capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("rules_hash", result.stderr)
            self.assertEqual(list(out.glob("**/*")), [])

    def test_read_index_loads_rows(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "index.csv"
            path.write_text("source_run_id,source_receipt_time\nabc,2026-09-12T11:00:00Z\n\n,ignored\n")
            index = read_index(path, "source_run_id")
            self.assertEqual(set(index), {"abc"})
            self.assertEqual(index["abc"]["source_receipt_time"], "2026-09-12T11:00:00Z")


class PredictionManifestInventoryTest(unittest.TestCase):
    def test_missing_predictions_counts_zero(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(inventory(Path(d))["prediction_manifests"], 0)
            self.assertEqual(inventory(Path(d))["sqlite_count_mismatches"], [])

    def test_prediction_manifests_are_counted(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            write_manifest(root / "predictions", sample())
            write_manifest(root / "predictions", sample(prediction=0.4))
            self.assertEqual(inventory(root)["prediction_manifests"], 2)

    def test_nested_model_version_manifests_are_counted(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            pred_dir = root / "predictions"
            write_manifest(pred_dir, sample(), key="model_version=climatology-v2/manifest_%s.json" % manifest_key(sample()))
            write_manifest(pred_dir, sample(prediction=0.4), key="model_version=persistence-v1/manifest_%s.json" % manifest_key(sample(prediction=0.4)))
            self.assertEqual(inventory(root)["prediction_manifests"], 2)


if __name__ == "__main__":
    unittest.main()

import unittest

from feature_store import effective_availability, reconstruct_vintages


DECISION = {
    "city": "phx", "contract": "KXHIGHTPHX-26SEP13-T108",
    "target_time_utc": "2026-09-14T07:00:00Z",
    "decision_time_utc": "2026-09-13T12:00:00Z",
}


def feature(**updates):
    row = {
        "city": DECISION["city"], "contract": DECISION["contract"],
        "target_time_utc": DECISION["target_time_utc"],
        "feature_name": "temperature_f", "source": "example-provider",
        "source_event_time": "2026-09-13T11:45:00Z",
        "issue_time": "", "valid_time": "2026-09-13T11:45:00Z",
        "revision": "1", "available_at": "2026-09-13T11:50:00Z",
        "availability_reference_time": "", "retrieved_at": "",
        "value": "100.0", "provenance": "raw/example.json#sha256=abc",
    }
    row.update(updates)
    return row


class FeatureStoreTests(unittest.TestCase):
    def test_exact_boundary_is_inclusive_and_late_feature_is_excluded(self):
        at_boundary = feature(available_at=DECISION["decision_time_utc"])
        late = feature(feature_name="dewpoint_f", available_at="2026-09-13T12:00:01Z")
        rows, rejected = reconstruct_vintages([at_boundary, late], [DECISION])
        self.assertEqual([row["feature_name"] for row in rows], ["temperature_f"])
        self.assertFalse(rejected)
        self.assertEqual(rows[0]["availability_method"], "exact")

    def test_latest_revision_available_at_each_decision_is_selected(self):
        decisions = [
            dict(DECISION, decision_time_utc="2026-09-13T11:55:00Z"),
            dict(DECISION, decision_time_utc="2026-09-13T12:05:00Z"),
        ]
        revision_2 = feature(
            revision="2", value="101.0", available_at="2026-09-13T12:01:00Z",
            provenance="raw/example-r2.json#sha256=def",
        )
        rows, rejected = reconstruct_vintages([feature(), revision_2], decisions)
        self.assertFalse(rejected)
        self.assertEqual([row["revision"] for row in rows], ["1", "2"])
        self.assertEqual([row["value"] for row in rows], ["100.0", "101.0"])

    def test_latency_scenarios_change_historical_admission(self):
        estimated = feature(
            available_at="", retrieved_at="",
            availability_reference_time="2026-09-13T11:58:00Z",
        )
        policies = {"example-provider": {
            "optimistic": 60, "base": 180, "conservative": 600,
            "highly_conservative": 1800,
        }}
        optimistic, optimistic_rejections = reconstruct_vintages(
            [estimated], [DECISION], scenario="optimistic", latency_policies=policies,
        )
        base, base_rejections = reconstruct_vintages(
            [estimated], [DECISION], scenario="base", latency_policies=policies,
        )
        self.assertEqual(len(optimistic), 1)
        self.assertFalse(optimistic_rejections)
        self.assertEqual(optimistic[0]["available_at"], "2026-09-13T11:59:00Z")
        self.assertEqual(optimistic[0]["assumed_latency_seconds"], "60")
        self.assertEqual(base, [])
        self.assertEqual(base_rejections[0]["reason"], "no_features_available_asof_decision")

    def test_missing_availability_is_rejected_not_assumed(self):
        rows, rejected = reconstruct_vintages(
            [feature(available_at="", retrieved_at="")], [DECISION],
        )
        self.assertEqual(rows, [])
        self.assertEqual(rejected[0]["kind"], "feature")
        self.assertIn("missing availability", rejected[0]["reason"])
        self.assertEqual(rejected[1]["reason"], "no_features_available_asof_decision")

    def test_observed_retrieval_is_a_conservative_availability_bound(self):
        row = feature(available_at="", retrieved_at="2026-09-13T11:59:00Z")
        available, method, delay = effective_availability(row, "base")
        self.assertEqual(available.isoformat(), "2026-09-13T11:59:00+00:00")
        self.assertEqual((method, delay), ("observed_receipt", None))

    def test_impossible_issue_before_availability_order_is_rejected(self):
        row = feature(issue_time="2026-09-13T11:51:00Z")
        rows, rejected = reconstruct_vintages([row], [DECISION])
        self.assertEqual(rows, [])
        self.assertEqual(rejected[0]["reason"], "issue_time is after available_at")

    def test_decision_keys_do_not_cross_contracts(self):
        other = dict(DECISION, contract="KXLOWTPHX-26SEP13-T80")
        rows, rejected = reconstruct_vintages([feature()], [other])
        self.assertEqual(rows, [])
        self.assertEqual(rejected[0]["reason"], "no_features_available_asof_decision")


if __name__ == "__main__":
    unittest.main()

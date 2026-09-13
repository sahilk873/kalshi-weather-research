import unittest

from build_provenance_indexes import build


class ProvenanceIndexTests(unittest.TestCase):
    def test_valid_rows_are_indexed_without_synthesis(self):
        sources, observations, rejected = build(
            [{"initialization_time_utc": "2026-09-13T00:00:00Z", "source_receipt_time": "2026-09-13T01:00:00Z", "raw_path": "raw/a", "sha256": "a" * 64}],
            [{"station": "KNYC", "valid_utc": "2026-09-13T00:53:00Z", "available_ts": "2026-09-13T01:00:00Z", "raw_path": "raw/b", "raw_sha256": "b" * 64}],
        )
        self.assertEqual(len(sources), 1); self.assertEqual(len(observations), 1); self.assertFalse(rejected)
        self.assertEqual(observations[0]["observation_id"], "KNYC:2026-09-13T00:53:00Z:" + "b" * 64)

    def test_missing_availability_or_hash_is_rejected(self):
        sources, observations, rejected = build(
            [{"initialization_time_utc": "2026-09-13T00:00:00Z", "source_receipt_time": "", "raw_path": "raw/a", "sha256": ""}],
            [{"station": "KNYC", "valid_utc": "2026-09-13T00:53:00Z", "raw_path": "raw/b", "raw_sha256": ""}],
        )
        self.assertEqual((sources, observations), ([], [])); self.assertEqual(len(rejected), 2)

    def test_duplicate_payload_keeps_earliest_receipt(self):
        row = {"station": "KNYC", "valid_utc": "2026-09-13T13:00:00Z", "available_ts": "2026-09-13T14:00:00Z", "raw_path": "raw/a", "raw_sha256": "a" * 64}
        later = dict(row, available_ts="2026-09-13T15:00:00Z", raw_path="raw/a-copy")
        _, observations, rejected = build([], [later, row])
        self.assertFalse(rejected)
        self.assertEqual(observations[0]["available_ts"], "2026-09-13T14:00:00Z")
        self.assertEqual(observations[0]["raw_path"], "raw/a")

    def test_station_allow_list_rejects_nearby_substitutes(self):
        row = {"station": "KLGA", "valid_utc": "2026-09-13T13:00:00Z", "available_ts": "2026-09-13T14:00:00Z", "raw_path": "raw/a", "raw_sha256": "a" * 64}
        _, observations, rejected = build([], [row], stations={"KNYC"})
        self.assertEqual(observations, [])
        self.assertEqual(rejected[0]["reason"], "non_target_station")


if __name__ == "__main__":
    unittest.main()

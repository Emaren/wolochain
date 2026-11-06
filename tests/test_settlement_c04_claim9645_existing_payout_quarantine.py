"""C04 claim9645 source-evidence quarantine: no duplicate 100-WOLO attribution."""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import pathlib
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SOURCE = ROOT / "scripts" / "settlement_c04_claim9645_existing_payout_quarantine.py"
spec = importlib.util.spec_from_file_location("c04_claim9645", SOURCE)
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)


def fixture():
    candidates = []
    for n in range(14):
        candidates.append({
            "amount_uwolo": 100000000,
            "hash": f"{n+1:064X}",
            "height": 2609000 + n,
            "original_market_memo": False,
            "other_claim_refs": 1,
            "timestamp": "2026-10-24 01:12:35",
            "wager_payout_refs": 1,
        })
    return {
        "schema": tool.INPUT_SCHEMA,
        "captured_utc": "2026-11-05T16:15:05.436071+00:00",
        "claim_created_after_attempt": True,
        "claim_id": 9645,
        "claim_payout_hash_absent": True,
        "claim_pending": True,
        "claim_retry_authorized": False,
        "financial_mutation": False,
        "independent_consensus_and_complete_coverage_proven": False,
        "indexed_candidate_count": 14,
        "indexed_candidates": candidates,
        "local_index_max_height": 2813553,
        "local_index_rows": 4300,
        "market_id": 946520,
        "market_voided": True,
        "refund_9645_paid_or_unpaid_proven": False,
        "refund_failed": True,
        "trust_limit": "single operator local indexing, no independent historical payment finality",
        "wager_amount_wolo": 100,
        "wager_count": 1,
    }


class Claim9645Tests(unittest.TestCase):
    def setUp(self):
        self.doc = fixture()

    def fail_code(self, reason):
        with self.assertRaisesRegex(tool.HoldError, "^" + reason + "$"):
            tool.classify(self.doc)

    def test_pass_is_still_noncrediting_nonretry_hold(self):
        report = tool.classify(self.doc)
        self.assertEqual(report["status"], "HOLD")
        self.assertEqual(report["claim_id"], 9645)
        self.assertEqual(report["indexed_other_100wolo_candidates"], 14)
        self.assertEqual(report["claimed_refund_payment_fate"], "UNKNOWN")
        self.assertTrue(report["every_indexed_candidate_already_referenced"])
        self.assertEqual(report["source_sha256"], tool.SOURCE_SHA256)
        self.assertFalse(report["refund_paid_proved"])
        self.assertFalse(report["refund_unpaid_proved"])
        self.assertFalse(report["retry_authorized"])
        self.assertFalse(report["financial_release_authorized"])
        self.assertFalse(report["production_mutated"])
        out = json.dumps(report)
        self.assertNotIn(self.doc["indexed_candidates"][0]["hash"], out)

    def test_claim_or_market_identity_change_refused(self):
        self.doc["claim_id"] = 889
        self.fail_code("CLAIM_OR_MARKET_IDENTITY_DRIFT")
        self.doc = fixture()
        self.doc["market_id"] = 261848
        self.fail_code("CLAIM_OR_MARKET_IDENTITY_DRIFT")

    def test_bool_cannot_coerce_to_identifiers_or_money(self):
        for key in ("claim_id", "market_id", "wager_amount_wolo", "wager_count"):
            self.doc = fixture()
            self.doc[key] = True
            self.fail_code("CLAIM_OR_MARKET_IDENTITY_DRIFT")

    def test_no_fake_independent_chain_trust(self):
        self.doc["independent_consensus_and_complete_coverage_proven"] = True
        self.fail_code("HISTORICAL_FINALITY_OR_RETRY_FABRICATED")

    def test_no_fake_refund_paid_unpaid_certification(self):
        self.doc["refund_9645_paid_or_unpaid_proven"] = True
        self.fail_code("HISTORICAL_FINALITY_OR_RETRY_FABRICATED")

    def test_no_retry_finance_mutation_or_laundered_claim_status(self):
        for key in ("claim_retry_authorized", "financial_mutation"):
            self.doc = fixture()
            self.doc[key] = True
            self.fail_code("HISTORICAL_FINALITY_OR_RETRY_FABRICATED")
        self.doc = fixture()
        self.doc["claim_pending"] = False
        self.fail_code("HISTORICAL_FINALITY_OR_RETRY_FABRICATED")

    def test_change_index_census_or_claim_count_denied(self):
        self.doc["indexed_candidate_count"] = 13
        self.fail_code("LOCAL_INDEX_COVERAGE_DRIFT")
        self.doc = fixture()
        self.doc["local_index_rows"] = 4299
        self.fail_code("LOCAL_INDEX_COVERAGE_DRIFT")
        self.doc = fixture()
        self.doc["indexed_candidates"].pop()
        self.fail_code("LOCAL_INDEX_COVERAGE_DRIFT")

    def test_candidates_cannot_be_duplicate_transactions(self):
        self.doc["indexed_candidates"][1]["hash"] = self.doc["indexed_candidates"][0]["hash"]
        self.fail_code("CANDIDATE_TX_IDENTITY_DUPLICATE_OR_INVALID")
        self.doc = fixture()
        self.doc["indexed_candidates"][0]["hash"] = "0" * 64
        self.fail_code("CANDIDATE_TX_IDENTITY_DUPLICATE_OR_INVALID")

    def test_candidates_cannot_share_height(self):
        self.doc["indexed_candidates"][1]["height"] = self.doc["indexed_candidates"][0]["height"]
        self.fail_code("CANDIDATE_HEIGHT_DUPLICATE_OR_INVALID")
        self.doc = fixture()
        self.doc["indexed_candidates"][0]["height"] = False
        self.fail_code("CANDIDATE_HEIGHT_DUPLICATE_OR_INVALID")

    def test_candidate_bogus_100wolo_amount_or_boolean_amount_denied(self):
        self.doc["indexed_candidates"][0]["amount_uwolo"] = 99999999
        self.fail_code("CANDIDATE_AMOUNT_DRIFT")
        self.doc = fixture()
        self.doc["indexed_candidates"][0]["amount_uwolo"] = True
        self.fail_code("CANDIDATE_AMOUNT_DRIFT")

    def test_candidate_without_other_claim_attribution_denied(self):
        self.doc["indexed_candidates"][0]["other_claim_refs"] = 0
        self.fail_code("CANDIDATE_ALREADY_ATTRIBUTED_OR_MEMO_DRIFT")
        self.doc = fixture()
        self.doc["indexed_candidates"][0]["wager_payout_refs"] = False
        self.fail_code("CANDIDATE_ALREADY_ATTRIBUTED_OR_MEMO_DRIFT")

    def test_memo_bool_does_not_masquerade_as_original(self):
        self.doc["indexed_candidates"][0]["original_market_memo"] = "market:946520"
        self.fail_code("CANDIDATE_ALREADY_ATTRIBUTED_OR_MEMO_DRIFT")

    def test_no_extra_payout_credit_fields_in_packet(self):
        self.doc["indexed_candidates"][0]["claim_9645_paid"] = True
        self.fail_code("CANDIDATE_SHAPE_DRIFT")
        self.doc = fixture()
        self.doc["verified"] = True
        self.fail_code("ATTRIBUTION_SOURCE_OR_SCHEMA_DRIFT")

    def test_timestamps_and_height_bounded(self):
        self.doc["indexed_candidates"][0]["timestamp"] = "TODAY"
        self.fail_code("CANDIDATE_TIMESTAMP_DRIFT")
        self.doc = fixture()
        self.doc["indexed_candidates"][0]["height"] = 2813554
        self.fail_code("CANDIDATE_HEIGHT_DUPLICATE_OR_INVALID")

    def test_private_source_digest_cannot_be_replaced_by_caller(self):
        doc = fixture()
        with tempfile.TemporaryDirectory(prefix="c04claim-") as directory:
            p = pathlib.Path(directory) / "attribution.json"
            p.write_bytes(json.dumps(doc).encode())
            p.chmod(0o600)
            with self.assertRaisesRegex(tool.HoldError, "^PRIVATE_INPUT_SHA256_DRIFT$"):
                tool.read_exact_private(p)

    def test_world_readable_and_symlink_file_refused(self):
        with tempfile.TemporaryDirectory(prefix="c04claim-") as directory:
            p = pathlib.Path(directory) / "attribution.json"
            p.write_text(json.dumps(fixture()))
            p.chmod(0o644)
            with self.assertRaisesRegex(tool.HoldError, "^PRIVATE_INPUT_OWNER_OR_MODE_DRIFT$"):
                tool.read_exact_private(p)
            p.chmod(0o600)
            q = pathlib.Path(directory) / "fake.json"
            q.symlink_to(p)
            with self.assertRaisesRegex(tool.HoldError, "^PRIVATE_INPUT_UNAVAILABLE$"):
                tool.read_exact_private(q)

    def test_noncanonical_json_duplicates_denied(self):
        with self.assertRaisesRegex(tool.HoldError, "^DUPLICATE_JSON_KEY$"):
            tool.unique_pairs([("claim_id", 9645), ("claim_id", 889)])
        with self.assertRaisesRegex(tool.HoldError, "^NONFINITE_JSON_NUMBER$"):
            tool.reject_constant("NaN")

    def test_missing_path_does_not_leak_files(self):
        code = tool.main(["--evidence", "/no-such-private-c04-packet"])
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()

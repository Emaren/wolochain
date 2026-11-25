"""Founder claim #889 local-index observations never authorize a financial retry."""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
FILE = ROOT / "scripts" / "settlement_c04_founder889_local_index_hold.py"
spec = importlib.util.spec_from_file_location("c04founder889", FILE)
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)


def fixture():
    return {
        "c04_closed": False,
        "chain_id": "wolo-1",
        "chain_index_historical_completeness_proven": False,
        "enumerated_other_candidates": [
            {
                "amount_300wolo_matches_original": True,
                "block_date": "2026-06-13", "class": "sender_amount",
                "height": 324458, "recipient_matches_original": False,
                "tx_hash_fingerprint": "1" * 64,
            },
            {
                "amount_300wolo_matches_original": False,
                "block_date": "2026-06-13", "class": "sender_recipient",
                "height": 334337, "recipient_matches_original": True,
                "tx_hash_fingerprint": "2" * 64,
            },
            {
                "amount_300wolo_matches_original": False,
                "block_date": "2026-06-14", "class": "sender_recipient",
                "height": 355431, "recipient_matches_original": True,
                "tx_hash_fingerprint": "3" * 64,
            },
        ],
        "financial_release_authorized": False,
        "founder889_payment_fate": "UNKNOWN",
        "funds_moved": False,
        "independent_chain_trust_root_verified": False,
        "known_positive_100wolo_control_found": True,
        "no_unindexed_payment_proven": False,
        "node_height": 2825757,
        "original_recipient_indexed_any_amount": 7,
        "original_recipient_indexed_exact_300wolo": 0,
        "original_recipient_sha256": "a" * 64,
        "original_request_id_sha256": "b" * 64,
        "original_request_sha256": "c" * 64,
        "original_sender_indexed_exact_300wolo": 1,
        "original_sender_to_original_recipient_any_amount": 2,
        "original_signer_sha256": "d" * 64,
        "production_mutated": False,
        "recipient_index_count_fully_enumerated": True,
        "retry_authorized": False,
        "schema": tool.EVIDENCE_SCHEMA,
        "source": "single_operator_local_txindex_nonindependent",
        "status": "HOLD",
    }


class Founder889Tests(unittest.TestCase):
    def setUp(self):
        self.doc = fixture()

    def refused(self, why):
        with self.assertRaisesRegex(tool.HoldError, "^" + why + "$"):
            tool.classify(self.doc)

    def test_valid_local_index_always_noncrediting_hold(self):
        d = tool.classify(self.doc)
        self.assertEqual(d["status"], "HOLD")
        self.assertEqual(d["payment_fate"], "UNKNOWN")
        self.assertEqual(d["local_sender_same_amount_other_recipient_count"], 1)
        self.assertEqual(d["local_sender_recipient_other_amount_count"], 2)
        self.assertEqual(d["local_exact_sender_recipient_300wolo_count"], 0)
        for k in ("historical_global_payment_absence_proved",
                  "independent_canonical_finality_proved", "unpaid_proved",
                  "paid_proved", "retry_authorized",
                  "financial_release_authorized", "production_mutated"):
            self.assertFalse(d[k])
        raw = json.dumps(d)
        self.assertNotIn(self.doc["original_recipient_sha256"], raw)
        self.assertNotIn(self.doc["enumerated_other_candidates"][0]["tx_hash_fingerprint"], raw)

    def test_local_recipient_count_not_global_completeness(self):
        self.doc["no_unindexed_payment_proven"] = True
        self.refused("FOUNDER_UNKNOWN_OR_INDEPENDENT_TRUST_FABRICATED")

    def test_nonindependent_chain_cannot_claim_finality(self):
        self.doc["independent_chain_trust_root_verified"] = True
        self.refused("FOUNDER_UNKNOWN_OR_INDEPENDENT_TRUST_FABRICATED")

    def test_no_c04_closure_or_funds_move(self):
        for key in ("c04_closed", "financial_release_authorized",
                    "retry_authorized", "funds_moved", "production_mutated"):
            self.doc = fixture()
            self.doc[key] = True
            self.refused("FOUNDER_UNKNOWN_OR_INDEPENDENT_TRUST_FABRICATED")

    def test_paid_unpaid_labels_not_valid(self):
        for fate in ("PAID", "UNPAID", "REFUND_DUE", "NOT_PAID"):
            self.doc = fixture()
            self.doc["founder889_payment_fate"] = fate
            self.refused("FOUNDER_UNKNOWN_OR_INDEPENDENT_TRUST_FABRICATED")

    def test_exact_300wolo_to_original_recipient_cannot_be_forged(self):
        self.doc["original_recipient_indexed_exact_300wolo"] = 1
        self.refused("FOUNDER_LOCAL_INDEX_METRICS_DRIFT")

    def test_false_not_int_count_or_height(self):
        self.doc["node_height"] = True
        self.refused("FOUNDER_LOCAL_INDEX_METRICS_DRIFT")
        self.doc = fixture()
        self.doc["original_sender_indexed_exact_300wolo"] = False
        self.refused("FOUNDER_LOCAL_INDEX_METRICS_DRIFT")

    def test_source_schema_chain_and_operator_identity_fixed(self):
        self.doc["chain_id"] = "other-chain"
        self.refused("FOUNDER_SOURCE_OR_SCHEMA_DRIFT")
        self.doc = fixture()
        self.doc["source"] = "independent_peer"
        self.refused("FOUNDER_SOURCE_OR_SCHEMA_DRIFT")

    def test_original_request_binding_required(self):
        self.doc["original_request_sha256"] = ""
        self.refused("FOUNDER_ORIGINAL_REQUEST_PINS_MISSING")
        self.doc = fixture()
        self.doc["original_signer_sha256"] = "0" * 64
        self.refused("FOUNDER_ORIGINAL_REQUEST_PINS_MISSING")

    def test_candidate_count_must_not_shrink_or_expand(self):
        self.doc["enumerated_other_candidates"].pop()
        self.refused("FOUNDER_LOCAL_CANDIDATE_COVERAGE_DRIFT")
        self.doc = fixture()
        self.doc["enumerated_other_candidates"].append(copy.deepcopy(
            self.doc["enumerated_other_candidates"][0]))
        self.refused("FOUNDER_LOCAL_CANDIDATE_COVERAGE_DRIFT")

    def test_sender_amount_must_not_masquerade_as_recipient(self):
        self.doc["enumerated_other_candidates"][0]["recipient_matches_original"] = True
        self.refused("FOUNDER_UNJUSTIFIED_MATCHED_PAYMENT")

    def test_sender_recipient_amount_must_not_masquerade_as_300wolo(self):
        self.doc["enumerated_other_candidates"][1]["amount_300wolo_matches_original"] = True
        self.refused("FOUNDER_UNJUSTIFIED_MATCHED_PAYMENT")

    def test_candidate_class_and_boolean_constraints(self):
        self.doc["enumerated_other_candidates"][0]["class"] = "original_payment"
        self.refused("FOUNDER_CANDIDATE_CLASS_DRIFT")
        self.doc = fixture()
        self.doc["enumerated_other_candidates"][0]["recipient_matches_original"] = 0
        self.refused("FOUNDER_UNJUSTIFIED_MATCHED_PAYMENT")

    def test_candidate_tx_identity_duplicate_refused(self):
        self.doc["enumerated_other_candidates"][1]["tx_hash_fingerprint"] = "1" * 64
        self.refused("FOUNDER_CANDIDATE_TX_IDENTITY_DRIFT")

    def test_candidate_duplicate_or_invalid_height_refused(self):
        self.doc["enumerated_other_candidates"][0]["height"] = 334337
        self.refused("FOUNDER_CANDIDATE_HEIGHT_DRIFT")
        self.doc = fixture()
        self.doc["enumerated_other_candidates"][0]["height"] = False
        self.refused("FOUNDER_CANDIDATE_HEIGHT_DRIFT")

    def test_private_raw_sha_must_match_fixed_evidence(self):
        with tempfile.TemporaryDirectory() as path:
            p = Path(path) / "founder-index.json"
            p.write_bytes(json.dumps(self.doc).encode())
            p.chmod(0o600)
            with self.assertRaisesRegex(tool.HoldError, "^PRIVATE_EVIDENCE_PIN_MISMATCH$"):
                tool.read_original_private(p)

    def test_symlink_world_mode_and_duplicate_json_rejected(self):
        with tempfile.TemporaryDirectory() as path:
            p = Path(path) / "founder-index.json"
            p.write_text("{}")
            p.chmod(0o644)
            with self.assertRaisesRegex(tool.HoldError, "^PRIVATE_EVIDENCE_MODE_OR_OWNER$"):
                tool.read_original_private(p)
            p.chmod(0o600)
            link = Path(path) / "fake.json"
            link.symlink_to(p)
            with self.assertRaisesRegex(tool.HoldError, "^PRIVATE_EVIDENCE_UNAVAILABLE$"):
                tool.read_original_private(link)
        with self.assertRaisesRegex(tool.HoldError, "^DUPLICATE_JSON_KEY$"):
            tool.unique([("founder889_payment_fate", "UNKNOWN"),
                         ("founder889_payment_fate", "PAID")])

    def test_missing_original_packet_stop(self):
        self.assertEqual(tool.main(["--evidence", "/no-such-founder-packet"]), 2)


if __name__ == "__main__":
    unittest.main()

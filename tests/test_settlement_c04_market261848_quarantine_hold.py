"""Adversarial market #261848 local historical proof: no finality, no payout credit."""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "scripts" / "settlement_c04_market261848_quarantine_hold.py"
spec = importlib.util.spec_from_file_location("market261848_hold", SOURCE)
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)


def fixture():
    def wager(wager_id, amount, height, sha):
        return {
            "id": wager_id, "amount_wolo": amount,
            "stake_hash": sha, "payout_hash_absent": True,
            "local_comet": {
                "execution_code": 0, "height": str(height), "inclusion_proof_present": True,
                "rpc_hash": sha, "stake_hash": sha,
            },
        }
    return {
        "schema": tool.EVIDENCE_SCHEMA,
        "source": "same-operator historical Comet local indexed transaction",
        "observed_utc": "2026-11-06T18:00:00Z",
        "market_id": 261848,
        "wagers": [wager(394, 5000, 719485, "A" * 64),
                   wager(396, 800, 719690, "B" * 64)],
        "amount_total_wolo": 5800,
        "local_stake_execution_proved": True,
        "independent_checkpoint_proved": False,
        "independent_recipient_amount_refund_disposition_proved": False,
        "refund_due_proved": False,
        "retry_authorized": False,
        "financial_release_authorized": False,
        "production_mutated": False,
    }


class Market261848HeldTests(unittest.TestCase):
    def setUp(self):
        self.data = fixture()

    def denied(self, code):
        with self.assertRaisesRegex(tool.HoldError, "^" + code + "$"):
            tool.classify(self.data, "a" * 64)

    def test_original_stakes_must_remain_noncrediting_hold(self):
        report = tool.classify(self.data, "a" * 64)
        self.assertEqual(report["status"], "HOLD")
        self.assertEqual(report["original_stake_local_observation_wolo"], 5800)
        self.assertEqual([x["wager_id"] for x in report["wagers"]], [394, 396])
        for key in ("independent_canonical_finality_proved",
                    "payout_or_refund_unpaid_proved", "refund_due_proved",
                    "retry_authorized", "financial_release_authorized",
                    "production_mutated"):
            self.assertIs(report[key], False)
        self.assertNotIn("stake_hash", json.dumps(report))

    def test_cannot_upgrade_local_index_to_independent_trust(self):
        self.data["independent_checkpoint_proved"] = True
        self.denied("UNSUPPORTED_PAYMENT_FINALITY_OR_AUTHORITY")

    def test_cannot_forge_refund_due_or_payout_state(self):
        self.data["refund_due_proved"] = True
        self.denied("UNSUPPORTED_PAYMENT_FINALITY_OR_AUTHORITY")

    def test_cannot_forge_disposition(self):
        self.data["independent_recipient_amount_refund_disposition_proved"] = True
        self.denied("UNSUPPORTED_PAYMENT_FINALITY_OR_AUTHORITY")

    def test_cannot_authorize_retry_or_release(self):
        for key in ("retry_authorized", "financial_release_authorized"):
            self.data = fixture()
            self.data[key] = True
            self.denied("UNSUPPORTED_PAYMENT_FINALITY_OR_AUTHORITY")

    def test_false_cannot_masquerade_as_comet_code_zero(self):
        self.data["wagers"][0]["local_comet"]["execution_code"] = False
        self.denied("LOCAL_COMET_EXECUTION_OR_HEIGHT_DRIFT")

    def test_boolean_wager_ids_or_amounts_rejected(self):
        self.data["wagers"][0]["id"] = True
        self.denied("WAGER_IDENTITY_DRIFT")
        self.data = fixture()
        self.data["wagers"][0]["amount_wolo"] = True
        self.denied("WAGER_AMOUNT_OR_PAYOUT_STATE_DRIFT")

    def test_local_execution_or_inclusion_missing_denies(self):
        self.data["wagers"][1]["local_comet"]["inclusion_proof_present"] = False
        self.denied("LOCAL_COMET_EXECUTION_OR_HEIGHT_DRIFT")

    def test_hashes_must_match_exact_tx_identity(self):
        self.data["wagers"][1]["local_comet"]["rpc_hash"] = "C" * 64
        self.denied("ORIGINAL_STAKE_IDENTITY_DRIFT")
        self.data = fixture()
        self.data["wagers"][1]["stake_hash"] = "a" * 64
        self.denied("ORIGINAL_STAKE_IDENTITY_DRIFT")

    def test_duplicate_original_stake_hash_cannot_double_count(self):
        self.data["wagers"][1]["stake_hash"] = "A" * 64
        self.data["wagers"][1]["local_comet"]["rpc_hash"] = "A" * 64
        self.data["wagers"][1]["local_comet"]["stake_hash"] = "A" * 64
        self.denied("ORIGINAL_STAKE_IDENTITY_DRIFT")

    def test_duplicate_or_extra_wagers_denied(self):
        self.data["wagers"][1]["id"] = 394
        self.denied("WAGER_REUSED")
        self.data = fixture()
        self.data["wagers"].append(copy.deepcopy(self.data["wagers"][0]))
        self.denied("MARKET_WAGER_COVERAGE_DRIFT")

    def test_amount_and_height_not_loosely_coerced(self):
        self.data["amount_total_wolo"] = "5800"
        self.denied("MARKET_ID_OR_AMOUNT_DRIFT")
        self.data = fixture()
        self.data["wagers"][1]["local_comet"]["height"] = 719690
        self.denied("LOCAL_COMET_EXECUTION_OR_HEIGHT_DRIFT")

    def test_no_unexpected_approval_fields(self):
        self.data["funded"] = True
        self.denied("MARKET_EVIDENCE_SHAPE_DRIFT")

    def test_payout_hash_absence_must_not_appear_confirmed(self):
        self.data["wagers"][0]["payout_hash_absent"] = False
        self.denied("WAGER_AMOUNT_OR_PAYOUT_STATE_DRIFT")

    def test_restricted_private_original_file_and_hash(self):
        raw = json.dumps(self.data).encode()
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory) / "observed.json"
            p.write_bytes(raw)
            p.chmod(0o600)
            got, sha = tool.read_exact_private(p, hashlib.sha256(raw).hexdigest())
            self.assertEqual(got["market_id"], 261848)
            self.assertEqual(sha, hashlib.sha256(raw).hexdigest())
            self.assertEqual(tool.main([
                "--evidence", str(p), "--sha256", sha
            ]), 3)

    def test_refuses_bad_hash_and_unsafe_file_mode(self):
        raw = json.dumps(self.data).encode()
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory) / "observed.json"
            p.write_bytes(raw)
            p.chmod(0o600)
            with self.assertRaisesRegex(tool.HoldError, "^EVIDENCE_DIGEST_DRIFT$"):
                tool.read_exact_private(p, "b" * 64)
            p.chmod(0o644)
            with self.assertRaisesRegex(tool.HoldError, "^EVIDENCE_OWNER_OR_MODE_DRIFT$"):
                tool.read_exact_private(p, hashlib.sha256(raw).hexdigest())

    def test_refuses_symlink_without_following(self):
        raw = json.dumps(self.data).encode()
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory) / "real.json"
            p.write_bytes(raw)
            p.chmod(0o600)
            q = Path(directory) / "symlink.json"
            q.symlink_to(p)
            with self.assertRaisesRegex(tool.HoldError, "^EVIDENCE_UNAVAILABLE$"):
                tool.read_exact_private(q, hashlib.sha256(raw).hexdigest())

    def test_duplicate_json_key_refused_even_with_matching_sha(self):
        raw = json.dumps(self.data).replace('"market_id": 261848',
                                            '"market_id": 261848, "market_id": 261848').encode()
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory) / "double.json"
            p.write_bytes(raw)
            p.chmod(0o600)
            with self.assertRaisesRegex(tool.HoldError, "^DUPLICATE_JSON_KEY$"):
                tool.read_exact_private(p, hashlib.sha256(raw).hexdigest())

    def test_nonfinite_and_corrupt_json_refused(self):
        for raw in (b'{"x":NaN}', b'{"bad":'):
            with tempfile.TemporaryDirectory() as directory:
                p = Path(directory) / "bad.json"
                p.write_bytes(raw)
                p.chmod(0o600)
                with self.assertRaises(tool.HoldError):
                    tool.read_exact_private(p, hashlib.sha256(raw).hexdigest())


if __name__ == "__main__":
    unittest.main()

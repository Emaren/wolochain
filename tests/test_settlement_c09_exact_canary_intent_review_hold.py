"""C08/C09 real ephemeral Ed25519 signed exact-canary review. Never funded."""
from __future__ import annotations

import base64
import copy
from datetime import datetime, timedelta, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "settlement_c09_exact_canary_intent_review_hold.py"
spec = importlib.util.spec_from_file_location("c09_exact_review", SCRIPT)
import sys
sys.path.insert(0, str(ROOT / "scripts"))
reviewer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reviewer)
owner = reviewer.owner
NOW = datetime(2026, 11, 6, 19, 0, 0, tzinfo=timezone.utc)
ISO = lambda t: t.strftime("%Y-%m-%dT%H:%M:%SZ")


def req():
    sha = lambda x: x * 64
    return {
        "schema": reviewer.SCHEMA,
        "chain_id": "wolo-1",
        "operation": "one-new-claim-canary-only",
        "fresh_claim_id": "fresh-c09-" + "a" * 32,
        "native_claim_id": "900000000001",
        "request_id": "c09-" + "b" * 32,
        "recipient": "wolo1" + "q" * 39,
        "amount_uwolo": "700000",
        "fee_uwolo": "1000",
        "bank_height": 2845220,
        "source_commit": "e" * 40,
        "satchel_binary_sha256": sha("1"),
        "reviewer_binary_sha256": sha("2"),
        "consensus_header_root_sha256": sha("3"),
        "bank_root_sha256": sha("4"),
        "liability_root_sha256": sha("5"),
        "full_writer_fence_sha256": sha("6"),
        "coordinated_backup_sha256": sha("7"),
        "isolated_restore_sha256": sha("8"),
        "c01_c08_acceptance_bundle_sha256": sha("9"),
        "governance_ratification_sha256": sha("a"),
        "rollback_receipt_sha256": sha("b"),
        "nonce": "c" * 32,
        "not_before": ISO(NOW - timedelta(seconds=10)),
        "expires_at": ISO(NOW + timedelta(seconds=100)),
        "legacy_fallback_allowed": False,
        "retry_on_unknown_allowed": False,
        "independent_human_review_claimed": False,
        "one_operation_only": True,
    }


class ExactCanaryReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="wolo-c09-test-")
        cls.folder = Path(cls.temp.name)
        cls.private = cls.folder / "synthetic-ephemeral-private.pem"
        cls.public = cls.folder / "synthetic-ephemeral-public.pem"
        subprocess.run(["openssl", "genpkey", "-algorithm", "Ed25519",
                        "-out", str(cls.private)], check=True, capture_output=True)
        subprocess.run(["openssl", "pkey", "-in", str(cls.private),
                        "-pubout", "-out", str(cls.public)], check=True, capture_output=True)
        cls.pub_pem = cls.public.read_text()
        der = subprocess.run(["openssl", "pkey", "-pubin", "-inform", "PEM",
                              "-outform", "DER"], input=cls.pub_pem.encode(),
                             check=True, capture_output=True).stdout
        cls.der_sha = hashlib.sha256(der).hexdigest()

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def setUp(self):
        self.enroll = {
            "schema": owner.ENROLL_SCHEMA,
            "owner_key_id": "synthetic-single-operator",
            "public_key_pem": self.pub_pem,
            "valid_from": ISO(NOW - timedelta(days=1)),
            "valid_until": ISO(NOW + timedelta(days=1)),
            "revoked": False,
        }
        self.req = req()

    def signed(self):
        body = reviewer.DOMAIN + owner.canonical({
            "owner_key_id": self.enroll["owner_key_id"], "request": self.req
        })
        with tempfile.TemporaryDirectory(prefix="c09-sig-") as d:
            p = Path(d) / "signed_message"
            p.write_bytes(body)
            sig = subprocess.run(["openssl", "pkeyutl", "-sign", "-rawin",
                                  "-inkey", str(self.private), "-in", str(p)],
                                 check=True, capture_output=True).stdout
        return {
            "schema": reviewer.PACKET_SCHEMA, "owner_key_id": self.enroll["owner_key_id"],
            "request": copy.deepcopy(self.req),
            "signature_b64": base64.b64encode(sig).decode(),
        }

    def reviewed(self, packet=None, enrollment=None, source=None, now=NOW):
        raw = owner.canonical(self.enroll if enrollment is None else enrollment)
        p = self.signed() if packet is None else packet
        return reviewer.review(
            raw, owner.canonical(p),
            pinned_enrollment_sha256=hashlib.sha256(raw).hexdigest(),
            pinned_owner_der_sha256=self.der_sha,
            pinned_source_commit=self.req["source_commit"] if source is None else source,
            now=now,
        )

    def refused(self, code, **kwargs):
        with self.assertRaisesRegex(owner.AuthorityHold, "^" + code + "$"):
            self.reviewed(**kwargs)

    def test_real_ed25519_exact_canary_signature_is_always_hold(self):
        result = self.reviewed()
        self.assertEqual(result["status"], "CRYPTO_VALID_NONAUTHORIZING_HOLD")
        self.assertTrue(result["exact_transaction_fields_were_signed"])
        self.assertTrue(result["real_single_human_owner_signature_verified"])
        for key in ("economic_canary_limit_ratified", "recipient_chain_checksum_verified",
                    "independent_chain_checkpoint_verified",
                    "bank_and_liability_roots_independently_verified",
                    "physical_c01_c08_gates_accepted", "offhost_one_use_nonce_consumed",
                    "new_governance_policy_ratified_and_notice_elapsed",
                    "independent_human_review_available", "funded_canary_permit_issued",
                    "financial_release_authorized", "retry_authorized", "production_mutated"):
            self.assertIs(result[key], False)
        s = json.dumps(result)
        self.assertNotIn(self.req["recipient"], s)
        self.assertNotIn(self.req["nonce"], s)
        self.assertNotIn(self.enroll["public_key_pem"], s)
        self.assertNotIn(self.req["amount_uwolo"], s)

    def test_exact_recipient_amount_fee_and_bank_root_tamper_fails_signature(self):
        for key, altered in (
            ("recipient", "wolo1" + "p" * 39),
            ("amount_uwolo", "900000"),
            ("fee_uwolo", "2000"),
            ("bank_root_sha256", "f" * 64),
            ("bank_height", 2845221),
            ("source_commit", "d" * 40),
            ("request_id", "c09-" + "e" * 32),
            ("native_claim_id", "900000000002"),
        ):
            packet = self.signed()
            packet["request"][key] = altered
            self.refused("INVALID_PUBLIC_KEY_OR_SIGNATURE", packet=packet)

    def test_wrong_domain_signature_cannot_convert_old_generic_owner_intent(self):
        packet = self.signed()
        packet["schema"] = owner.PACKET_SCHEMA
        self.refused("OWNER_PACKET_SCHEMA_OR_KEY_MISMATCH", packet=packet)

    def test_old_v2_c09_domain_and_packet_schema_cannot_be_accepted(self):
        p = self.signed()
        p["schema"] = "wolo.c09.solo-owner-signed-exact-canary-intent.v2"
        self.refused("OWNER_PACKET_SCHEMA_OR_KEY_MISMATCH", packet=p)
        p = self.signed()
        p["request"]["schema"] = "wolo.c09.solo-owner-exact-canary-intent.v2"
        self.refused("C09_SIGNED_FIELDS_OR_OPERATION_INVALID", packet=p)

    def test_signed_native_app_id_exact_forward_only_namespace(self):
        original = req()
        for good in ("900000000001", "900000000002", "999999999999"):
            q = dict(original)
            q["native_claim_id"] = good
            reviewer.validate_request(q, NOW)
        for bad in ("889", "9645", "101", "0", "900000000000",
                    "99999999999", "1000000000000", "0900000000001",
                    "900000000001 ", "-900000000001", "90000000000a"):
            q = dict(original)
            q["native_claim_id"] = bad
            with self.subTest(native_claim_id=bad), self.assertRaises(owner.AuthorityHold) as caught:
                reviewer.validate_request(q, NOW)
            self.assertEqual(str(caught.exception),
                             "C09_NATIVE_CLAIM_NOT_FORWARD_ONLY_APP_ID")
        q = dict(original)
        q.pop("native_claim_id")
        with self.assertRaises(owner.AuthorityHold) as caught:
            reviewer.validate_request(q, NOW)
        self.assertEqual(str(caught.exception),
                         "C09_SIGNED_FIELDS_OR_OPERATION_INVALID")

    def test_legacy_claim_or_forged_historical_liability_disallowed(self):
        self.req["fresh_claim_id"] = "889"
        self.refused("C09_FRESH_CANARY_IDENTITY_INVALID")
        self.req = req()
        self.req["historic_claim_id"] = "9645"
        self.refused("C09_SIGNED_FIELDS_OR_OPERATION_INVALID")

    def test_one_claim_only_and_separate_request_identity(self):
        self.req["fresh_claim_id"] = "fresh-c09-" + "b" * 32
        self.refused("C09_FRESH_CANARY_IDENTITY_INVALID")
        self.req = req()
        self.req["one_operation_only"] = False
        self.refused("C09_UNSAFE_PERMISSION_SEMANTICS")

    def test_no_legacy_fallback_or_unknown_retry(self):
        self.req["legacy_fallback_allowed"] = True
        self.refused("C09_UNSAFE_PERMISSION_SEMANTICS")
        self.req = req()
        self.req["retry_on_unknown_allowed"] = True
        self.refused("C09_UNSAFE_PERMISSION_SEMANTICS")

    def test_no_fictional_independent_human(self):
        self.req["independent_human_review_claimed"] = True
        self.refused("C09_UNSAFE_PERMISSION_SEMANTICS")

    def test_amounts_canonical_positive_and_technical_only(self):
        for value in ("0", "-1", "01", "2.0", "", "1e9", "9" * 21, 0, False):
            self.req = req()
            self.req["amount_uwolo"] = value
            with self.assertRaises(owner.AuthorityHold):
                self.reviewed()
        self.req = req()
        self.req["fee_uwolo"] = "-1"
        self.refused("C09_NONCANONICAL_AMOUNT")
        self.req = req()
        self.req["amount_uwolo"] = str((1 << 63) + 1)
        self.refused("C09_AMOUNT_OUT_OF_TECHNICAL_RANGE")

    def test_expired_not_yet_valid_or_longer_than_120_seconds(self):
        self.req["expires_at"] = ISO(NOW - timedelta(seconds=1))
        self.refused("C09_EXACT_CANARY_WINDOW_INVALID")
        self.req = req()
        self.req["not_before"] = ISO(NOW + timedelta(seconds=1))
        self.refused("C09_EXACT_CANARY_WINDOW_INVALID")
        self.req = req()
        self.req["expires_at"] = ISO(NOW + timedelta(seconds=121))
        self.refused("C09_EXACT_CANARY_WINDOW_INVALID")

    def test_true_false_cannot_masquerade_as_height_or_amount(self):
        self.req["bank_height"] = True
        self.refused("C09_BANK_HEIGHT_INVALID")
        self.req = req()
        self.req["fee_uwolo"] = False
        self.refused("C09_NONCANONICAL_AMOUNT")

    def test_missing_source_bank_chain_or_recovery_roots_refused(self):
        for key in ("satchel_binary_sha256", "consensus_header_root_sha256",
                    "bank_root_sha256", "full_writer_fence_sha256",
                    "coordinated_backup_sha256", "isolated_restore_sha256",
                    "c01_c08_acceptance_bundle_sha256", "governance_ratification_sha256"):
            self.req = req()
            self.req[key] = "0" * 64
            self.refused("C09_PROOF_HASH_BINDING_INCOMPLETE")

    def test_new_claim_id_and_request_id_must_be_canonical(self):
        self.req["request_id"] = "c09-INVALID"
        self.refused("C09_FRESH_CANARY_IDENTITY_INVALID")
        self.req = req()
        self.req["nonce"] = "0" * 32
        self.refused("C09_NONCE_INVALID")

    def test_revoked_expired_enrollment_or_wrong_owner_pin_refused(self):
        enrollment = copy.deepcopy(self.enroll)
        enrollment["revoked"] = True
        self.refused("OWNER_PUBLIC_ENROLLMENT_INVALID", enrollment=enrollment)
        enrollment = copy.deepcopy(self.enroll)
        enrollment["valid_until"] = ISO(NOW - timedelta(seconds=1))
        self.refused("OWNER_ENROLLMENT_EXPIRED", enrollment=enrollment)
        self.refused("C09_EXPECTED_SOURCE_MISMATCH", source="f" * 40)

    def test_replaying_identical_valid_signature_is_still_non_authorizing(self):
        p = self.signed()
        first = self.reviewed(packet=p)
        second = self.reviewed(packet=p)
        self.assertEqual(first["nonce_commitment_sha256"], second["nonce_commitment_sha256"])
        self.assertFalse(first["offhost_one_use_nonce_consumed"])
        self.assertFalse(second["funded_canary_permit_issued"])

    def test_invalid_recipient_fails_syntax_without_claiming_checksum_proof(self):
        self.req["recipient"] = "cosmos1" + "q" * 40
        self.refused("C09_RECIPIENT_SYNTAX_UNQUALIFIED")

    def test_duplicate_json_key_rejected_even_with_matching_pin(self):
        signed = owner.canonical(self.signed())
        repeated = signed.replace(b'"owner_key_id":', b'"owner_key_id":"evil","owner_key_id":', 1)
        raw = owner.canonical(self.enroll)
        with self.assertRaisesRegex(owner.AuthorityHold, "^DUPLICATE_JSON_FIELD$"):
            reviewer.review(raw, repeated,
                            pinned_enrollment_sha256=hashlib.sha256(raw).hexdigest(),
                            pinned_owner_der_sha256=self.der_sha,
                            pinned_source_commit=self.req["source_commit"], now=NOW)

    def test_cli_reads_private_files_but_always_exit3(self):
        self.enroll["valid_from"] = ISO(datetime.now(timezone.utc) - timedelta(days=1))
        self.enroll["valid_until"] = ISO(datetime.now(timezone.utc) + timedelta(days=1))
        now = datetime.now(timezone.utc)
        self.req["not_before"] = ISO(now - timedelta(seconds=20))
        self.req["expires_at"] = ISO(now + timedelta(seconds=90))
        with tempfile.TemporaryDirectory(prefix="wolo-c09-test-cli-") as d:
            p = Path(d)
            e = p / "owner.json"
            signed = p / "intent.json"
            raw = owner.canonical(self.enroll)
            e.write_bytes(raw)
            signed.write_bytes(owner.canonical(self.signed()))
            e.chmod(0o600)
            signed.chmod(0o600)
            with patch.object(reviewer, "print", create=True) as out:
                exit_code = reviewer.main([
                    "--enrollment", str(e), "--signed-intent", str(signed),
                    "--pinned-enrollment-sha256", hashlib.sha256(raw).hexdigest(),
                    "--pinned-owner-der-sha256", self.der_sha,
                    "--pinned-source-commit", self.req["source_commit"],
                ])
                self.assertEqual(exit_code, 3)
                report = json.loads(out.call_args.args[0])
                self.assertFalse(report["financial_release_authorized"])

    def test_never_supports_execute_flag(self):
        with self.assertRaises(SystemExit) as caught:
            reviewer.main(["--execute"])
        self.assertEqual(caught.exception.code, 2)


if __name__ == "__main__":
    unittest.main()

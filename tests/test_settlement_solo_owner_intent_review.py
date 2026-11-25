"""Real disposable Ed25519 one-owner review, always NONAUTHORIZING."""
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
SCRIPT = ROOT / "scripts" / "settlement_solo_owner_intent_review.py"
spec = importlib.util.spec_from_file_location("solo_intent", SCRIPT)
solo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(solo)
NOW = datetime(2026, 10, 26, 14, 0, 0, tzinfo=timezone.utc)
ISO = lambda n: n.strftime("%Y-%m-%dT%H:%M:%SZ")
DIGEST = lambda c: c * 64


class SoloOwnerIntentionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="wolo-solo-test-")
        cls.path = Path(cls.temp.name)
        cls.private = cls.path / "operator-private.pem"
        cls.public = cls.path / "operator-public.pem"
        subprocess.run(["openssl", "genpkey", "-algorithm", "Ed25519",
                        "-out", str(cls.private)], check=True, capture_output=True)
        subprocess.run(["openssl", "pkey", "-in", str(cls.private),
                        "-pubout", "-out", str(cls.public)], check=True, capture_output=True)
        cls.pem = cls.public.read_text()
        der = subprocess.run(["openssl", "pkey", "-pubin", "-inform", "PEM",
                              "-outform", "DER"], input=cls.pem.encode("ascii"),
                             capture_output=True, check=True).stdout
        cls.der_hash = hashlib.sha256(der).hexdigest()

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def setUp(self):
        self.enroll = {
            "schema": solo.ENROLL_SCHEMA, "owner_key_id": "actual-human-owner",
            "public_key_pem": self.pem, "valid_from": ISO(NOW - timedelta(days=1)),
            "valid_until": ISO(NOW + timedelta(days=1)), "revoked": False,
        }
        self.req = {
            "schema": solo.SCHEMA, "chain_id": "wolo-1",
            "phase": "live_capture",
            "operation": "fence-drain-capture-hd-de",
            "source_commit": "a" * 40,
            "consensus_binary_sha256": DIGEST("1"),
            "settlement_binary_sha256": DIGEST("2"),
            "scope_sha256": DIGEST("3"),
            "global_fence_sha256": DIGEST("4"),
            "bank_proof_sha256": DIGEST("5"),
            "liability_proof_sha256": DIGEST("6"),
            "rollback_receipt_sha256": DIGEST("7"),
            "previous_phase_receipt_sha256": None,
            "nonce": "c" * 32,
            "not_before": ISO(NOW - timedelta(minutes=2)),
            "expires_at": ISO(NOW + timedelta(minutes=10)),
        }
        self.packet = None

    def signed(self):
        message = solo.DOMAIN + solo.canonical({
            "owner_key_id": self.enroll["owner_key_id"], "request": self.req
        })
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "msg"
            p.write_bytes(message)
            signature = subprocess.run(
                ["openssl", "pkeyutl", "-sign", "-rawin", "-inkey",
                 str(self.private), "-in", str(p)],
                capture_output=True, check=True).stdout
        return {
            "schema": solo.PACKET_SCHEMA,
            "owner_key_id": self.enroll["owner_key_id"],
            "request": copy.deepcopy(self.req),
            "signature_b64": base64.b64encode(signature).decode(),
        }

    def review(self, *, packet=None, trusted=None, pin=None, now=NOW):
        e = self.enroll if trusted is None else trusted
        raw_e = solo.canonical(e)
        p = self.signed() if packet is None else packet
        return solo.review(raw_e, solo.canonical(p),
                           pinned_enrollment_sha256=hashlib.sha256(raw_e).hexdigest()
                           if pin is None else pin,
                           pinned_owner_der_sha256=self.der_hash, now=now)

    def held(self, reason, **kwargs):
        with self.assertRaisesRegex(solo.AuthorityHold, "^" + reason + "$"):
            self.review(**kwargs)

    def test_real_single_person_cryptography_is_valid_but_never_a_permit(self):
        r = self.review()
        self.assertEqual(r["status"], "CRYPTO_VALID_NONAUTHORIZING")
        self.assertTrue(r["real_single_owner_signature_verified"])
        self.assertFalse(r["offhost_monotonic_nonce_consumed"])
        self.assertFalse(r["all_financial_writers_fenced"])
        self.assertFalse(r["owner_financial_operation_authorized"])
        self.assertFalse(r["independent_chain_finality_authenticated"])
        self.assertNotIn(self.pem, json.dumps(r))
        self.assertNotIn(self.req["nonce"], json.dumps(r))

    def test_existing_nonce_replay_cannot_infer_reservation(self):
        first, second = self.review(), self.review()
        self.assertEqual(first["nonce_commitment_sha256"],
                         second["nonce_commitment_sha256"])
        self.assertFalse(first["offhost_monotonic_nonce_consumed"])
        self.assertFalse(second["owner_financial_operation_authorized"])

    def test_tampered_signed_intent_fails_cryptographically(self):
        forged = self.signed()
        forged["request"]["source_commit"] = "b" * 40
        self.held("INVALID_PUBLIC_KEY_OR_SIGNATURE", packet=forged)

    def test_wrong_public_enrollment_pin_rejected(self):
        self.held("EXTERNAL_ENROLLMENT_PIN_MISMATCH", pin=DIGEST("f"))

    def test_wrong_der_public_key_pin_rejected(self):
        p = self.signed()
        raw = solo.canonical(self.enroll)
        with self.assertRaisesRegex(solo.AuthorityHold,
                                    "^PINNED_OWNER_PUBLIC_KEY_MISMATCH$"):
            solo.review(raw, solo.canonical(p),
                        pinned_enrollment_sha256=hashlib.sha256(raw).hexdigest(),
                        pinned_owner_der_sha256=DIGEST("f"), now=NOW)

    def test_revoked_or_out_of_window_owner_cannot_sign(self):
        e = copy.deepcopy(self.enroll)
        e["revoked"] = True
        self.held("OWNER_PUBLIC_ENROLLMENT_INVALID", trusted=e)
        e = copy.deepcopy(self.enroll)
        e["valid_until"] = ISO(NOW - timedelta(seconds=1))
        self.held("OWNER_ENROLLMENT_EXPIRED", trusted=e)

    def test_bad_phase_or_operation_is_never_authorized(self):
        p = self.signed()
        p["request"]["phase"] = "unrestricted_transfer"
        self.held("SIGNED_OPERATION_UNAPPROVED", packet=p)
        p = self.signed()
        p["request"]["operation"] = "send-tokens"
        self.held("SIGNED_OPERATION_UNAPPROVED", packet=p)

    def test_resume_requires_prior_phase_receipt_digest(self):
        self.req["phase"] = "resume"
        self.req["operation"] = "reviewed-resume-existing-hd-de-units"
        self.held("PRIOR_SIGNED_PHASE_LINEAGE_MISSING")
        self.req["previous_phase_receipt_sha256"] = DIGEST("8")
        r = self.review()
        self.assertEqual(r["phase"], "resume")
        self.assertFalse(r["owner_financial_operation_authorized"])

    def test_funded_canary_does_not_derive_payment_rights_from_signed_hashes(self):
        self.req["phase"] = "funded_activate"
        self.req["operation"] = "owner-authorized-bounded-canary"
        self.req["previous_phase_receipt_sha256"] = DIGEST("a")
        r = self.review()
        self.assertFalse(r["same_height_solvency_authenticated"])
        self.assertFalse(r["owner_financial_operation_authorized"])

    def test_phase_expiry_or_oversized_window_stop(self):
        self.req["expires_at"] = ISO(NOW - timedelta(seconds=1))
        self.held("OWNER_PHASE_WINDOW_INVALID")
        self.req["expires_at"] = ISO(NOW + timedelta(minutes=30))
        self.held("OWNER_PHASE_WINDOW_INVALID")

    def test_nonce_must_be_hex32_and_cannot_be_zero(self):
        self.req["nonce"] = "0" * 32
        self.held("FRESH_NONCE_INVALID")
        self.req["nonce"] = "broken"
        self.held("FRESH_NONCE_INVALID")

    def test_signature_decode_fail_closed(self):
        p = self.signed()
        p["signature_b64"] = "@INVALID@"
        self.held("SIGNATURE_ENCODING_INVALID", packet=p)

    def test_private_file_rejects_world_modes_and_symlink(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "public-review.json"
            p.write_bytes(solo.canonical(self.enroll))
            os.chmod(p, 0o600)
            self.assertEqual(solo.read_private(p), solo.canonical(self.enroll))
            os.chmod(p, 0o644)
            with self.assertRaisesRegex(solo.AuthorityHold, "^PRIVATE_FILE_UNSAFE$"):
                solo.read_private(p)
            p.unlink()
            p.symlink_to("/etc/passwd")
            with self.assertRaises(solo.AuthorityHold):
                solo.read_private(p)

    def test_cli_requires_actual_signature_and_exits_hold_three(self):
        # CLI uses a real clock; avoid mocking datetime.strptime and accidentally
        # replacing time validation with a MagicMock.
        current = datetime.now(timezone.utc)
        # Enrollment and request must share this clock; the fixed review fixture
        # otherwise expires independently of the CLI request being exercised.
        self.enroll["valid_from"] = ISO(current - timedelta(days=1))
        self.enroll["valid_until"] = ISO(current + timedelta(days=1))
        self.req["not_before"] = ISO(current - timedelta(minutes=1))
        self.req["expires_at"] = ISO(current + timedelta(minutes=10))
        with tempfile.TemporaryDirectory() as d:
            e = Path(d) / "owner.json"
            p = Path(d) / "intent.json"
            raw = solo.canonical(self.enroll)
            e.write_bytes(raw)
            p.write_bytes(solo.canonical(self.signed()))
            e.chmod(0o600)
            p.chmod(0o600)
            with patch.object(solo, "print", create=True) as printer:
                code = solo.main([
                    "--enrollment", str(e), "--packet", str(p),
                    "--pinned-enrollment-sha256", hashlib.sha256(raw).hexdigest(),
                    "--pinned-owner-der-sha256", self.der_hash,
                ])
            self.assertEqual(code, 3)
            result = json.loads(printer.call_args.args[0])
            self.assertFalse(result["owner_financial_operation_authorized"])


if __name__ == "__main__":
    unittest.main()

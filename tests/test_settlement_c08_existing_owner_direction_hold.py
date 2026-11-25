"""C08 historical device direction audit: adversarial ephemeral Ed25519, no money."""
from __future__ import annotations
import base64
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/"scripts"))
spec = importlib.util.spec_from_file_location(
    "review_existing_direction", ROOT/"scripts"/"settlement_c08_existing_owner_direction_hold.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

class ExistingOwnerDirectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="c08-dir-ephemeral-")
        cls.p = Path(cls.tmp.name)
        cls.private = cls.p/"synthetic.pem"
        cls.public = cls.p/"synthetic.pub"
        subprocess.run(["openssl", "genpkey", "-algorithm", "ED25519",
                        "-out", str(cls.private)], check=True, capture_output=True)
        subprocess.run(["openssl", "pkey", "-in", str(cls.private), "-pubout",
                        "-out", str(cls.public)], check=True, capture_output=True)
        cls.der = subprocess.run(
            ["openssl", "pkey", "-pubin", "-in", str(cls.public),
             "-outform", "DER"], capture_output=True, check=True).stdout
        cls.policy = (ROOT/m.POLICY_FILE).read_bytes()

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def setUp(self):
        self.req = {
            "schema": "wolo.single-human-device-governance-direction.v2",
            "chain_id": "wolo-1",
            "purpose": "DEVICE_GOVERNANCE_DIRECTION_ONLY_NO_FUNDS_NO_FINANCIAL_PERMIT",
            "source_commit": m.PINNED_DIRECTION_SOURCE,
            "source_proposal_sha256": hashlib.sha256(self.policy).hexdigest(),
            "nonce": "a"*64,
            "device_governance_public_key_der_sha256": hashlib.sha256(self.der).hexdigest(),
            "utc": m.PINNED_ISSUED_UTC,
            "single_human_owner": True,
            "custodian_reserve_reviewer_approver_same_human": True,
            "independent_human_review_available": False,
            "independent_human_review_claimed": False,
            "technical_custody_reviewer_keys_remain_distinct": True,
            "public_notice_min_seconds": 86400,
            "c03_writer_fence_c06_backup_c07_restore_required": True,
            "c04_unknown_payout_frozen_pending_proof": True,
            "c05_authenticated_common_height_bank_proof_required": True,
            "real_complete_liabilities_and_reserves_required": True,
            "c08_one_use_offhost_witness_required": True,
            "c09_separate_human_confirmed_transaction_signature_required": True,
            "legacy_8092_fallback_allowed": False,
            "funded_canary_max_uwolo": 0,
            "governance_implementation_source_reviewed": False,
            "owner_interactive_signature_confirmed_this_execution": False,
            "financial_release_authorized": False,
        }

    def payload(self, *, signature_from=None, change=None):
        source = self.req if signature_from is None else signature_from
        body = m.DOMAIN + m.canonical(source)
        message = self.p/"message"
        message.write_bytes(body)
        sig = subprocess.run(
            ["openssl", "pkeyutl", "-sign", "-rawin",
             "-inkey", str(self.private), "-in", str(message)],
            capture_output=True, check=True).stdout
        req = copy.deepcopy(self.req if change is None else change)
        return {
            "schema": m.DIRECTION_SCHEMA,
            "request": req,
            "signature_b64": base64.b64encode(sig).decode(),
            "public_key_pem": self.public.read_text(),
            "message_sha256": hashlib.sha256(body).hexdigest(),
            "device_signature_verified": True,
            "financial_release_authorized": False,
        }

    def audit(self, payload=None, *, override=None, policy=None, **pin_overrides):
        obj = self.payload() if payload is None else payload
        raw = m.canonical(obj)
        pins = {
            "PINNED_PACKET_SHA": hashlib.sha256(raw).hexdigest(),
            "PINNED_POLICY_SHA": hashlib.sha256(self.policy).hexdigest(),
            "PINNED_PUBLIC_DER_SHA": hashlib.sha256(self.der).hexdigest(),
        }
        pins.update(pin_overrides)
        with patch.multiple(m, **pins):
            return m.verify_existing_direction(raw, self.policy if policy is None else policy)

    def test_real_ephemeral_signature_is_strict_nonfinancial_hold(self):
        r = self.audit()
        self.assertEqual(r["status"], "HOLD_C08_VERIFIED_20261107_OWNER_DIRECTION_NOT_POLICY_RATIFICATION")
        self.assertTrue(r["existing_device_ed25519_signature_verified"])
        for k in ("financial_release_authorized", "owner_approved_current_funded_governance_policy",
                  "c09_funded_transaction_authorized", "c08_new_time_bounded_ratification_signature_present"):
            self.assertIs(r[k], False)
        self.assertNotIn(self.req["nonce"], json.dumps(r))
        self.assertNotIn(self.public.read_text(), json.dumps(r))

    def test_raw_packet_changed_without_source_pin_fails(self):
        packet = self.payload()
        packet["financial_release_authorized"] = True
        with self.assertRaisesRegex(m.Stop, "NOV7_DEVICE_DIRECTION_HASH_CHANGED"):
            self.audit(packet, PINNED_PACKET_SHA="f"*64)

    def test_validly_signed_funded_limit_refused(self):
        self.req["funded_canary_max_uwolo"] = 1
        with self.assertRaisesRegex(m.Stop, "CENTRALIZED_POLICY_OR_FINANCIAL_HOLD"):
            self.audit()

    def test_validly_signed_legacy_fallback_refused(self):
        self.req["legacy_8092_fallback_allowed"] = True
        with self.assertRaisesRegex(m.Stop, "CENTRALIZED_POLICY_OR_FINANCIAL_HOLD"):
            self.audit()

    def test_validly_signed_fake_independent_human_refused(self):
        self.req["independent_human_review_claimed"] = True
        with self.assertRaisesRegex(m.Stop, "CENTRALIZED_POLICY_OR_FINANCIAL_HOLD"):
            self.audit()

    def test_validly_signed_owner_interactive_funding_claim_refused(self):
        self.req["owner_interactive_signature_confirmed_this_execution"] = True
        with self.assertRaisesRegex(m.Stop, "CENTRALIZED_POLICY_OR_FINANCIAL_HOLD"):
            self.audit()

    def test_validly_signed_implementation_review_claim_refused(self):
        self.req["governance_implementation_source_reviewed"] = True
        with self.assertRaisesRegex(m.Stop, "CENTRALIZED_POLICY_OR_FINANCIAL_HOLD"):
            self.audit()

    def test_validly_signed_unapproved_source_refused(self):
        self.req["source_commit"] = "b"*40
        with self.assertRaisesRegex(m.Stop, "SIGNATURE_DIRECTION_SOURCE_OR_IDENTITY_CHANGED"):
            self.audit()

    def test_signature_mismatch_after_request_tamper_refused(self):
        packet = self.payload()
        packet["request"]["nonce"] = "b"*64
        with self.assertRaisesRegex(m.Stop, "SIGNED_MESSAGE_MISMATCH"):
            self.audit(packet)

    def test_tampered_signature_refused(self):
        packet = self.payload()
        packet["signature_b64"] = base64.b64encode(b"x"*64).decode()
        with self.assertRaisesRegex(m.Stop, "ED25519_SIGNATURE_INVALID"):
            self.audit(packet)

    def test_unreviewed_key_substitution_refused(self):
        with self.assertRaisesRegex(m.Stop, "PUBLIC_KEY_DER_ANCHOR_CHANGED"):
            self.audit(PINNED_PUBLIC_DER_SHA="c"*64)

    def test_changed_policy_refused(self):
        with self.assertRaisesRegex(m.Stop, "SOURCE_POLICY_HASH_CHANGED"):
            self.audit(policy=self.policy+b" ")

    def test_fake_ratified_policy_refused(self):
        policy=json.loads(self.policy)
        policy["status"]="RATIFIED"
        altered=m.canonical(policy)
        with self.assertRaisesRegex(m.Stop, "POLICY_ALREADY_RATIFIED_OR_CHANGED"):
            self.audit(policy=altered, PINNED_POLICY_SHA=hashlib.sha256(altered).hexdigest())

    def test_extra_field_in_signed_request_refused(self):
        self.req["extra_permit"] = True
        with self.assertRaisesRegex(m.Stop, "SIGNATURE_DIRECTION_SOURCE_OR_IDENTITY_CHANGED"):
            self.audit()

    def test_missing_signature_header_refused(self):
        packet=self.payload()
        packet.pop("signature_b64")
        with self.assertRaisesRegex(m.Stop, "DIRECTION_HEADER_OR_RELEASE_SCOPE_INVALID"):
            self.audit(packet)

if __name__ == "__main__":
    unittest.main()

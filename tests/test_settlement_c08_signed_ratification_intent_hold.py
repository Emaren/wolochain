"""C08: real Ed25519 ratification *intent* + public notice, always funded HOLD."""
from __future__ import annotations
import base64
from datetime import datetime,timezone,timedelta
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
SCRIPTS=ROOT/"scripts"
sys.path.insert(0,str(SCRIPTS))
SPEC=importlib.util.spec_from_file_location(
    "c08_signed_ratification_intent_hold",
    SCRIPTS/"settlement_c08_signed_ratification_intent_hold.py")
m=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)
POLICY=(ROOT/"docs"/"settlement-contracts"/
        "solo-owner-governance-proposal-20261106.json").read_bytes()
NOW=datetime(2026,11,8,12,32,0,tzinfo=timezone.utc)
ISO=lambda d:d.strftime("%Y-%m-%dT%H:%M:%SZ")

class SignedRatificationHold(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(prefix="c08-disposable-ed25519-")
        cls.folder=Path(cls.tmp.name)
        cls.private=cls.folder/"owner-temporary-only.key"
        cls.public=cls.folder/"owner-public.pem"
        subprocess.run(["openssl","genpkey","-algorithm","ED25519",
                        "-out",str(cls.private)],capture_output=True,check=True)
        subprocess.run(["openssl","pkey","-in",str(cls.private),
                        "-pubout","-out",str(cls.public)],capture_output=True,check=True)
        cls.pem=cls.public.read_text()
        pub_der=subprocess.run(["openssl","pkey","-pubin","-inform","PEM",
            "-outform","DER"],input=cls.pem.encode(),capture_output=True,check=True).stdout
        cls.der_sha=hashlib.sha256(pub_der).hexdigest()

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def setUp(self):
        self.raw_policy=POLICY
        self.enroll={"schema":m.solo.ENROLL_SCHEMA,
            "owner_key_id":"disposable-review-human",
            "public_key_pem":self.pem,
            "valid_from":ISO(NOW-timedelta(days=1)),
            "valid_until":ISO(NOW+timedelta(days=1)),
            "revoked":False}
        sample_body="CENTRALIZED SINGLE OWNER PUBLIC NOTICE; NO FUNDED RELEASE. "*30
        self.issue={"number":184,"html_url":m.notice.ISSUE_URL,
            "state":"open","closed_at":None,
            "created_at":m.notice.CREATED_UTC,
            "user":{"login":"Emaren"},"body":sample_body}
        self.repo={"full_name":"Emaren/wolochain",
                   "visibility":"public","has_issues":True}
        self.sha_patch=patch.object(m.notice,"EXACT_PUBLIC_BODY_SHA256",
                                    hashlib.sha256(sample_body.encode()).hexdigest())
        self.sha_patch.start()
        self.addCleanup(self.sha_patch.stop)
        self.request={
            "schema":m.SCHEMA,"chain_id":"wolo-1",
            "source_commit":"a"*40,
            "policy_sha256":hashlib.sha256(self.raw_policy).hexdigest(),
            "public_notice_sha256":m.notice.EXACT_PUBLIC_BODY_SHA256,
            "public_notice_uri":m.notice.ISSUE_URL,
            "public_notice_not_before":m.notice.EARLIEST_UTC,
            "approval_scope":m.APPROVAL_SCOPE,"human_operator_count":1,
            "independent_human_review_claimed":False,
            "new_permission_version_required":True,
            "allow_legacy_8092_fallback":False,
            "historical_liabilities_waived":False,
            "funded_limit_uwolo":0,
            "c09_transaction_permit_present":False,
            "nonce":"b"*32,
            "not_before":ISO(NOW-timedelta(seconds=30)),
            "expires_at":ISO(NOW+timedelta(seconds=60)),
        }

    def sign(self,domain=None):
        data=(m.DOMAIN if domain is None else domain)+m.solo.canonical({
            "owner_key_id":self.enroll["owner_key_id"],"request":self.request})
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"message"
            p.write_bytes(data)
            signature=subprocess.run(["openssl","pkeyutl","-sign","-rawin",
                "-inkey",str(self.private),"-in",str(p)],
                capture_output=True,check=True).stdout
        return {"schema":m.PACKET,
                "owner_key_id":self.enroll["owner_key_id"],
                "request":self.request.copy(),
                "signature_b64":base64.b64encode(signature).decode()}

    def audit(self,*, packet=None, enrollment=None,clock=NOW,pin=None,der=None):
        enrollment=m.solo.canonical(self.enroll if enrollment is None else enrollment)
        packet=m.solo.canonical(self.sign() if packet is None else packet)
        return m.review(
          policy_raw=self.raw_policy,
          notice_issue=self.issue,notice_repository=self.repo,
          owner_enrollment_raw=enrollment,signed_packet_raw=packet,
          pinned_enrollment_sha256=hashlib.sha256(enrollment).hexdigest()
            if pin is None else pin,
          pinned_owner_der_sha256=self.der_sha if der is None else der,
          now=clock)

    def stopped(self):
        with self.assertRaises((m.Stop,m.solo.AuthorityHold)):
            self.audit()

    def test_real_valid_signed_intent_is_non_authorizing(self):
        r=self.audit()
        self.assertEqual(r["status"],
            "HOLD_C08_SIGNATURE_VALID_RUNTIME_AND_AUTHORITY_NOT_RATIFIED")
        self.assertTrue(r["public_notice_24h_verified"])
        self.assertTrue(r["owner_intent_signature_cryptographically_verified"])
        self.assertTrue(r["one_human_centralized_control_disclosed"])
        for flag in (
           "owner_enrollment_external_pin_independently_trusted",
           "signed_source_commit_independently_authenticated",
           "independent_human_reviewer_available",
           "one_use_offhost_nonce_consumed",
           "governance_runtime_policy_implemented_and_ratified",
           "old_five_human_permits_converted","c03_fenced","c04_finality_proven",
           "c05_solvency_proven","c06_c07_same_capture_restored",
           "c09_exact_transfer_permit_present","funded_8094_8095_authorized",
           "financial_release_authorized","production_mutated"):
            self.assertIs(r[flag],False,flag)
        self.assertNotIn(self.pem,json.dumps(r))
        self.assertNotIn(self.request["nonce"],json.dumps(r))

    def test_signed_operation_cannot_be_reused_as_ratification(self):
        packet=self.sign(domain=m.solo.DOMAIN)
        with self.assertRaises(m.Stop):
            self.audit(packet=packet)

    def test_wrong_packet_signature_denied(self):
        packet=self.sign()
        packet["signature_b64"]=base64.b64encode(b"x"*64).decode()
        with self.assertRaises(m.Stop):
            self.audit(packet=packet)

    def test_notice_before_maturity_denied(self):
        self.request["not_before"]=ISO(NOW-timedelta(hours=3))
        with self.assertRaisesRegex(m.Stop,"C08_PUBLIC_NOTICE_24H_NOT_AUTHENTICATED_MATURE"):
            self.audit(clock=m.solo.utc(m.notice.EARLIEST_UTC)-timedelta(seconds=1))

    def test_notice_missing_or_edited_denied(self):
        self.issue["body"]+=" EDITED"
        with self.assertRaisesRegex(m.Stop,"C08_PUBLIC_NOTICE_SOURCE_UNVERIFIED"):
            self.audit()

    def test_notice_private_rejected(self):
        self.repo["visibility"]="private"
        self.stopped()

    def test_notice_closed_rejected(self):
        self.issue["state"]="closed"
        self.stopped()

    def test_notice_author_substituted_rejected(self):
        self.issue["user"]={"login":"attacker"}
        self.stopped()

    def test_outdated_notice_reference_rejected(self):
        self.request["public_notice_uri"]="https://example.org"
        self.stopped()

    def test_policy_digest_mismatch_rejected(self):
        self.request["policy_sha256"]="0"*64
        self.stopped()

    def test_mutated_policy_rejected_even_if_self_signed(self):
        doc=json.loads(self.raw_policy)
        doc["human_operator_count"]=2
        self.raw_policy=m.solo.canonical(doc)
        self.request["policy_sha256"]=hashlib.sha256(self.raw_policy).hexdigest()
        self.stopped()

    def test_policy_does_not_allow_five_human_silent_conversion(self):
        doc=json.loads(self.raw_policy)
        doc["old_five_human_permits_auto_convert"]=True
        self.raw_policy=m.solo.canonical(doc)
        self.request["policy_sha256"]=hashlib.sha256(self.raw_policy).hexdigest()
        self.stopped()

    def test_unknown_keys_rejected(self):
        self.request["unreviewed_bypass"]=True
        self.stopped()

    def test_invalid_source_identity_rejected(self):
        self.request["source_commit"]="not-a-source-sha"
        self.stopped()

    def test_altered_signature_after_signing_denied(self):
        packet=self.sign()
        packet["request"]["source_commit"]="c"*40
        with self.assertRaises(m.Stop):
            self.audit(packet=packet)

    def test_untrusted_public_enrollment_pin_rejected(self):
        with self.assertRaises(m.Stop):
            self.audit(pin="0"*64)

    def test_wrong_public_key_identity_rejected(self):
        with self.assertRaises(m.Stop):
            self.audit(der="a"*64)

    def test_revoked_owner_public_identity_rejected(self):
        self.enroll["revoked"]=True
        self.stopped()

    def test_external_signature_expired_rejected(self):
        self.request["expires_at"]=ISO(NOW)
        self.stopped()

    def test_zero_nonce_rejected(self):
        self.request["nonce"]="0"*32
        self.stopped()

    def test_overlong_ratification_window_rejected(self):
        self.request["expires_at"]=ISO(NOW+timedelta(minutes=6))
        self.stopped()

    def test_no_funded_quota(self):
        for n in (1,-1,True,"0"):
            self.request["funded_limit_uwolo"]=n
            self.stopped()

    def test_no_false_independent_human(self):
        self.request["independent_human_review_claimed"]=True
        self.stopped()

    def test_no_legacy_8092_fallback(self):
        self.request["allow_legacy_8092_fallback"]=True
        self.stopped()

    def test_no_waiver_historical_claims(self):
        self.request["historical_liabilities_waived"]=True
        self.stopped()

    def test_no_old_permit_reuse(self):
        self.request["new_permission_version_required"]=False
        self.stopped()

    def test_no_claimed_c09_transaction_permit(self):
        self.request["c09_transaction_permit_present"]=True
        self.stopped()

    def test_missing_private_signature_cli_does_not_ratify(self):
        with tempfile.TemporaryDirectory() as d:
            base=Path(d)
            with patch.object(m.notice,"live_fetch",return_value=(self.issue,self.repo)):
                r=m.main([
                 "--owner-enrollment",str(base/"missing-enrollment.json"),
                 "--owner-ratification-packet",str(base/"missing-packet.json"),
                 "--pinned-enrollment-sha256","a"*64,
                 "--pinned-owner-der-sha256","b"*64])
            self.assertEqual(r,2)

if __name__=="__main__":
    unittest.main()

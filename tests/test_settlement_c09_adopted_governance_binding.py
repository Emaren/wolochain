"""C09 signed exact canary must honor the genuine adopted C08 receipt, total <= 1 WOLO.

Only test-owned ephemeral Ed25519 credentials; no real operator key or funds.
"""
from __future__ import annotations
import base64
import copy
from datetime import datetime,timezone,timedelta
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
import settlement_c09_exact_canary_intent_review_hold as c09
import settlement_c08_governance_adoption_v2 as gov
import settlement_solo_owner_intent_review as own

NOW=datetime(2026,11,8,21,5,tzinfo=timezone.utc)
ST=lambda t:t.strftime("%Y-%m-%dT%H:%M:%SZ")

class RatifiedGovernanceCanaryContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix="c09-c08-disposable-owner-")
        cls.p=Path(cls.temp.name)
        cls.private=cls.p/"ephemeral-owner-only.pem"
        cls.public=cls.p/"ephemeral-public.pem"
        subprocess.run(["openssl","genpkey","-algorithm","Ed25519",
                        "-out",str(cls.private)],capture_output=True,check=True)
        subprocess.run(["openssl","pkey","-in",str(cls.private),
                        "-pubout","-out",str(cls.public)],capture_output=True,check=True)
        cls.pub=cls.public.read_bytes()
        cls.der=gov.public_der_hash(cls.pub)
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()
    def sign(self,data):
        with tempfile.TemporaryDirectory(prefix="c09-test-message-") as p:
            file=Path(p)/"message"
            file.write_bytes(data)
            return subprocess.run(["openssl","pkeyutl","-sign","-rawin",
                "-inkey",str(self.private),"-in",str(file)],
                check=True,capture_output=True).stdout
    def setUp(self):
        self.temp_root=tempfile.TemporaryDirectory(prefix="c09-test-ratification-")
        self.addCleanup(self.temp_root.cleanup)
        self.root=Path(self.temp_root.name)/"owner"
        self.root.mkdir(mode=0o700)
        self.body="ONE HUMAN CENTRALIZED FINANCIAL POLICY NOTICE NO CLAIM DELETION. "*30
        self.issue={"number":184,"html_url":gov.notice.ISSUE_URL,
                    "state":"open","closed_at":None,
                    "created_at":gov.notice.CREATED_UTC,
                    "user":{"login":"Emaren"},"body":self.body}
        self.repo_info={"full_name":"Emaren/wolochain",
                        "visibility":"public","has_issues":True}
        patches=[
            patch.object(gov,"OWNER_DER_SHA",self.der),
            patch.object(gov,"source_commit",return_value="e"*40),
            patch.object(gov.notice,"EXACT_PUBLIC_BODY_SHA256",
                         hashlib.sha256(self.body.encode()).hexdigest())
        ]
        for q in patches:q.start();self.addCleanup(q.stop)
        ratreq=gov.prepare_request(repo=ROOT,pem=self.pub,now=NOW,
                                   nonce="a"*32)
        ratpacket={"schema":gov.PACKET_SCHEMA,"request":ratreq,
          "signature_b64":base64.b64encode(
              self.sign(gov.signed_request(ratreq))).decode()}
        self.receipt,self.receipt_sha=gov.adopt(
            packet_raw=gov.canonical(ratpacket),
            public_pem=self.pub,repo=ROOT,root=self.root,now=NOW,
            notice_issue=self.issue,notice_repo=self.repo_info)
        self.enroll={
            "schema":own.ENROLL_SCHEMA,
            "owner_key_id":"disposable-c09-governance-owner",
            "public_key_pem":self.pub.decode("ascii"),
            "valid_from":ST(NOW-timedelta(days=1)),
            "valid_until":ST(NOW+timedelta(days=1)),
            "revoked":False}
        self.c09req={
            "schema":c09.SCHEMA,"chain_id":"wolo-1",
            "operation":"one-new-claim-canary-only",
            "fresh_claim_id":"fresh-c09-"+"a"*32,
            "native_claim_id":"900000000001",
            "request_id":"c09-"+"b"*32,
            "recipient":"wolo1"+"q"*39,
            "amount_uwolo":"700000","fee_uwolo":"1000",
            "bank_height":12345,"source_commit":"e"*40,
            "satchel_binary_sha256":"1"*64,
            "reviewer_binary_sha256":"2"*64,
            "consensus_header_root_sha256":"3"*64,
            "bank_root_sha256":"4"*64,
            "liability_root_sha256":"5"*64,
            "full_writer_fence_sha256":"6"*64,
            "coordinated_backup_sha256":"7"*64,
            "isolated_restore_sha256":"8"*64,
            "c01_c08_acceptance_bundle_sha256":"9"*64,
            "governance_ratification_sha256":self.receipt_sha,
            "rollback_receipt_sha256":"b"*64,
            "nonce":"c"*32,
            "not_before":ST(NOW-timedelta(seconds=10)),
            "expires_at":ST(NOW+timedelta(seconds=100)),
            "legacy_fallback_allowed":False,
            "retry_on_unknown_allowed":False,
            "independent_human_review_claimed":False,
            "one_operation_only":True}
    def c09_packet(self,req=None):
        q=self.c09req if req is None else req
        sig=self.sign(c09.DOMAIN+own.canonical({
              "owner_key_id":self.enroll["owner_key_id"],"request":q}))
        return {"schema":c09.PACKET_SCHEMA,
               "owner_key_id":self.enroll["owner_key_id"],
               "request":copy.deepcopy(q),
               "signature_b64":base64.b64encode(sig).decode()}
    def bound(self,req=None):
        enroll=own.canonical(self.enroll)
        return c09.review_with_adopted_governance(
            enroll,own.canonical(self.c09_packet(req)),
            pinned_enrollment_sha256=hashlib.sha256(enroll).hexdigest(),
            pinned_owner_der_sha256=self.der,
            pinned_source_commit="e"*40,
            ratification_root=self.root,
            governance_owner_public_pem=self.pub,
            governance_source_repo=ROOT,
            notice_issue=self.issue,notice_repository=self.repo_info,
            now=NOW)
    def stopped(self,reason=None,req=None):
        with self.assertRaises(own.AuthorityHold) as caught:
            self.bound(req)
        if reason is not None:
            self.assertIn(reason,str(caught.exception))
    def test_original_c08_signature_and_c09_canary_bound_without_money(self):
        out=self.bound()
        self.assertEqual(out["status"],
            "C09_SIGNED_INTENT_AND_C08_ADOPTION_VALID_FINANCIAL_RELEASE_HOLD")
        self.assertEqual(out["c08_ratification_receipt_sha256"],self.receipt_sha)
        self.assertEqual(out["maximum_signed_canary_including_fee_uwolo"],1000000)
        self.assertTrue(out["economic_canary_limit_ratified"])
        self.assertTrue(out["new_governance_policy_ratified_and_notice_elapsed"])
        self.assertFalse(out["funded_canary_permit_issued"])
        self.assertFalse(out["financial_release_authorized"])
    def test_second_valid_review_does_not_spend(self):
        a,b=self.bound(),self.bound()
        self.assertEqual(a["c08_ratification_receipt_sha256"],
                         b["c08_ratification_receipt_sha256"])
        self.assertFalse(a["offhost_one_use_nonce_consumed"])
        self.assertFalse(b["funded_canary_permit_issued"])
    def test_transaction_amount_over_1_wolo_denied(self):
        q=dict(self.c09req);q["amount_uwolo"]="1000001"
        self.stopped("C09_SIGNED_CANARY_PLUS_FEE_EXCEEDS_ONE_WOLO",q)
    def test_fee_must_fit_within_1_wolo(self):
        q=dict(self.c09req);q["fee_uwolo"]="400000"
        self.stopped("C09_SIGNED_CANARY_PLUS_FEE_EXCEEDS_ONE_WOLO",q)
    def test_exact_ceiling_with_zero_fee_allowed_without_spending(self):
        q=dict(self.c09req);q["amount_uwolo"]="1000000";q["fee_uwolo"]="0"
        out=self.bound(q)
        self.assertTrue(out["economic_canary_limit_ratified"])
        self.assertFalse(out["financial_release_authorized"])
    def test_different_signed_governance_digest_denied(self):
        q=dict(self.c09req);q["governance_ratification_sha256"]="f"*64
        self.stopped("C09_SIGNED_GOVERNANCE_RECEIPT_BINDING_CHANGED",q)
    def test_missing_owner_adoption_denied(self):
        (self.root/"adopted-governance-v2.json").unlink()
        self.stopped("C09_RATIFIED_GOVERNANCE_NOT_AUTHENTICATED")
    def test_altered_adopted_receipt_denied(self):
        f=self.root/"adopted-governance-v2.json"
        o=json.loads(f.read_text())
        o["financial_release_authorized"]=True
        f.write_bytes(gov.canonical(o))
        self.stopped("C09_RATIFIED_GOVERNANCE_NOT_AUTHENTICATED")
    def test_tampered_original_policy_signature_denied(self):
        f=self.root/"adopted-governance-v2.json"
        o=json.loads(f.read_text())
        o["signed_packet"]["signature_b64"]=base64.b64encode(b"x"*64).decode()
        f.write_bytes(gov.canonical(o))
        self.stopped("C09_RATIFIED_GOVERNANCE_NOT_AUTHENTICATED")
    def test_wrong_governance_public_identity_denied(self):
        with patch.object(gov,"OWNER_DER_SHA","0"*64):
            self.stopped("C09_DIFFERENT_OWNER_FROM_ADOPTED_GOVERNANCE")
    def test_public_notice_body_changed_denied(self):
        self.issue["body"]+=" MALICIOUS_EDIT"
        self.stopped("C09_RATIFIED_GOVERNANCE_NOT_AUTHENTICATED")
    def test_forged_c09_signature_denied_even_with_valid_governance(self):
        q=dict(self.c09req);q["amount_uwolo"]="1"
        p=self.c09_packet()
        p["request"]["amount_uwolo"]="1"
        enrollment=own.canonical(self.enroll)
        with self.assertRaises(own.AuthorityHold):
            c09.review_with_adopted_governance(
                enrollment,own.canonical(p),
                pinned_enrollment_sha256=hashlib.sha256(enrollment).hexdigest(),
                pinned_owner_der_sha256=self.der,
                pinned_source_commit="e"*40,
                ratification_root=self.root,governance_owner_public_pem=self.pub,
                governance_source_repo=ROOT,
                notice_issue=self.issue,notice_repository=self.repo_info,now=NOW)
    def test_wrong_owner_dir_permissions_refused(self):
        self.root.chmod(0o755)
        self.stopped("C09_RATIFIED_GOVERNANCE_NOT_AUTHENTICATED")
    def test_c09_no_c08_evidence_stays_original_hold(self):
        enrollment=own.canonical(self.enroll)
        out=c09.review(enrollment,own.canonical(self.c09_packet()),
            pinned_enrollment_sha256=hashlib.sha256(enrollment).hexdigest(),
            pinned_owner_der_sha256=self.der,pinned_source_commit="e"*40,now=NOW)
        self.assertFalse(out["new_governance_policy_ratified_and_notice_elapsed"])
    def test_syntactic_old_transfer_no_repeat(self):
        q=dict(self.c09req);q["fresh_claim_id"]="889"
        self.stopped("C09_FRESH_CANARY_IDENTITY_INVALID",q)

if __name__=="__main__":
    unittest.main()

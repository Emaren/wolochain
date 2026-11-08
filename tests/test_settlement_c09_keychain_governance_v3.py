"""C09 exact-canary preflight against real P256 C08 signed receipt.

Uses disposable P-256 key and synthetic exact C09 request (not a transaction
signature): proof is ZERO SPENDING. No user Keychain, RPC, broadcast, or SQL.
"""
from __future__ import annotations
from datetime import datetime,timedelta,timezone
import hashlib
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
sys.path.insert(0,str(ROOT/"tests"))
import settlement_c09_exact_canary_intent_review_hold as c09
import settlement_c08_keychain_policy_adoption_v3 as gov
import settlement_solo_owner_public_notice_hold as notice
from test_settlement_c09_exact_canary_intent_review_hold import req

NOW=datetime(2026,11,8,22,5,0,tzinfo=timezone.utc)
ST=lambda t:t.strftime("%Y-%m-%dT%H:%M:%SZ")

class CrossDomainRatification(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix="c09-v3-cross-domain-")
        cls.folder=Path(cls.temp.name)
        cls.key=cls.folder/"p256-fixture.pem"
        r=subprocess.run(["openssl","genpkey","-algorithm","EC",
           "-pkeyopt","ec_paramgen_curve:P-256","-out",str(cls.key)],
           capture_output=True,timeout=8)
        assert r.returncode==0
        der=subprocess.run(["openssl","pkey","-in",str(cls.key),
           "-pubout","-outform","DER"],capture_output=True,check=True).stdout
        assert der.startswith(gov.SPKI) and len(der)==91
        cls.pub=der[len(gov.SPKI):]
        cls.pub_sha=hashlib.sha256(cls.pub).hexdigest()
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix="c09-v3-policy-proof-")
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)/"owner"
        self.root.mkdir(mode=0o700)
        gov.write_private(self.root/gov.PUB_FILE,self.pub)
        self.body="ONE HUMAN C08 P256 OWNER ENROLLMENT "+self.pub_sha
        self.comment={"id":gov.KEY_COMMENT_ID,
          "issue_url":"https://api.github.com/repos/Emaren/wolochain/issues/184",
          "user":{"login":"Emaren"},"body":self.body}
        self.issue={"state":"open"}
        self.repo_info={"full_name":"Emaren/wolochain"}
        patches=[
          patch.object(gov,"OWNER_X963_SHA",self.pub_sha),
          patch.object(gov,"KEY_COMMENT_SHA",hashlib.sha256(self.body.encode()).hexdigest()),
          patch.object(gov,"git_commit",return_value="e"*40),
          patch.object(notice,"inspect_notice",
                return_value={"status":"PASS_NOTICE_TIME_ONLY_ALL_FINANCIAL_GATES_HOLD"})
        ]
        for p in patches:p.start();self.addCleanup(p.stop)
        receipt=gov.ceremony(ROOT,self.root,now=NOW,nonce="a"*32,
             comment=self.comment,issue=self.issue,repo_info=self.repo_info,
             signer=self.sign)
        self.receipt_sha=receipt["receipt_sha256"]
        self.request=req()
        self.request["source_commit"]="e"*40
        self.request["governance_ratification_sha256"]=self.receipt_sha
        self.request["not_before"]=ST(NOW-timedelta(seconds=5))
        self.request["expires_at"]=ST(NOW+timedelta(seconds=90))
    def sign(self,message):
        with tempfile.TemporaryDirectory(prefix="c09-v3-sign-fixture-") as folder:
            msg=Path(folder)/"message";msg.write_bytes(message)
            signature=Path(folder)/"signature"
            p=subprocess.run(["openssl","dgst","-sha256","-sign",
                str(self.key),"-out",str(signature),str(msg)],
                capture_output=True,timeout=8)
            self.assertEqual(p.returncode,0)
            return signature.read_bytes()
    def check(self,q=None):
        return c09.qualify_c09_request_against_keychain_governance_v3(
           self.request if q is None else q,
           governance_root=self.root,governance_public_x963=self.pub,
           governance_source_repo=ROOT,now=NOW,comment=self.comment,
           notice_issue=self.issue,notice_repo=self.repo_info)
    def stop(self,code,q=None):
        with self.assertRaises(c09.owner.AuthorityHold) as context:
            self.check(q)
        self.assertEqual(str(context.exception),code)
    def test_actual_signed_p256_c08_receipt_enforces_zero_spend(self):
        out=self.check()
        self.assertEqual(out["status"],
           "C09_C08_V3_GOVERNANCE_PROOF_VALID_EXECUTION_HOLD")
        self.assertEqual(out["c08_adoption_receipt_sha256"],self.receipt_sha)
        self.assertEqual(out["future_maximum_amount_including_fee_uwolo"],1000000)
        self.assertFalse(out["financial_release_authorized"])
        self.assertFalse(out["transaction_specific_owner_signature_proven_by_this_method"])
    def test_valid_one_wolo_exact_ceiling_is_not_funded_permit(self):
        q=dict(self.request)
        q["amount_uwolo"]="1000000";q["fee_uwolo"]="0"
        self.assertFalse(self.check(q)["financial_release_authorized"])
    def test_amount_over_ceiling_denied(self):
        q=dict(self.request);q["amount_uwolo"]="1000001"
        self.stop("C09_C08_V3_AMOUNT_PLUS_FEE_OVER_ONE_WOLO",q)
    def test_gas_fee_over_ceiling_denied(self):
        q=dict(self.request);q["fee_uwolo"]="301000"
        self.stop("C09_C08_V3_AMOUNT_PLUS_FEE_OVER_ONE_WOLO",q)
    def test_unlinked_c08_sha_denied(self):
        q=dict(self.request);q["governance_ratification_sha256"]="f"*64
        self.stop("C09_C08_V3_SIGNED_RECEIPT_SHA_MISMATCH",q)
    def test_no_c08_receipt_denied(self):
        (self.root/gov.RECEIPT_FILE).unlink()
        self.stop("C09_C08_V3_SIGNED_ADOPTION_UNAVAILABLE")
    def test_forged_c08_signature_denied(self):
        file=self.root/gov.RECEIPT_FILE
        import json,base64
        r=json.loads(file.read_text())
        r["signed_packet"]["signature_der_b64"]=base64.b64encode(b"a"*70).decode()
        file.write_bytes(gov.canonical(r));file.chmod(0o600)
        self.stop("C09_C08_V3_SIGNED_ADOPTION_UNAVAILABLE")
    def test_original_ed_key_not_cross_signed_by_new_p256(self):
        out=self.check()
        self.assertFalse(out["original_ed25519_key_falsely_reused"])
    def test_public_identity_github_author_mismatch_denied(self):
        self.comment["user"]["login"]="attacker"
        self.stop("C09_C08_V3_SIGNED_ADOPTION_UNAVAILABLE")
    def test_source_not_consensus_finality(self):
        out=self.check()
        self.assertFalse(out["all_c01_c07_gates_accepted"])
        self.assertFalse(out["offhost_one_use_nonce_consumed"])
    def test_historical_claim_id_rejected(self):
        q=dict(self.request);q["fresh_claim_id"]="889"
        self.stop("C09_FRESH_CANARY_IDENTITY_INVALID",q)
    def test_legacy_fallback_rejected(self):
        q=dict(self.request);q["legacy_fallback_allowed"]=True
        self.stop("C09_UNSAFE_PERMISSION_SEMANTICS",q)
    def test_unknown_retry_rejected(self):
        q=dict(self.request);q["retry_on_unknown_allowed"]=True
        self.stop("C09_UNSAFE_PERMISSION_SEMANTICS",q)

if __name__=="__main__":unittest.main()

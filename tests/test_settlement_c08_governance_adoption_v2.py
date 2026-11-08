"""C08 real governance adoption: public real Ed25519, no funds, no fake reviewer.

23+ hermetic positive/negative tests use disposable test-only signing keys.
No production key is loaded, no bank RPC, no PostgreSQL or native funding.
"""
from __future__ import annotations

import base64
from datetime import datetime,timezone,timedelta
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
S=ROOT/"scripts"
sys.path.insert(0,str(S))
spec=importlib.util.spec_from_file_location(
 "settlement_c08_governance_adoption_v2",
 S/"settlement_c08_governance_adoption_v2.py")
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
AT=datetime(2026,11,8,21,0,0,tzinfo=timezone.utc)
COMMIT="a"*40

class TestRealAdoption(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix="c08-policy-adoption-ed25519-")
        cls.path=Path(cls.temp.name)
        cls.key=cls.path/"test-only.key"
        cls.pem=cls.path/"test-only-public.pem"
        subprocess.run(["openssl","genpkey","-algorithm","ED25519","-out",str(cls.key)],
                       check=True,capture_output=True)
        subprocess.run(["openssl","pkey","-in",str(cls.key),
                        "-pubout","-out",str(cls.pem)],check=True,capture_output=True)
        cls.pub=cls.pem.read_bytes()
        cls.derhash=m.public_der_hash(cls.pub)
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()
    def setUp(self):
        self.temp_root=tempfile.TemporaryDirectory(prefix="c08-disposable-registry-")
        self.addCleanup(self.temp_root.cleanup)
        self.root=Path(self.temp_root.name)/"owner"
        self.root.mkdir(mode=0o700)
        self.body="ONE HUMAN PUBLIC CENTRALIZED OWNER NOTICE NO CUSTOMER DEBT WAIVER. "*30
        self.issue={
            "number":184,"html_url":m.notice.ISSUE_URL,
            "state":"open","closed_at":None,
            "created_at":m.notice.CREATED_UTC,
            "user":{"login":"Emaren"},"body":self.body}
        self.repo_info={"full_name":"Emaren/wolochain",
          "visibility":"public","has_issues":True}
        self.patches=[
            patch.object(m,"OWNER_DER_SHA",self.derhash),
            patch.object(m,"source_commit",return_value=COMMIT),
            patch.object(m.notice,"EXACT_PUBLIC_BODY_SHA256",
                         hashlib.sha256(self.body.encode()).hexdigest())
        ]
        for p in self.patches:p.start();self.addCleanup(p.stop)
        self.request=m.prepare_request(repo=ROOT,pem=self.pub,now=AT,
                                       nonce="1"*32)
    def packet(self,request=None,domain=None,signature=None):
        q=self.request if request is None else request
        if signature is None:
            raw=(m.DOMAIN if domain is None else domain)+m.canonical(q)
            with tempfile.TemporaryDirectory(prefix="c08-test-sign-") as tmp:
                f=Path(tmp)/"msg";f.write_bytes(raw)
                signature=subprocess.run(
                    ["openssl","pkeyutl","-sign","-rawin",
                     "-inkey",str(self.key),"-in",str(f)],
                    check=True,capture_output=True).stdout
        return {"schema":m.PACKET_SCHEMA,"request":q,
                "signature_b64":base64.b64encode(signature).decode()}
    def verify(self,p=None,at=AT):
        return m.verify_packet(packet_raw=m.canonical(self.packet() if p is None else p),
          public_pem=self.pub,repo=ROOT,now=at,
          notice_issue=self.issue,notice_repo=self.repo_info)
    def accept(self,p=None,at=AT):
        return m.adopt(packet_raw=m.canonical(self.packet() if p is None else p),
          public_pem=self.pub,repo=ROOT,root=self.root,now=at,
          notice_issue=self.issue,notice_repo=self.repo_info)
    def stopped(self,p=None,at=AT):
        with self.assertRaises((m.Hold,m.notice.NoticeStop)):
            self.verify(p,at)
    def test_source_policy_has_zero_funds(self):
        data=json.loads(m.load_policy(ROOT))
        self.assertEqual(data["initial_funded_allowance_uwolo"],0)
        self.assertFalse(data["legacy_8092_fallback_allowed"])
        self.assertFalse(data["old_unknown_claims_deleted_or_waived"])
        self.assertEqual(data["human_operator_count"],1)
    def test_owner_prepared_nonce_source_and_no_funding(self):
        self.assertEqual(self.request["source_commit"],COMMIT)
        self.assertEqual(self.request["policy_sha256"],m.POLICY_SHA)
        self.assertEqual(self.request["owner_der_sha256"],self.derhash)
        self.assertEqual(self.request["initial_funded_allowance_uwolo"],0)
        self.assertFalse(self.request["adoption_is_transaction_permit"])
        self.assertEqual(self.request["nonce"],"1"*32)
    def test_genuine_signature_and_public_notice_pass(self):
        p=self.verify()
        self.assertEqual(p["schema"],m.PACKET_SCHEMA)
    def test_real_adoption_writes_exactly_one_finance_disabled_receipt(self):
        receipt,digest=self.accept()
        self.assertEqual(receipt["status"],
            "PASS_C08_OWNER_GOVERNANCE_POLICY_ADOPTED_NO_FUNDS")
        self.assertFalse(receipt["financial_release_authorized"])
        self.assertEqual(receipt["funded_allowance_uwolo"],0)
        self.assertEqual(receipt["source_commit"],COMMIT)
        self.assertNotIn("private",json.dumps(receipt).lower())
        f=self.root/"adopted-governance-v2.json"
        self.assertEqual(hashlib.sha256(f.read_bytes()).hexdigest(),digest)
        self.assertEqual(f.stat().st_mode&0o777,0o600)
    def test_adopted_receipt_still_verifies_after_signature_expired(self):
        self.accept()
        proof=m.inspect_adoption(root=self.root,public_pem=self.pub,repo=ROOT,
            notice_issue=self.issue,notice_repo=self.repo_info)
        self.assertEqual(proof["status"],"PASS_C08_GOVERNANCE_ADOPTION_PROOF_VERIFIED")
        self.assertFalse(proof["financial_release_authorized"])
    def test_existing_adoption_replay_rejected(self):
        self.accept()
        with self.assertRaisesRegex(m.Hold,"ADOPTION_ALREADY_EXISTS"):
            self.accept()
    def test_different_signed_packet_cannot_replace_adoption(self):
        self.accept()
        q=dict(self.request);q["nonce"]="2"*32
        with self.assertRaisesRegex(m.Hold,"ADOPTION_ALREADY_EXISTS"):
            self.accept(p=self.packet(q))
    def test_missing_owner_signature_denied(self):
        self.stopped(p=self.packet(signature=b"x"*64))
    def test_changed_signer_key_denied(self):
        with patch.object(m,"OWNER_DER_SHA","0"*64):
            self.stopped()
    def test_old_direction_signature_domain_denied(self):
        self.stopped(p=self.packet(domain=b"AOE2WAR-WOLO-SINGLE-HUMAN-NONFINANCIAL-GOVERNANCE-V2\x00"))
    def test_false_independent_human_reviewer_denied(self):
        q=dict(self.request);q["independent_human_review_claimed"]=True
        self.stopped(p=self.packet(q))
    def test_wrong_human_count_denied(self):
        q=dict(self.request);q["owner_human_count"]=2
        self.stopped(p=self.packet(q))
    def test_legacy_8092_fallback_denied(self):
        q=dict(self.request);q["legacy_8092_fallback_allowed"]=True
        self.stopped(p=self.packet(q))
    def test_historical_claim_waiver_denied(self):
        q=dict(self.request);q["historical_claims_waived"]=True
        self.stopped(p=self.packet(q))
    def test_funded_quota_denied_even_if_signed(self):
        q=dict(self.request);q["initial_funded_allowance_uwolo"]=1
        self.stopped(p=self.packet(q))
    def test_c09_permit_smuggling_denied(self):
        q=dict(self.request);q["c09_transaction_signature_present"]=True
        self.stopped(p=self.packet(q))
    def test_adoption_as_transfer_permit_denied(self):
        q=dict(self.request);q["adoption_is_transaction_permit"]=True
        self.stopped(p=self.packet(q))
    def test_unknown_extra_field_denied(self):
        q=dict(self.request);q["emergency_skip_gate"]="C03"
        self.stopped(p=self.packet(q))
    def test_incorrect_commit_denied(self):
        q=dict(self.request);q["source_commit"]="b"*40
        self.stopped(p=self.packet(q))
    def test_incorrect_policy_sha_denied(self):
        q=dict(self.request);q["policy_sha256"]="c"*64
        self.stopped(p=self.packet(q))
    def test_incorrect_public_notice_denied(self):
        self.issue["body"]+=" DRIFT"
        self.stopped()
    def test_notice_not_mature_denied(self):
        self.stopped(at=m.notice.utc(m.notice.EARLIEST_UTC)-timedelta(seconds=5))
    def test_forged_private_notice_rejected(self):
        self.repo_info["visibility"]="private"
        self.stopped()
    def test_replaced_notice_owner_denied(self):
        self.issue["user"]={"login":"attacker"}
        self.stopped()
    def test_expired_request_denied(self):
        self.stopped(at=AT+timedelta(minutes=21))
    def test_zero_nonce_denied(self):
        q=dict(self.request);q["nonce"]="0"*32
        self.stopped(p=self.packet(q))
    def test_oversize_signature_window_denied(self):
        q=dict(self.request);q["expires_at"]=m.stamp(AT+timedelta(days=1))
        self.stopped(p=self.packet(q))
    def test_duplicate_json_key_rejected(self):
        p=self.packet()
        s=m.canonical(p).decode()
        s=s.replace('"schema":','"schema":"evil","schema":',1)
        with self.assertRaises(m.Hold):
            m.verify_packet(packet_raw=s.encode(),public_pem=self.pub,
                repo=ROOT,now=AT,notice_issue=self.issue,notice_repo=self.repo_info)
    def test_receipt_mutation_detected(self):
        self.accept()
        f=self.root/"adopted-governance-v2.json"
        o=json.loads(f.read_bytes())
        o["financial_release_authorized"]=True
        f.write_bytes(m.canonical(o))
        with self.assertRaises(m.Hold):
            m.inspect_adoption(root=self.root,public_pem=self.pub,repo=ROOT,
                notice_issue=self.issue,notice_repo=self.repo_info)
    def test_plaintext_owner_key_denied(self):
        plaintext=self.root/"plaintext-key.pem"
        plaintext.write_bytes(self.key.read_bytes());plaintext.chmod(0o600)
        with self.assertRaisesRegex(m.Hold,"UNENCRYPTED"):
            m.sign_packet(self.request,self.pub,plaintext,now=AT,commit=COMMIT)
    def test_wrong_directory_mode_denied(self):
        self.root.chmod(0o755)
        with self.assertRaisesRegex(m.Hold,"PRIVATE_DIR_UNSAFE"):
            self.accept()
    def test_no_financial_execution_calls_in_source(self):
        code=(S/"settlement_c08_governance_adoption_v2.py").read_text()
        for banned in ("tx bank send","systemctl start wolo-satchel",
           "ALTER ROLE","GRANT ALL","db.execute",":8092/settlement"):
            self.assertNotIn(banned,code)
        self.assertIn("initial_funded_allowance_uwolo",code)
        self.assertIn("financial_release_authorized",code)

if __name__=="__main__":unittest.main()

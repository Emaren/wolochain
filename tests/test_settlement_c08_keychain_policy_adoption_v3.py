"""Real P-256 C08 governance owner adoption and adversarial tests.

Disposable OpenSSL P-256 keys only; no macOS Keychain, user private key,
chain bank, live GitHub, PostgreSQL, wallet RPC, or WOLO transfer.
"""
from __future__ import annotations
import base64
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
import settlement_c08_keychain_policy_adoption_v3 as m
import settlement_solo_owner_public_notice_hold as notice

NOW=datetime(2026,11,8,22,0,0,tzinfo=timezone.utc)

class KeychainGovernanceV3(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(prefix="c08-p256-disposable-signing-")
        cls.folder=Path(cls.tmp.name)
        cls.key=cls.folder/"disposable-private-p256.pem"
        generated=subprocess.run(["openssl","genpkey","-algorithm","EC",
            "-pkeyopt","ec_paramgen_curve:P-256","-out",str(cls.key)],
            capture_output=True,timeout=8)
        assert generated.returncode==0
        cls.key.chmod(0o600)
        der=subprocess.run(["openssl","pkey","-in",str(cls.key),
            "-pubout","-outform","DER"],capture_output=True,check=True,timeout=8).stdout
        assert len(der)==91 and der.startswith(m.SPKI)
        cls.public=der[len(m.SPKI):]
        cls.public_sha=hashlib.sha256(cls.public).hexdigest()
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def setUp(self):
        self.tmp_root=tempfile.TemporaryDirectory(prefix="c08-v3-test-adoption-")
        self.addCleanup(self.tmp_root.cleanup)
        self.root=Path(self.tmp_root.name)/"owner"
        self.root.mkdir(mode=0o700)
        m.write_private(self.root/m.PUB_FILE,self.public)
        self.body=("ONE HUMAN P256 GOVERNANCE SIGNER ONLY. PUBLIC ENROLLMENT. "
                   +self.public_sha)*3
        self.comment={
            "id":m.KEY_COMMENT_ID,
            "issue_url":"https://api.github.com/repos/Emaren/wolochain/issues/184",
            "user":{"login":"Emaren"},
            "body":self.body}
        self.issue={"state":"open"}
        self.repo_info={"full_name":"Emaren/wolochain"}
        self.patches=[
            patch.object(m,"OWNER_X963_SHA",self.public_sha),
            patch.object(m,"KEY_COMMENT_SHA",hashlib.sha256(self.body.encode()).hexdigest()),
            patch.object(m,"git_commit",return_value="e"*40),
            patch.object(notice,"inspect_notice",
                return_value={"status":"PASS_NOTICE_TIME_ONLY_ALL_FINANCIAL_GATES_HOLD"}),
        ]
        for p in self.patches:p.start();self.addCleanup(p.stop)
    def sign(self,message):
        with tempfile.TemporaryDirectory(prefix="c08-v3-private-signature-fixture-") as root:
            data=Path(root)/"message"
            data.write_bytes(message)
            sig=Path(root)/"sig.der"
            p=subprocess.run(["openssl","dgst","-sha256","-sign",
                str(self.key),"-out",str(sig),str(data)],
                capture_output=True,timeout=8)
            self.assertEqual(p.returncode,0)
            return sig.read_bytes()
    def ceremony(self,**opts):
        return m.ceremony(ROOT,self.root,now=NOW,nonce="f"*32,
             comment=self.comment,issue=self.issue,repo_info=self.repo_info,
             signer=self.sign,**opts)
    def status(self,when=None):
        return m.adopted(self.root,ROOT,self.public,now=when or NOW,
             comment=self.comment,issue=self.issue,repo_info=self.repo_info)
    def reject(self,token,fn):
        with self.assertRaises((m.Hold,m.old.Hold,OSError)) as exc:
            fn()
        if token:self.assertIn(token,str(exc.exception))
    def test_source_policy_still_zero_and_future_cap_one_wolo(self):
        policy=json.loads(m.old.load_policy(ROOT))
        self.assertEqual(policy["initial_funded_allowance_uwolo"],0)
        self.assertEqual(policy["separately_signed_future_c09_canary_ceiling_uwolo"],1000000)
        self.assertFalse(policy["legacy_8092_fallback_allowed"])
        self.assertFalse(policy["old_unknown_claims_deleted_or_waived"])
    def test_real_ecdsa_p256_adoption_zero_funds_success(self):
        result=self.ceremony()
        self.assertEqual(result["status"],
          "PASS_C08_ONE_HUMAN_KEYCHAIN_GOVERNANCE_ADOPTED_NO_FUNDS")
        self.assertFalse(result["financial_release_authorized"])
        doc=json.loads((self.root/m.RECEIPT_FILE).read_text())
        self.assertEqual(doc["owner_public_x963_sha256"],self.public_sha)
        self.assertTrue(doc["historic_ed25519_key_not_used"])
        self.assertTrue(doc["login_keychain_software_key_not_secure_enclave"])
        self.assertFalse(doc["c09_permit_issued"])
        self.assertEqual(doc["standing_funded_allowance_uwolo"],0)
        self.assertEqual(doc["future_c09_canary_ceiling_uwolo"],1000000)
    def test_actual_signed_receipt_still_authenticates_after_expiry(self):
        self.ceremony()
        r=self.status(NOW+timedelta(days=5))
        self.assertEqual(r["status"],
          "PASS_C08_KEYCHAIN_GOVERNANCE_OWNER_ADOPTION_VERIFIED")
        self.assertFalse(r["financial_release_authorized"])
    def test_one_time_adoption_replay_denied(self):
        self.ceremony()
        self.reject("C08_V3_ALREADY_ADOPTED_NO_REPLAY",self.ceremony)
    def test_other_nonce_cannot_replace_adoption(self):
        self.ceremony()
        self.reject("C08_V3_ALREADY_ADOPTED_NO_REPLAY",
            lambda:m.ceremony(ROOT,self.root,now=NOW,nonce="1"*32,
             comment=self.comment,issue=self.issue,repo_info=self.repo_info,
             signer=self.sign))
    def test_public_owner_key_wrong(self):
        with patch.object(m,"OWNER_X963_SHA","0"*64):
            self.reject("PUBLIC_KEY_ANCHOR_CHANGED",self.ceremony)
    def test_signature_failure_never_writes_adoption(self):
        def bad(message):return b"x"*70
        self.reject("ECDSA_SIGNATURE_ENCODING",
            lambda:m.ceremony(ROOT,self.root,now=NOW,nonce="f"*32,
             comment=self.comment,issue=self.issue,repo_info=self.repo_info,
             signer=bad))
        self.assertFalse((self.root/m.RECEIPT_FILE).exists())
    def test_old_key_signature_domain_cannot_substitute(self):
        msg=b"AOE2WAR-WOLO-SINGLE-HUMAN-NONFINANCIAL-GOVERNANCE-V2\x00hello"
        self.reject("SIGNED_MESSAGE_DOMAIN",
             lambda:m.verify_ecdsa(msg,self.sign(msg),self.public))
    def test_altered_signed_amount_denied(self):
        q=m.prepared_request(ROOT,NOW,nonce="f"*32)
        q["standing_funded_allowance_uwolo"]=1
        self.reject("SIGNED_POLICY_SCOPE_INVALID",
            lambda:m.request_valid(q,NOW,"e"*40))
    def test_future_canary_ceiling_cannot_be_raised(self):
        q=m.prepared_request(ROOT,NOW,nonce="f"*32)
        q["future_c09_canary_ceiling_uwolo"]=10000000
        self.reject("SIGNED_POLICY_SCOPE_INVALID",
            lambda:m.request_valid(q,NOW,"e"*40))
    def test_historical_claim_waiver_and_8092_denied(self):
        for key in ("historical_claims_waived","legacy_8092_fallback_allowed"):
            q=m.prepared_request(ROOT,NOW,nonce="f"*32)
            q[key]=True
            self.reject("SIGNED_POLICY_SCOPE_INVALID",
                lambda:m.request_valid(q,NOW,"e"*40))
    def test_false_independent_human_denied(self):
        q=m.prepared_request(ROOT,NOW,nonce="f"*32)
        q["independent_human_review_claimed"]=True
        self.reject("SIGNED_POLICY_SCOPE_INVALID",
            lambda:m.request_valid(q,NOW,"e"*40))
    def test_old_ed25519_key_not_misrepresented(self):
        q=m.prepared_request(ROOT,NOW,nonce="f"*32)
        q["historical_owner_key_signed_this_request"]=True
        self.reject("SIGNED_POLICY_SCOPE_INVALID",
            lambda:m.request_valid(q,NOW,"e"*40))
    def test_unreviewed_source_ref_denied(self):
        q=m.prepared_request(ROOT,NOW,nonce="f"*32)
        q["source_commit"]="d"*40
        self.reject("SIGNED_POLICY_SCOPE_INVALID",
            lambda:m.request_valid(q,NOW,"e"*40))
    def test_expired_short_lived_request_denied(self):
        q=m.prepared_request(ROOT,NOW,nonce="f"*32)
        self.reject("SIGNED_WINDOW_EXPIRED",
            lambda:m.request_valid(q,NOW+timedelta(hours=1),"e"*40))
    def test_extended_signature_window_denied(self):
        q=m.prepared_request(ROOT,NOW,nonce="f"*32)
        q["expires_at"]=m.old.stamp(NOW+timedelta(days=1))
        self.reject("SIGNED_WINDOW_EXPIRED",
            lambda:m.request_valid(q,NOW,"e"*40))
    def test_missing_receipt_denied(self):
        self.reject(None,self.status)
    def test_modified_receipt_denied(self):
        self.ceremony()
        file=self.root/m.RECEIPT_FILE
        r=json.loads(file.read_text())
        r["financial_release_authorized"]=True
        file.write_bytes(m.canonical(r));file.chmod(0o600)
        self.reject("ADOPTED_RECEIPT_SCOPE_INVALID",self.status)
    def test_modified_receipt_signature_denied(self):
        self.ceremony()
        file=self.root/m.RECEIPT_FILE
        r=json.loads(file.read_text())
        r["signed_packet"]["signature_der_b64"]=base64.b64encode(b"a"*70).decode()
        file.write_bytes(m.canonical(r));file.chmod(0o600)
        self.reject("ECDSA_SIGNATURE_ENCODING",self.status)
    def test_missing_public_comment_denied(self):
        self.comment["body"]="EDITED"
        self.reject("PUBLIC_OWNER_KEY_ENROLLMENT_DRIFT",self.ceremony)
    def test_wrong_github_author_denied(self):
        self.comment["user"]["login"]="unknown"
        self.reject("PUBLIC_OWNER_KEY_ENROLLMENT_DRIFT",self.ceremony)
    def test_wrong_issue_comment_reference_denied(self):
        self.comment["issue_url"]="https://github.com/attacker/wolo"
        self.reject("PUBLIC_OWNER_KEY_ENROLLMENT_DRIFT",self.ceremony)
    def test_private_dir_0700_required(self):
        self.root.chmod(0o755)
        self.reject("PRIVATE_DIR_UNSAFE",self.ceremony)
    def test_public_key_file_must_be_0600(self):
        (self.root/m.PUB_FILE).chmod(0o644)
        self.reject("PRIVATE_FILE_UNSAFE",self.ceremony)
    def test_no_funding_io_in_governance_source(self):
        text=(ROOT/m.SOURCE_PY).read_text()
        for token in ("tx bank send","/satchel/v1/returns/execute",
            "ALTER ROLE","systemctl start","--fund","keyring send"):
            self.assertNotIn(token,text)
    def test_signed_receipt_public_body_drift_denied(self):
        self.ceremony()
        self.comment["body"]+=" changed"
        self.reject("PUBLIC_OWNER_KEY_ENROLLMENT_DRIFT",self.status)

if __name__=="__main__":unittest.main()

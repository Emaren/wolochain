"""Physical exact-source and wrong-host negative contracts: NOT production authority."""
from pathlib import Path
import hashlib
import platform
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/settlement_c03_intel_hd_auth_preservation_owner_fence_rehearsal.py"
EXECUTED_SHA256 = "7e5587fa6b619ee224555125e81fb6018c32dd7f6ee183cb8f77c5ae8bca81d5"
C07_SHA256 = "7a8d495b4259c5316f0f38ff060667d6b81f1243f77e1656daf2765da3603305"
RECEIPT_SHA256 = "66297b9531a17c906bcdc8e599714a6d5556571feb45ac4bcb3d8a283dcf21bf"

class C03IntelAuthPreservation(unittest.TestCase):
    def test_original_intel_executed_script_exact(self):
        self.assertEqual(hashlib.sha256(SCRIPT.read_bytes()).hexdigest(), EXECUTED_SHA256)
        text=SCRIPT.read_text()
        self.assertIn(C07_SHA256,text)
        self.assertIn("c03-hd-auth-v2-20261109",text)
        self.assertIn("len(tables)==190",text)
        self.assertIn("len(seqs)==180",text)

    def test_actual_live_functions_and_security_claims_pinned(self):
        text=SCRIPT.read_text()
        for term in (
            "5f9ed5c71d3867b5ce08b8ca70374fc5",
            "7a3fa3a9ff027bec46caf10d92080f3d",
            "0a95ed3ac1676477785d1ecc6adc1a17",
            "RESTORED_AUTH_FUNCTION_BODY_NOT_LIVE_EXACT",
            "aoe2war_auth_owner NOLOGIN NOINHERIT",
            "aoe2war_web_prod LOGIN NOINHERIT",
            "AUTH_OWNER_SEQ_USAGE_RETAINED",
            "AUTH_OWNER_SENSITIVE_NO_UPDATE",
            "AUTH_OWNER_TOKEN_NOT_SELECTABLE",
            "AUTH_WEB_READ_USER_AFTER_OWNER_MIGRATION_FAILED",
            "AUTH_WEB_TOUCH_SESSION_AFTER_OWNER_MIGRATION_FAILED",
            "WEB_DIRECT_WALLET_DML_NOT_DENIED",
            "WEB_DIRECT_USERS_SEQUENCE_NOT_DENIED",
            '"full_chrome_browser_authenticated_continuity_proven":False',
            '"production_c03_fence_complete":False',
            '"funded_activation_authorized":False',
            "SINGLE_SHOT_NO_OVERWRITE",
            "RESTORED_SOURCE_MUST_BE_STOPPED",
            "listen_addresses=''",
        ):
            self.assertIn(term,text,term)

    def test_wrong_architecture_must_fail_before_clone(self):
        if sys.platform=="darwin" and platform.machine()=="x86_64":
            self.skipTest("Do not re-execute consumed one-use Intel live-data source")
        r=subprocess.run([sys.executable,str(SCRIPT)],text=True,capture_output=True,timeout=12,check=False)
        self.assertEqual(r.returncode,3)
        self.assertIn("INTEL_ONLY_UNPRIVILEGED",r.stdout)
        self.assertIn("HOLD_C03_ISOLATED_PRECONNECTED_REHEARSAL",r.stdout)

if __name__=="__main__":
    unittest.main()

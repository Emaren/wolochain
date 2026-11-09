"""Source/identity adversarial checks for C07 exact owner-Intel recovery runner."""
from __future__ import annotations
import hashlib
import importlib.util
from pathlib import Path
import subprocess
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/"scripts/settlement_c07_intel_real_cipher_recovery_rehearsal_hold.py"
SOURCE_SHA="1b1a4412bf2f08e61fd4524472c2a17b8d946f832924c6bc62c1aa387891a3ab"
spec=importlib.util.spec_from_file_location("c07_intel_exact",SOURCE)
module=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=module
spec.loader.exec_module(module)

class IntelC07Boundary(unittest.TestCase):
    def test_physically_executed_source_pin_unchanged(self):
        self.assertEqual(hashlib.sha256(SOURCE.read_bytes()).hexdigest(),SOURCE_SHA)
    def test_only_exact_two_original_real_ciphertext_identities(self):
        self.assertEqual(set(module.PINS),{"aoe2de_db","aoe2hd_db"})
        self.assertEqual(module.PINS["aoe2de_db"]["sha"],
            "6d7b63d94e1e9fcbea07cadc482e1c8914eb90ceb7b31ade19efcd8a580aa4bc")
        self.assertEqual(module.PINS["aoe2hd_db"]["sha"],
            "b011a0a7949199a8b124650f9d16e3280264cca70380a789438fbe4221e504a4")
        self.assertEqual(module.PINS["aoe2de_db"]["bytes"],349608)
        self.assertEqual(module.PINS["aoe2hd_db"]["bytes"],872018705)
        self.assertEqual(module.PINS["aoe2de_db"]["tables"],52)
        self.assertEqual(module.PINS["aoe2hd_db"]["tables"],190)
    def test_never_runs_on_m1_or_unreviewed_db(self):
        if sys.platform=="darwin" and module.platform.machine()=="x86_64":
            self.skipTest("positive physical Intel proof occurs separately")
        for db in ("aoe2de_db","aoe2hd_db"):
            result=subprocess.run([sys.executable,str(SOURCE),
                "--mode","inspect","--db",db],capture_output=True,text=True,timeout=10)
            self.assertEqual(result.returncode,3)
            self.assertIn("HOLD_C07_INTEL_SOURCE_PINNED_RESTORE_FAILED",result.stdout)
        p=subprocess.run([sys.executable,str(SOURCE),
            "--mode","inspect","--db","legacy_8092"],capture_output=True,text=True,timeout=10)
        self.assertNotEqual(p.returncode,0)
    def test_requires_real_age_full_pgdump_restore_not_manifest_only(self):
        s=SOURCE.read_text()
        for essential in ("FileVault is On.","os.getuid()==os.geteuid()!=0",
            '"--exit-on-error"','decrypt.wait(timeout=45)',
            "dec_rc==0","imported.returncode==0",
            "listen_addresses=''","unix_socket_permissions=0700",
            '"PUBLIC_TABLES|"','"PUBLIC_SEQUENCES|"','"TCP_DISABLED|1"',
            '"financial_writer_freeze_proven":False',
            '"c06_gate_closed":False','"c07_gate_closed":False',
            '"funded_canary_authorized":False'):
            self.assertIn(essential,s)
    def test_no_financial_runtime_or_secret_material(self):
        s=SOURCE.read_text()
        for forbidden in ("wolochaind tx","systemctl restart","systemctl start",
            "DROP TABLE","ALTER ROLE","8092","8094",
            "pending_wolo_claims SET","--listen-addresses=0.0.0.0"):
            self.assertNotIn(forbidden,s)
if __name__=="__main__":unittest.main()

"""C03 tested Intel DDL-escape closure proof, never authority to migrate HEL1."""
from pathlib import Path
import hashlib
import platform
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
CASES = (
    ("hd",190,180,39,"c03-hd-ddl-v2-20261109",
     "settlement_c03_intel_hd_fullscope_ddl_owner_fence_rehearsal.py",
     "3686e36ed727085c38a3ddb9f84090bcef16a966ba53518f8d7f07aae7698377",
     "7a8d495b4259c5316f0f38ff060667d6b81f1243f77e1656daf2765da3603305"),
    ("de",52,50,0,"c03-de-ddl-v1-20261109",
     "settlement_c03_intel_de_fullscope_ddl_owner_fence_rehearsal.py",
     "666719253daa37ffaf77012b4ba468b65bf4e61126509e43c599956626c83d79",
     "df21fa2e67319e606a530af501c5b108831178c27fb98c79b31e02bb166a5bb7"),
)

class ExactIntelDDLClosureSource(unittest.TestCase):
    def test_byte_identical_physically_executed_sources_and_restored_receipt_pins(self):
        for name, tables, seqs, funcs, directory, file, sha, recovery_sha in CASES:
            with self.subTest(name=name):
                p=ROOT/"scripts"/file
                self.assertEqual(hashlib.sha256(p.read_bytes()).hexdigest(),sha)
                t=p.read_text()
                self.assertIn(recovery_sha,t)
                self.assertIn(directory,t)
                self.assertIn(f"len(tables)=={tables}",t)
                self.assertIn(f"len(seqs)=={seqs}",t)
                self.assertIn(f"len(funcs)=={funcs}",t)

    def test_fence_tests_database_schema_function_and_preconnected_old_backend(self):
        for name, tables, seqs, funcs, directory, file, sha, recovery_sha in CASES:
            with self.subTest(name=name):
                t=(ROOT/"scripts"/file).read_text()
                for contract in (
                    "SINGLE_SHOT_NO_OVERWRITE",
                    "INTEL_ONLY_UNPRIVILEGED",
                    "REAL_C07_RECOVERY_SHA_DRIFT",
                    "RESTORED_SOURCE_MUST_BE_STOPPED",
                    "listen_addresses=''",
                    "ALTER DATABASE ",
                    "ALTER SCHEMA public OWNER TO ",
                    "ALTER FUNCTION public.",
                    "REVOKE CREATE ON DATABASE ",
                    "REVOKE CREATE ON SCHEMA public ",
                    "PRECONNECTED_LEGACY_DB_SCHEMA_CREATE_NOT_REPRODUCED",
                    "FORMER_LEGACY_CREATE_SURFACE_NOT_FENCED",
                    "PRECONNECTED_TABLE_SEQUENCE_DATABASE_SCHEMA_FUNCTION_DENIAL_NOT_EXACT",
                    "FRESH_RECONNECTED_LEGACY_",
                    "PRECONNECTED_BACKEND_GONE",
                    "C03_PRECONNECTED_PUBLIC_TABLE_DDL_DENIED",
                    "C03_PRECONNECTED_PUBLIC_FUNCTION_DDL_DENIED",
                    "C03_PRECONNECTED_DATABASE_SCHEMA_DDL_DENIED",
                    '"mutations_only_in_disposable_intel_apfs_clone":True',
                    '"production_hd_de_postgres_mutated":False',
                    '"c03_formally_closed":False',
                    '"funded_activation_authorized":False',
                ):
                    self.assertIn(contract,t,contract)
                self.assertNotIn("https://",t)
                self.assertNotIn("http://",t)

    def test_actual_wrong_host_must_refuse_before_any_database_clone(self):
        if sys.platform=="darwin" and platform.machine()=="x86_64":
            self.skipTest("Do not repeat consumed one-shot production-data Intel clone run")
        for name,tables,seqs,funcs,directory,file,sha,recovery_sha in CASES:
            with self.subTest(name=name):
                p=subprocess.run([sys.executable,str(ROOT/"scripts"/file)],
                     text=True,capture_output=True,timeout=12,check=False)
                self.assertEqual(p.returncode,3)
                self.assertIn("INTEL_ONLY_UNPRIVILEGED",p.stdout)
                self.assertIn("HOLD_C03_ISOLATED_PRECONNECTED_REHEARSAL",p.stdout)

if __name__=="__main__":
    unittest.main()

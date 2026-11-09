"""Exact physical source-bound C03 restored-HD APFS clone sandbox regression."""
from pathlib import Path
import hashlib
import importlib.util
import subprocess
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/"scripts/settlement_c03_intel_hd_owner_migration_rehearsal_hold.py"
EXPECTED="c6739f4f2676efacb18cdbf19657f41b8d3fccc77629c31c7ef6ae34d08cf6cb"
spec=importlib.util.spec_from_file_location("c03_hd_clone_exact",SOURCE)
module=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=module
spec.loader.exec_module(module)

class RealHDCloneC03(unittest.TestCase):
    def test_executed_file_hash(self):
        self.assertEqual(hashlib.sha256(SOURCE.read_bytes()).hexdigest(),EXPECTED)
    def test_literal_scope_29_disjoint_finance_tables(self):
        self.assertEqual(len(module.FINANCE),29)
        self.assertEqual(len(set(module.FINANCE)),29)
        self.assertEqual(module.EXP_TABLES,190)
        self.assertEqual(module.EXP_SEQS,180)
        self.assertIn("pending_wolo_claims",module.FINANCE)
        self.assertIn("pending_wolo_claims_repair_backup_20260610",module.FINANCE)
        self.assertIn("wolo_indexed_transfers",module.FINANCE)
        self.assertNotIn("users",module.FINANCE)
    def test_never_runs_on_arm64_m1_linux_or_nonintel(self):
        if sys.platform=="darwin" and module.platform.machine()=="x86_64":
            self.skipTest("positive physical owner transfer is executed on Intel")
        p=subprocess.run([sys.executable,str(SOURCE)],capture_output=True,text=True,timeout=10)
        self.assertEqual(p.returncode,3)
        self.assertIn("HOLD_C03_RESTORED_HD_OWNER_FENCE",p.stdout)
    def test_actual_owner_transition_and_sql_permission_denial(self):
        code=SOURCE.read_text()
        for expected in (
            "FileVault is On.","c03-isolated-hd-writer-rehearsal-20261109",
            "pg_ctl","listen_addresses=''","CREATE ROLE aoe2hd_user LOGIN NOINHERIT",
            "CREATE ROLE aoe2war_finance_owner NOLOGIN NOINHERIT",
            "ALTER TABLE public.","ALTER SEQUENCE public.",
            "GRANT ALL PRIVILEGES ON TABLE public.",
            "REVOKE ALL PRIVILEGES ON TABLE public.",
            "REVOKE ALL PRIVILEGES ON SEQUENCE public.",
            "has_table_privilege('aoe2hd_user'",
            "has_sequence_privilege('aoe2hd_user'",
            "SET LOCAL ROLE aoe2hd_user; DELETE FROM public.pending_wolo_claims WHERE false;",
            "legacy_owner_finance_table_DML_denied",
            "old_owner_users_table_still_writable",
            "production_sql_role_modified",
            "c03_financial_writer_gate_closed",
            "funded_permit_authorized"
        ):
            self.assertIn(expected,code)
    def test_no_prod_or_wallet_secret_mutation(self):
        code=SOURCE.read_text()
        for forbidden in (
            "root@hel1","ssh ","scp ","sudo","runuser -u postgres",
            "systemctl","wolochaind tx","8092","8094","8095",
            "public.users OWNER TO aoe2war_finance_owner",
            "CREATE EXTENSION","TRUNCATE TABLE",
            "security unlock-keychain","--listen-addresses=0.0.0.0",
        ):
            self.assertNotIn(forbidden,code)
if __name__=="__main__":unittest.main()

"""C03 local NOLOGIN finance role partition rehearses denial and rollback."""
import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch

P=Path(__file__).resolve().parents[1]/"scripts/settlement_c03_isolated_nologin_owner_rehearsal.py"
spec=importlib.util.spec_from_file_location("c03_nologin_rehearsal",P)
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

def proofs():
    return {name:True for name in m.TRUE}

class C03FinanceOwnerTests(unittest.TestCase):
    def test_all_nine_assertions_required(self):
        self.assertEqual(len(m.TRUE),9)
        self.assertTrue(m.validate_proof(proofs()))
        for key in m.TRUE:
            sample=proofs()
            sample.pop(key)
            with self.subTest(key=key),self.assertRaises(m.Hold):
                m.validate_proof(sample)

    def test_false_or_integer_one_not_valid(self):
        for key in m.TRUE:
            sample=proofs()
            sample[key]=False
            with self.subTest(key=key),self.assertRaises(m.Hold):
                m.validate_proof(sample)
            sample[key]=1
            with self.subTest(key=key+"INT"),self.assertRaises(m.Hold):
                m.validate_proof(sample)

    def test_unexpected_authorization_key_denied(self):
        sample=proofs()
        sample["financialReleaseAuthorized"]=True
        with self.assertRaisesRegex(m.Hold,"KEY_DRIFT"):
            m.validate_proof(sample)

    def test_no_hel1_source_or_funded_transfer(self):
        raw=P.read_text()
        self.assertNotIn("root@hel1",raw)
        self.assertNotIn("aoe2hd_db",raw)
        self.assertNotIn("aoe2de_db",raw)
        self.assertNotIn("wolochaind",raw)
        self.assertIn("listen_addresses=''",raw)
        self.assertIn("unix_socket_permissions=0700",raw)
        self.assertIn("TemporaryDirectory(",raw)
        self.assertIn("c03_finance_owner NOLOGIN",raw)

    def test_migration_and_rollback_statically_bounded(self):
        raw=P.read_text()
        self.assertIn("ALTER TABLE public.finance_shadow OWNER TO c03_finance_owner",raw)
        self.assertIn("ALTER SEQUENCE public.finance_shadow_id_seq OWNER TO c03_finance_owner",raw)
        self.assertIn("ALTER TABLE public.finance_shadow OWNER TO c03_legacy",raw)
        self.assertIn("ALTER SEQUENCE public.finance_shadow_id_seq OWNER TO c03_legacy",raw)
        self.assertIn("nonfinanceWritesPermitted",raw)

    def test_root_and_nonmac_refused(self):
        with patch.object(m.os,"geteuid",return_value=0):
            with self.assertRaisesRegex(m.Hold,"MAC_NONROOT_REQUIRED"):
                m.main()
        with patch.object(m.sys,"platform","linux"):
            with self.assertRaisesRegex(m.Hold,"MAC_NONROOT_REQUIRED"):
                m.main()

    def test_missing_scratch_refused(self):
        with patch.object(m.Path,"home",return_value=Path("/unlikely/a01-c03-scratch")):
            with self.assertRaises(m.Hold):m.main()

    def test_explicit_hold(self):
        with self.assertRaisesRegex(m.Hold,"EXPECTED_HOLD"):
            m.require(False,"EXPECTED_HOLD")

if __name__=="__main__":
    unittest.main()

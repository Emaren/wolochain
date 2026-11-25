"""C03 physical synthetic NOLOGIN is not a live financial writer fence."""
from __future__ import annotations
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

SRC=Path(__file__).resolve().parents[1]/"scripts/settlement_c03_nologin_existing_backend_rehearsal.py"
spec=importlib.util.spec_from_file_location("c03_existing_session",SRC)
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

def positive():
    return {key:True for key in m.REQUIRED}

class ExistingSessionTests(unittest.TestCase):
    def test_five_specific_invariants(self):
        self.assertEqual(len(m.REQUIRED),5)
        self.assertTrue(m.require_proofs(positive()))

    def test_each_missing_proof_is_a_hold(self):
        for key in m.REQUIRED:
            check=positive()
            check.pop(key)
            with self.subTest(proof=key),self.assertRaisesRegex(ValueError,"PROOF_SHAPE_DRIFT"):
                m.require_proofs(check)

    def test_boolean_int_and_false_do_not_count_as_true(self):
        for key in m.REQUIRED:
            check=positive()
            for wrong in (False,0,1,None,"true"):
                check[key]=wrong
                with self.subTest(proof=key,wrong=str(wrong)),self.assertRaises(ValueError):
                    m.require_proofs(check)

    def test_unknown_extra_proof_is_not_automatically_trusted(self):
        values=positive()
        values['financialReleaseAuthorized']=True
        with self.assertRaisesRegex(ValueError,"PROOF_SHAPE_DRIFT"):
            m.require_proofs(values)

    def test_mac_nonroot_and_private_scratch_only(self):
        with patch.object(m.sys,"platform","linux"):
            with self.assertRaisesRegex(ValueError,"MAC_NONROOT_ONLY"):
                m.main()
        with patch.object(m.os,"geteuid",return_value=0):
            with self.assertRaisesRegex(ValueError,"MAC_NONROOT_ONLY"):
                m.main()
        with patch.object(m,"ROOT",Path("/no-such-c03-probe-path-20261106")):
            with self.assertRaisesRegex(ValueError,"MAC_NONROOT_ONLY"):
                m.main()

    def test_exact_one_backend_termination_not_aggregate_predicate(self):
        s=SRC.read_text()
        self.assertIn("pid <> pg_backend_pid()",s)
        self.assertIn("SELECT pg_terminate_backend("+chr(34),s)
        self.assertNotIn("AND pg_terminate_backend(pid)",s)
        self.assertIn("if not target.isdecimal()",s)
        self.assertIn("EXACT_BACKEND_TERMINATE_UNPROVEN",s)

    def test_no_real_database_or_production_hosts(self):
        raw=SRC.read_text()
        for forbidden in ("root@hel1","aoe2hd_db","aoe2de_db","wolochaind","8094","8095","private_key"):
            self.assertNotIn(forbidden,raw)
        self.assertIn("listen_addresses=''",raw)
        self.assertIn("unix_socket_permissions=0700",raw)
        self.assertIn("TemporaryDirectory(",raw)
        self.assertIn("productionDatabaseTouched",raw)
        self.assertIn("financialPermitIssued",raw)

    def test_distinct_live_and_new_login_denials(self):
        for required in (
            "existingLegacySessionStillWritesAfterNoLogin",
            "newLegacyConnectionDenied",
            "terminatedLegacyBackendCannotCommit",
            "independentPublicRoleKeepsReading",
            "roleLoginReinstatementRestoresWrites",
        ):
            self.assertIn(required,m.REQUIRED)

if __name__=="__main__":
    unittest.main()

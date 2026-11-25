"""C03 isolated lock counterexample source is never a writer-freeze permit."""
import importlib.util
import os
from pathlib import Path
import stat
import unittest
from unittest.mock import patch

P=Path(__file__).resolve().parents[1]/"scripts"/"settlement_c03_isolated_lock_counterexample.py"
spec=importlib.util.spec_from_file_location("c03_lock_counterexample",P)
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

def proof():
    return {**{key:True for key in m.REQUIRED_TRUE},
            **{key:False for key in m.REQUIRED_FALSE}}

class C03CounterexampleTests(unittest.TestCase):
    def test_expected_nonquiescence_is_successful_counterexample(self):
        self.assertTrue(m.validate_counterexample(proof()))
        self.assertFalse(proof()["globalFinanceQuiescenceProven"])
        self.assertFalse(proof()["ownedSequenceWritingDenied"])

    def test_missing_or_extra_observation_fails(self):
        x=proof()
        x.pop("shareModeLockAcquired")
        with self.assertRaisesRegex(m.Hold,"SCOPE_DRIFT"):
            m.validate_counterexample(x)
        y=proof()
        y["financialReleaseAuthorized"]=True
        with self.assertRaisesRegex(m.Hold,"SCOPE_DRIFT"):
            m.validate_counterexample(y)

    def test_all_true_booleans_mandatory(self):
        for key in m.REQUIRED_TRUE:
            x=proof()
            x[key]=False
            with self.subTest(key=key),self.assertRaises(m.Hold):
                m.validate_counterexample(x)

    def test_all_false_booleans_mandatory(self):
        for key in m.REQUIRED_FALSE:
            x=proof()
            x[key]=True
            with self.subTest(key=key),self.assertRaises(m.Hold):
                m.validate_counterexample(x)

    def test_integer_one_or_zero_never_masquerades_as_bool(self):
        for key in m.REQUIRED_TRUE|m.REQUIRED_FALSE:
            x=proof()
            x[key]=1 if key in m.REQUIRED_TRUE else 0
            with self.subTest(key=key),self.assertRaises(m.Hold):
                m.validate_counterexample(x)

    def test_source_has_no_hel1_live_db_or_network_target(self):
        raw=P.read_text()
        self.assertNotIn("root@hel1",raw)
        self.assertNotIn("aoe2hd_db",raw)
        self.assertNotIn("aoe2de_db",raw)
        self.assertIn("listen_addresses=''",raw)
        self.assertIn("unix_socket_permissions=0700",raw)
        self.assertIn("TemporaryDirectory(",raw)
        self.assertIn("APPROVED_BINARY_DIR",raw)

    def test_root_is_fail_closed_before_startup(self):
        with patch.object(m.os,"geteuid",return_value=0):
            with self.assertRaisesRegex(m.Hold,"NONROOT_MAC_REQUIRED"):
                m.main()

    def test_wrong_platform_is_fail_closed(self):
        with patch.object(m.sys,"platform","linux"):
            with self.assertRaisesRegex(m.Hold,"NONROOT_MAC_REQUIRED"):
                m.main()

    def test_hold_precondition_is_explicit(self):
        with self.assertRaisesRegex(m.Hold,"EXPECTED_DENIAL"):
            m.must(False,"EXPECTED_DENIAL")

if __name__=="__main__":
    unittest.main()

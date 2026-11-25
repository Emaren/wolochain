"""C01 real native negative start is a HOLD, never an activation claim."""
from __future__ import annotations

import importlib.util
from pathlib import Path
from unittest.mock import patch
import json
import unittest
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/"scripts"))
SOURCE=ROOT/"scripts/settlement_c01_native_unfunded_denial_hold.py"
spec=importlib.util.spec_from_file_location("c01_native_denial",SOURCE)
c01=importlib.util.module_from_spec(spec)
spec.loader.exec_module(c01)


def rows():
    return [{"program":n,"actual_unfunded_nonroot_check":True,
             "expected_fixed_config_refusal":True,"native_exit":2,
             "pinned_binary_sha256":s["sha"],"sensitive_output_captured":False}
            for n,s in c01.PROGRAMS.items()]


class NegativeAdmit(unittest.TestCase):
    def setUp(self):
        self.samples=rows()

    def classify(self):
        return c01.classify(self.samples,ports_before=True,ports_after=True)

    def test_all_native_denials_still_financial_hold(self):
        o=self.classify()
        self.assertEqual(o["status"],"HOLD")
        self.assertEqual(o["exact_source_binary_checks"],2)
        self.assertFalse(o["c01_physically_admitted"])
        self.assertFalse(o["financial_release_authorized"])
        self.assertFalse(o["independent_reviewer_admitted"])
        self.assertFalse(o["financial_database_fenced"])
        self.assertFalse(o["production_mutated"])
        self.assertNotIn("token",json.dumps(o).lower())

    def test_new_listener_appears_before(self):
        with self.assertRaisesRegex(c01.Stop,"C01_FINANCIAL_LISTENER_APPEARED"):
            c01.classify(self.samples,ports_before=False,ports_after=True)

    def test_new_listener_appears_after(self):
        with self.assertRaisesRegex(c01.Stop,"C01_FINANCIAL_LISTENER_APPEARED"):
            c01.classify(self.samples,ports_before=True,ports_after=False)

    def test_missing_nonroot_reviewer(self):
        self.samples.pop()
        with self.assertRaisesRegex(c01.Stop,"C01_NATIVE_COVERAGE_INCOMPLETE"):
            self.classify()

    def test_duplicate_same_program_cannot_impersonate_reviewer(self):
        self.samples[1]=dict(self.samples[0])
        with self.assertRaisesRegex(c01.Stop,"C01_NATIVE_COVERAGE_INCOMPLETE"):
            self.classify()

    def test_unexpected_payout_authorization_field_is_rejected(self):
        self.samples[0]["financial_release_authorized"]=True
        with self.assertRaisesRegex(c01.Stop,"C01_NATIVE_ROW_INVALID"):
            self.classify()

    def test_false_nonroot_check_is_rejected(self):
        self.samples[0]["actual_unfunded_nonroot_check"]=False
        with self.assertRaisesRegex(c01.Stop,"C01_NATIVE_CUSTODY_DENIAL_NOT_PROVEN"):
            self.classify()

    def test_false_is_not_exit_2(self):
        self.samples[0]["native_exit"]=True
        with self.assertRaisesRegex(c01.Stop,"C01_NATIVE_CUSTODY_DENIAL_NOT_PROVEN"):
            self.classify()

    def test_zero_exit_is_not_denial(self):
        self.samples[0]["native_exit"]=0
        with self.assertRaisesRegex(c01.Stop,"C01_NATIVE_CUSTODY_DENIAL_NOT_PROVEN"):
            self.classify()

    def test_changed_binary_sha_refused(self):
        self.samples[0]["pinned_binary_sha256"]="0"*64
        with self.assertRaisesRegex(c01.Stop,"C01_NATIVE_CUSTODY_DENIAL_NOT_PROVEN"):
            self.classify()

    def test_sensitive_output_never_marked_captured(self):
        self.samples[0]["sensitive_output_captured"]=True
        with self.assertRaisesRegex(c01.Stop,"C01_NATIVE_CUSTODY_DENIAL_NOT_PROVEN"):
            self.classify()

    def test_missing_config_diagnostic_cannot_be_confused_with_permit(self):
        class Run:
            returncode=2
            stdout=b""
            stderr=b"satchel: HELD independent activation permit unavailable"
        with patch.object(c01,"command",return_value=Run):
            with patch.object(c01,"verify_binary"):
                with patch.object(c01,"account_for_user") as role:
                    role.return_value.pw_uid=988
                    with patch.object(c01.Path,"exists",return_value=False):
                        with patch.object(c01.Path,"is_symlink",return_value=False):
                            with self.assertRaisesRegex(c01.Stop,"C01_NATIVE_DENIAL_DIAGNOSTIC_CHANGED"):
                                c01.denied("wolosatcheld",c01.PROGRAMS["wolosatcheld"])

    def test_nonroot_identity_drift_detected(self):
        with patch.object(c01,"account_for_user") as role:
            role.return_value.pw_uid=0
            with patch.object(c01.Path,"exists",return_value=False):
                with patch.object(c01.Path,"is_symlink",return_value=False):
                    with self.assertRaisesRegex(c01.Stop,"C01_NATIVE_SERVICE_IDENTITY_DRIFT"):
                        c01.denied("wolosatcheld",c01.PROGRAMS["wolosatcheld"])

    def test_profiles_not_generated(self):
        code=SOURCE.read_text()
        self.assertIn('not p.exists()',code)
        self.assertIn('runuser',code)
        self.assertNotIn("os.system(",code)
        self.assertNotIn("subprocess.Popen(",code)
        self.assertNotIn("ssh-keygen",code)
        self.assertNotIn("send-tx",code)

    def test_no_funded_mode_accepted(self):
        with patch.object(c01.os,"geteuid",return_value=0):
            self.assertEqual(c01.main(["--fund"]),2)
        with patch.object(c01.os,"geteuid",return_value=1000):
            self.assertEqual(c01.main(["--inspect"]),2)

    def test_fixed_source_program_pins_distinct(self):
        self.assertEqual(set(c01.PROGRAMS),{"wolosatcheld","woloreviewerd"})
        self.assertEqual(len({v["sha"] for v in c01.PROGRAMS.values()}),2)
        self.assertEqual(len({v["uid"] for v in c01.PROGRAMS.values()}),2)
        self.assertEqual(len({v["file"] for v in c01.PROGRAMS.values()}),2)


if __name__=="__main__":
    unittest.main()

#!/usr/bin/env python3
"""Regression suite: auxiliary producer metadata is never a payment release permit."""
from __future__ import annotations
from pathlib import Path
import importlib.util
import json
import os
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

SCRIPT=Path(__file__).resolve().parents[1]/"scripts"/"settlement_auxiliary_producer_surfaces.py"
SPEC=importlib.util.spec_from_file_location("settlement_auxiliary_producer_surfaces",SCRIPT)
assert SPEC and SPEC.loader
A=importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name]=A
SPEC.loader.exec_module(A)


class AuxiliaryProducerTests(unittest.TestCase):
    def test_cron_counts_without_printing_commands_or_secret_env(self):
        lines=[
            "# Wolo funding is commented", "",
            "WOLO_MNEMONIC=never-output-this-secret",
            "PATH=/usr/bin", "*/5 * * * * /usr/bin/true",
            "0 0 * * * /usr/bin/python3 /private/staking-payout.py --secret=DO_NOT_ECHO",
            "@reboot /usr/local/bin/check",
        ]
        r=A.cron_count(lines)
        self.assertEqual(r["jobLinesObserved"],3)
        self.assertEqual(r["financialKeywordLines"],1)
        self.assertEqual(r["jobsWhoseFinancialAuthorityIsExcluded"],0)
        self.assertTrue(r["requiresHumanClassification"])
        self.assertNotIn("DO_NOT_ECHO",str(r))
        self.assertNotIn("never-output-this-secret",str(r))

    def test_symlink_cron_path_is_not_trusted(self):
        with tempfile.TemporaryDirectory() as d:
            secret=Path(d)/"secret-crontab"
            secret.write_text("* * * * * /bin/echo SECRET_STRING\n")
            symlink=Path(d)/"symlink"
            symlink.symlink_to(secret)
            with self.assertRaises(OSError):
                A.safe_file_lines(symlink)
            real=A.cron_count(A.safe_file_lines(secret))
            self.assertEqual(real["jobLinesObserved"],1)
            self.assertNotIn("SECRET_STRING",json.dumps(real))

    def test_unit_parser_requires_identifiable_unit_and_known_activity(self):
        x=A.unit_names(
            "user@0.service loaded active running User Manager for UID 0\n"
            "user@1000.service loaded active running User Manager for UID 1000\n")
        self.assertEqual(x,[("user@0.service",True),("user@1000.service",True)])
        with self.assertRaises(A.InventoryError):
            A.unit_names("user@1000.service loaded ??? status\n")
        with self.assertRaises(A.InventoryError):
            A.unit_names("bad/../../path.timer loaded active waiting Alias\n")
        with self.assertRaises(A.InventoryError):
            A.unit_names("user@1000.service loaded active running X\n"
                         "user@1000.service loaded active running X\n")

    def test_root_and_tony_user_managers_names_only_and_inaccessible_is_unknown(self):
        class User: pw_name="tony"
        def mocked_command(args, **kw):
            if args[0] == "systemctl":
                return (0,"user@1000.service loaded active running User\n")
            if args[0]=="runuser":
                self.assertEqual(args[2],"tony")
                self.assertEqual(args[3],"--")
                self.assertNotIn("sh",args)
                return (0,"payment-watch.timer loaded active waiting X\n"
                          "payment-watch.service loaded inactive dead Y\n")
            self.fail(f"unknown command {args}")
        with patch.object(A,"command",side_effect=mocked_command), \
             patch.object(A.pwd,"getpwuid",return_value=User()):
            r=A.user_managers()
        self.assertEqual(r[0]["uid"],1000)
        self.assertEqual(r[0]["activeUserTimers"],["payment-watch.timer"])
        self.assertIs(r[0]["financialWriterExcluded"],False)

        with patch.object(A,"command",side_effect=lambda args, **kw:
                          (0,"user@1000.service loaded active running X\n")
                          if args[0]=="systemctl" else (127,"")), \
             patch.object(A.pwd,"getpwuid",return_value=User()):
            missing=A.user_managers()
        self.assertEqual(missing[0]["status"],"NOT_INSPECTED")
        self.assertFalse(missing[0]["financialWriterExcluded"])

    def test_container_restart_policy_is_not_financial_exclusion(self):
        def mock_command(args,**kw):
            if args[1]=="ps":
                return 0,"historical-hasura\n"
            if args[1]=="inspect":
                self.assertIn("HostConfig.RestartPolicy.Name",args[3])
                return 0,"always\n"
            self.fail(f"unexpected args {args}")
        with patch.object(A,"command",side_effect=mock_command):
            out=A.container_inventory("docker")
        self.assertEqual(out["status"],"OBSERVED_ONLY")
        self.assertEqual(out["names"],[{"name":"historical-hasura",
                                       "restartConfigured":True,
                                       "potentialFinancialWriter":True}])
        self.assertFalse(out["containerEnvOrMountsInspected"])

        with patch.object(A,"command",return_value=(127,"")):
            absent=A.container_inventory("podman")
        self.assertEqual(absent["status"],"ENGINE_UNAVAILABLE")
        self.assertFalse(absent["restartPolicyObserved"])

    def test_forged_duplicate_names_and_inspection_error_fail_closed(self):
        with patch.object(A,"command",return_value=(0,"a\n" * 2)):
            with self.assertRaises(A.InventoryError):
                A.container_inventory("docker")
        with patch.object(A,"command",return_value=(0,"../../unsafe\n")):
            with self.assertRaises(A.InventoryError):
                A.container_inventory("docker")
        with patch.object(A,"command",return_value=(4,"")):
            r=A.container_inventory("docker")
        self.assertEqual(r["status"],"NOT_INSPECTED")

    def test_no_mutation_and_no_success_exit(self):
        report={
            "schema":"wolo.financial.auxiliary-producer-surfaces.v1",
            "status":"HOLD","financialReleaseAuthorized":False,
            "financialIngressFenced":False,"satchelActivationAuthorized":False,
            "productionMutated":False,
        }
        with patch.object(A,"inspect",return_value=report),patch("builtins.print"):
            self.assertEqual(A.main(["--inspect"]),3)
        with patch("builtins.print"):
            self.assertEqual(A.main(["--apply"]),2)
        with patch.object(A,"inspect",side_effect=A.InventoryError("UNCERTAIN")), \
             patch("builtins.print"):
            self.assertEqual(A.main(["--inspect"]),2)


if __name__=="__main__":
    unittest.main()

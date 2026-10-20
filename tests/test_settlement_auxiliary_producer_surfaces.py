#!/usr/bin/env python3
"""Regression suite: auxiliary producer metadata is never a payment release permit."""
from __future__ import annotations
from pathlib import Path
import importlib.util
import io
import json
from contextlib import redirect_stdout
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

    def test_all_spool_users_and_periodic_scripts_observed_without_secret_leaks(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            etc=root/"etc"
            spool=root/"var"/"spool"/"cron"
            users=spool/"crontabs"
            daily=etc/"cron.daily"
            hourly=etc/"cron.hourly"
            for p in (etc,users,daily,hourly):
                p.mkdir(parents=True,exist_ok=True)
            (etc/"crontab").write_text(
                "# root cron\n*/5 * * * * root /bin/true # PRIVATE_MAIN\n")
            (etc/"anacrontab").write_text(
                "1 5 cron.daily run-parts /etc/cron.daily # PRIVATE_ANACRON\n")
            (users/"alice").write_text(
                "WOLO_SECRET=KEEP_PRIVATE\n0 * * * * /private/send-wallet # PRIVATE_ALICE\n")
            (users/"bob").write_text(
                "0 2 * * * /private/ordinary # PRIVATE_BOB\n")
            (spool/"legacyuser").write_text(
                "0 4 * * * /private/another # PRIVATE_LEGACY\n")
            script=daily/"payment-run"
            script.write_text("#!/bin/sh\necho PRIVATE_SCRIPT_BODY\n")
            script.chmod(0o755)
            (hourly/".placeholder").write_text("PRIVATE_PLACEHOLDER")
            with patch.object(A,"command",return_value=(0,
                        "12  Wed Oct 21 13:10:00 2026 root PRIVATE_AT\n")):
                observed=A.cron_sources(
                    etc,(users,spool),
                )
            self.assertEqual(observed["spoolCrontabsObserved"],3)
            self.assertEqual(observed["totalJobLines"],5)
            self.assertEqual(observed["filesObserved"],5)
            self.assertEqual(observed["periodic"]["filesObserved"],2)
            self.assertEqual(observed["periodic"]["runPartsNameAndExecutableCandidates"],1)
            self.assertEqual(observed["atQueue"]["pendingJobs"],1)
            self.assertIn("cron.daily",observed["periodic"]["directoriesObserved"])
            self.assertFalse(observed["allFinancialWritersIdentified"])
            self.assertFalse(observed["otherSpoolAndNonstandardCronSourcesExcluded"])
            for secret in ("WOLO_SECRET","KEEP_PRIVATE","PRIVATE_MAIN",
                           "PRIVATE_ANACRON","PRIVATE_ALICE","PRIVATE_BOB",
                           "PRIVATE_LEGACY","PRIVATE_SCRIPT_BODY","PRIVATE_AT"):
                self.assertNotIn(secret,json.dumps(observed))

    def test_missing_cron_roots_never_prove_scheduler_absence(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            with patch.object(A,"command",return_value=(127,"")):
                observed=A.cron_sources(root/"etc", (
                    root/"var"/"spool"/"cron"/"crontabs",
                    root/"var"/"spool"/"cron",
                ))
            self.assertEqual(observed["spoolDirectoriesObserved"],[])
            self.assertEqual(observed["spoolDirectoriesMissingOrUnverified"],
                             ["crontabs","cron"])
            self.assertEqual(observed["periodic"]["directoriesObserved"],[])
            self.assertEqual(len(observed["periodic"]["directoriesMissingOrUnverified"]),5)
            self.assertEqual(observed["atQueue"]["status"],"UNOBSERVED")
            self.assertIsNone(observed["atQueue"]["pendingJobs"])
            self.assertFalse(observed["allFinancialWritersIdentified"])

    def test_ubuntu_at_spool_directories_are_known_but_financially_unverified(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            etc = root / "etc"
            parent = root / "var" / "spool" / "cron"
            users = parent / "crontabs"
            atjobs = parent / "atjobs"
            atspool = parent / "atspool"
            for folder in (etc, users, atjobs, atspool):
                folder.mkdir(parents=True, exist_ok=True)
            (users / "tony").write_text("0 * * * * /bin/true # PRIVATE_CRON_COMMAND\\n")
            # These intentionally do not meet CRON_FILE: at payloads are NOT
            # crontabs, and their names/contents must not enter any output.
            (atjobs / "SECRET_JOB_\t").write_text("PRIVATE_AT_JOB_PAYLOAD")
            (atspool / "SECRET_OUTPUT_\t").write_text("PRIVATE_AT_SPOOL_PAYLOAD")
            with patch.object(A, "command", return_value=(0, "1 Tue 2026 PRIVATE_ATQ\\n")):
                result = A.cron_sources(etc, (users, parent))
            self.assertEqual(result["spoolCrontabsObserved"], 1)
            self.assertEqual(result["totalJobLines"], 1)
            self.assertEqual(result["atSpoolDirectoriesObserved"],
                             ["atjobs", "atspool"])
            self.assertEqual(result["atSpoolDirectoriesMissingOrUnverified"], [])
            self.assertFalse(result["atSpoolJobPayloadsInspected"])
            self.assertFalse(result["atSpoolFinancialWriterCapabilityExcluded"])
            self.assertEqual(result["atQueue"]["pendingJobs"], 1)
            self.assertFalse(result["allFinancialWritersIdentified"])
            serialized = json.dumps(result)
            for secret in ("PRIVATE_CRON_COMMAND", "PRIVATE_AT_JOB_PAYLOAD",
                           "PRIVATE_AT_SPOOL_PAYLOAD", "PRIVATE_ATQ",
                           "SECRET_JOB", "SECRET_OUTPUT"):
                self.assertNotIn(secret, serialized)

    def test_at_queue_unavailable_or_spool_absent_never_proves_zero_writers(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            etc = root / "etc"
            users = root / "cron" / "crontabs"
            users.mkdir(parents=True)
            with patch.object(A, "command", return_value=(127, "")):
                result = A.cron_sources(etc, (users, users.parent))
            self.assertEqual(result["atSpoolDirectoriesObserved"], [])
            self.assertEqual(result["atSpoolDirectoriesMissingOrUnverified"],
                             ["atjobs", "atspool"])
            self.assertEqual(result["atQueue"]["status"], "UNOBSERVED")
            self.assertIsNone(result["atQueue"]["pendingJobs"])
            self.assertFalse(result["atSpoolFinancialWriterCapabilityExcluded"])

    def test_fake_or_symlinked_at_directories_and_unknown_nested_entries_fail(self):
        for name in ("atjobs", "atspool"):
            for bad in ("symlink", "ordinary-file", "unknown-dir"):
                with self.subTest(name=name, bad=bad), tempfile.TemporaryDirectory() as d:
                    root = Path(d)
                    etc = root / "etc"
                    parent = root / "cron"
                    users = parent / "crontabs"
                    users.mkdir(parents=True)
                    (parent / "atjobs").mkdir()
                    (parent / "atspool").mkdir()
                    target = parent / name
                    if bad == "symlink":
                        target.rmdir()
                        target.symlink_to(users, target_is_directory=True)
                    elif bad == "ordinary-file":
                        target.rmdir()
                        target.write_text("not-a-directory")
                    else:
                        (parent / "unrelated-service").mkdir()
                    with patch.object(A, "command", return_value=(127, "")):
                        with self.assertRaises(A.InventoryError) as caught:
                            A.cron_sources(etc, (users, parent))
                    self.assertEqual(str(caught.exception), "UNSAFE_SCHEDULER_ENTRY")

    def test_unknown_nested_cron_source_and_links_refuse_coverage(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            etc=root/"etc";etc.mkdir()
            sp=root/"cron";sp.mkdir()
            source=sp/"otheruser"
            source.write_text("* * * * * /usr/bin/true\n")
            other=sp/"evil-directory"
            other.mkdir()
            with patch.object(A,"command",return_value=(127,"")):
                with self.assertRaises(A.InventoryError):
                    A.cron_sources(etc,(sp,))
            other.rmdir()
            evil=sp/"link"
            evil.symlink_to(source)
            with patch.object(A,"command",return_value=(127,"")):
                with self.assertRaises(A.InventoryError):
                    A.cron_sources(etc,(sp,))
            evil.unlink()
            (etc/"cron.daily").symlink_to(sp,target_is_directory=True)
            with patch.object(A,"command",return_value=(127,"")):
                with self.assertRaises(A.InventoryError):
                    A.cron_sources(etc,(sp,))

    def test_at_queue_is_an_observation_not_finance_exclusion(self):
        with patch.object(A,"command",return_value=(0,
                "1 Tue Oct 20 2026 a PRIVATE_WALLET\n"
                "2 Tue Oct 20 2026 b PRIVATE_PASSWORD\n")):
            q=A._at_queue()
        self.assertEqual(q,{"status":"OBSERVED_ONLY","pendingJobs":2,
                            "financialWriterCapabilityExcluded":False})
        self.assertNotIn("PRIVATE_WALLET",json.dumps(q))
        with patch.object(A,"command",return_value=(126,"inaccessible")):
            q=A._at_queue()
        self.assertEqual(q["status"],"UNOBSERVED")
        self.assertFalse(q["financialWriterCapabilityExcluded"])

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

    def test_wrong_host_is_explicit_stop_before_any_linux_inventory(self):
        output=io.StringIO()
        with (patch.object(A.sys,"platform","darwin"),
              patch.object(A,"inspect",side_effect=AssertionError(
                  "Must not inspect operator Mac")),
              redirect_stdout(output)):
            self.assertEqual(A.main(["--inspect"]),2)
        result=json.loads(output.getvalue())
        self.assertEqual(result["status"],"STOP")
        self.assertEqual(result["reason"],"WRONG_HOST_LINUX_REQUIRED")
        self.assertFalse(result["financialReleaseAuthorized"])
        self.assertFalse(result["satchelActivationAuthorized"])
        self.assertFalse(result["productionMutated"])
        self.assertNotIn("username",output.getvalue())
        self.assertNotIn("hostName",output.getvalue())

    def test_failure_codes_identify_critical_stage_without_secret_strings(self):
        sample = {
            "CRON": "UNSAFE_SCHEDULER_ENTRY",
            "USER_SYSTEMD": "SYSTEM_USER_MANAGERS_UNOBSERVED",
            "DOCKER": "UNSAFE_CONTAINER_LIST",
            "PODMAN": "TOO_MUCH_COMMAND_OUTPUT",
        }
        for stage, code in sample.items():
            with self.subTest(stage=stage):
                output = io.StringIO()
                with (patch.object(A.sys, "platform", "linux"),
                      patch.object(A, "inspect",
                                   side_effect=A.StagedInventoryError(stage, code)),
                      redirect_stdout(output)):
                    self.assertEqual(A.main(["--inspect"]), 2)
                result = json.loads(output.getvalue())
                self.assertEqual(result["status"], "STOP")
                self.assertEqual(result["failureStage"], stage)
                self.assertEqual(result["failureCode"], code)
                self.assertFalse(result["financialReleaseAuthorized"])
                self.assertFalse(result["satchelActivationAuthorized"])
                self.assertFalse(result["productionMutated"])

    def test_unknown_inventory_error_cannot_exfiltrate_file_path_or_secret(self):
        secret = "SECRET_WALLET_MNEMONIC_NEVER_PRINT_ME"
        def bad():
            raise A.InventoryError(secret)
        with self.assertRaises(A.StagedInventoryError) as caught:
            A.observed_section("CRON", bad)
        self.assertEqual(caught.exception.stage, "CRON")
        self.assertEqual(caught.exception.code, "INVENTORY_EXCEPTION_REDACTED")
        self.assertNotIn(secret, str(caught.exception))
        with self.assertRaises(A.StagedInventoryError) as caught:
            A.observed_section("DOCKER", lambda: (_ for _ in ()).throw(
                OSError("/home/tony/private/" + secret)))
        self.assertEqual(caught.exception.code, "HOST_INTERFACE_UNOBSERVED")
        self.assertNotIn(secret, str(caught.exception))
        with self.assertRaises(A.InventoryError):
            A.observed_section("WRONG_STAGE", bad)

    def test_real_inspection_pipeline_attributes_cron_failure_before_later_queries(self):
        out = io.StringIO()
        with (patch.object(A.sys, "platform", "linux"),
              patch.object(A, "cron_sources",
                           side_effect=A.InventoryError("UNSAFE_SCHEDULER_DIRECTORY")),
              patch.object(A, "user_managers",
                           side_effect=AssertionError("later scan must not run")),
              redirect_stdout(out)):
            self.assertEqual(A.main(["--inspect"]), 2)
        result = json.loads(out.getvalue())
        self.assertEqual(result["failureStage"], "CRON")
        self.assertEqual(result["failureCode"], "UNSAFE_SCHEDULER_DIRECTORY")
        self.assertFalse(result["financialReleaseAuthorized"])

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

"""Adversarial tests for read-only 18-unit pre-resume identity sealing.

All systemd calls and file reads are mocked; no production units or secrets used.
"""
import importlib.util
import io
import json
from contextlib import ExitStack, redirect_stdout
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import settlement_financial_maintenance as m

spec = importlib.util.spec_from_file_location(
    "settlement_resume_producer_identities",
    ROOT / "scripts" / "settlement_resume_producer_identities.py")
identity = importlib.util.module_from_spec(spec)
spec.loader.exec_module(identity)


class ProducerIdentityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.app = "demo-api.service"
        self.once = "demo-finance.service"
        self.timer = "demo-finance.timer"
        self.units = (self.app, self.once, self.timer)
        self.active = {self.app: "active", self.once: "inactive", self.timer: "active"}
        self.gated = False
        self.secret_revision = 0
        self.reads = 0
        self.runtime_revision = 0
        self.command_revision = 0
        self.drift_at = None
        self.invalid_env = False
        self.omit_service_mainpid = False
        self.omit_service_execstart = False
        self.omit_timer_fragment = False
        self.timer_service_field = False
        self.extra_service_optional_field = False
        self.files = {u: Path(self.tmp.name) / (u + ".gate") for u in self.units}
        for name, value in (
            ("UNITS", self.units), ("APPS", (self.app,)),
            ("ONESHOTS", (self.once,)), ("TIMERS", (self.timer,)),
            ("HOLD", Path(self.tmp.name) / "HOLD")
        ):
            p = patch.object(m, name, value)
            p.start()
            self.addCleanup(p.stop)
        self.original_gate_bytes = m.expected_dropin()
        for name, value in (
            ("no_jobs", lambda runner: None),
            ("scope_digest", lambda: "a" * 64),
            ("dropin", lambda unit: self.files[unit]),
            ("show", self.show),
            ("private_read", self.private_read),
        ):
            p = patch.object(m, name, value)
            p.start()
            self.addCleanup(p.stop)

    def properties(self, unit):
        # Exactly mirror observed hel1 omissions: timers expose only common
        # unit properties; optional service commands are absent when unset.
        p = {"Id": unit, "FragmentPath": "/etc/systemd/system/" + unit,
             "ActiveState": self.active[unit],
             "DropInPaths": str(self.files[unit]) if self.gated else ""}
        if unit != self.timer:
            p.update({
                "MainPID": "100" if self.active[unit] == "active" and
                                     unit == self.app else "0",
                "ExecStart": "{ path=/opt/demo; argv[]=/opt/demo ; }",
                "Environment": "API_TOKEN=DO_NOT_LEAK_THIS_SECRET",
                "User": "root",
            })
            if unit == self.app:
                p["EnvironmentFiles"] = "/etc/demo.env (ignore_errors=no)"
                if self.invalid_env:
                    p["EnvironmentFiles"] = '"/etc/file name" (ignore_errors=yes)'
            if self.extra_service_optional_field:
                p["ExecStartPre"] = "{ path=/opt/preflight; argv[]=/opt/preflight ; }"
            if self.omit_service_mainpid:
                p.pop("MainPID")
            if self.omit_service_execstart:
                p.pop("ExecStart")
        elif self.timer_service_field:
            p["ExecStart"] = "{ path=/opt/unexpected ; }"
        if unit == self.timer and self.omit_timer_fragment:
            p.pop("FragmentPath")
        return p

    def show(self, unit, runner):
        p = self.properties(unit)
        return {key: p[key] for key in ("Id", "FragmentPath", "DropInPaths",
                                       "ActiveState", "MainPID") if key in p}

    def runner(self, args):
        if args[0] == "busctl":
            if "LoadUnit" in args:
                return json.dumps({"type":"o","data":["/org/freedesktop/systemd1/unit/fixture"]})
            field = args[-1]
            argv = ["/opt/demo", str(self.command_revision)]
            return json.dumps({"type":"a(sasbttttuii)","data":[
                ["/opt/demo",argv,False,self.runtime_revision,0,0,0,100,0,0]]})
        self.assertEqual(args[:3], ["systemctl", "--no-pager", "show"])
        self.assertEqual(args[4], "--")
        p = self.properties(args[5])
        return "\n".join(key + "=" + p[key] for key in identity.CONFIG_PROPERTIES
                         if key in p)

    def private_read(self, path, source=False):
        self.assertTrue(source)
        self.reads += 1
        if self.drift_at is not None and self.reads > self.drift_at:
            self.secret_revision = 1
        if path in self.files.values():
            return self.original_gate_bytes
        return ("secret byte revision " + str(self.secret_revision)).encode()

    def capture(self):
        return identity.collect_producer_identities(runner=self.runner)

    def test_two_stable_samples_and_zero_authority(self):
        packet = self.capture()
        self.assertEqual(set(packet["units"]), set(self.units))
        self.assertFalse(packet["resume_authorized"])
        self.assertFalse(packet["financial_release_authorized"])
        self.assertFalse(packet["units"][self.once]["originally_active"])
        self.assertTrue(packet["units"][self.app]["originally_active"])
        self.assertNotIn("DO_NOT_LEAK_THIS_SECRET", repr(packet))
        report = identity.verify_producer_identities(packet, runner=self.runner)
        self.assertEqual(report["originally_active_apps"], [self.app])
        self.assertEqual(report["originally_active_timers"], [self.timer])
        self.assertFalse(report["resume_authorized"])

    def test_real_hel1_timer_and_unset_service_fields(self):
        self.assertNotIn("MainPID", self.properties(self.timer))
        self.assertNotIn("ExecStart", self.properties(self.timer))
        self.assertNotIn("EnvironmentFiles", self.properties(self.once))
        self.assertNotIn("ExecStartPost", self.properties(self.app))
        capture = self.capture()
        self.assertEqual(set(capture["units"]), set(self.units))
        self.assertFalse(capture["financial_release_authorized"])

    def test_native_execution_runtime_counters_do_not_become_configuration(self):
        packet = self.capture()
        self.runtime_revision = 123456
        identity.verify_producer_identities(packet, runner=self.runner)
        self.command_revision = 1
        with self.assertRaisesRegex(m.MaintenanceError, "PRODUCER_CONFIGURATION_DRIFT"):
            identity.verify_producer_identities(packet, runner=self.runner)

    def test_native_repeated_execution_and_envfile_properties_preserve_order(self):
        props = self.properties(self.app)
        first = "EnvironmentFiles=/etc/first.env (ignore_errors=no)"
        second = "EnvironmentFiles=/etc/second.env (ignore_errors=no)"
        cmd1 = "ExecStartPre={ path=/opt/check-one; argv[]=/opt/check-one ; }"
        cmd2 = "ExecStartPre={ path=/opt/check-two; argv[]=/opt/check-two ; }"
        raw = "\n".join(k+"="+v for k,v in props.items() if k!="EnvironmentFiles")
        raw += "\n"+first+"\n"+second+"\n"+cmd1+"\n"+cmd2
        fields = identity.read_properties(self.app, lambda _: raw)
        self.assertEqual(fields["EnvironmentFiles"], [first.partition("=")[2], second.partition("=")[2]])
        self.assertEqual(fields["ExecStartPre"], [cmd1.partition("=")[2], cmd2.partition("=")[2]])
        self.assertEqual(identity.env_file_paths(fields["EnvironmentFiles"]), ["/etc/first.env", "/etc/second.env"])

    def test_duplicate_singular_properties_are_still_invalid(self):
        raw = "\n".join(k+"="+v for k,v in self.properties(self.app).items())
        with self.assertRaisesRegex(m.MaintenanceError, "PRODUCER_PROPERTIES_INVALID"):
            identity.read_properties(self.app, lambda _: raw+"\nActiveState=inactive")

    def test_missing_required_service_mainpid_refused(self):
        self.omit_service_mainpid = True
        with self.assertRaisesRegex(m.MaintenanceError, "PRODUCER_PROPERTIES_INCOMPLETE"):
            self.capture()

    def test_missing_required_service_execstart_refused(self):
        self.omit_service_execstart = True
        with self.assertRaisesRegex(m.MaintenanceError, "PRODUCER_PROPERTIES_INCOMPLETE"):
            self.capture()

    def test_missing_required_timer_fragment_refused(self):
        self.omit_timer_fragment = True
        with self.assertRaisesRegex(m.MaintenanceError, "PRODUCER_PROPERTIES_INCOMPLETE"):
            self.capture()

    def test_unexpected_timer_execution_property_refused(self):
        self.timer_service_field = True
        with self.assertRaisesRegex(m.MaintenanceError, "UNEXPECTED_TIMER_EXECUTION_PROPERTY"):
            self.capture()

    def test_optional_service_property_added_after_capture_is_drift(self):
        packet = self.capture()
        self.extra_service_optional_field = True
        with self.assertRaisesRegex(m.MaintenanceError, "PRODUCER_CONFIGURATION_DRIFT"):
            identity.verify_producer_identities(packet, runner=self.runner)

    def test_root_only_inspection_of_complete_scope_no_financial_authority(self):
        apps = tuple(f"demo-app-{i}.service" for i in range(4))
        once = tuple(f"demo-task-{i}.service" for i in range(7))
        timers = tuple(f"demo-task-{i}.timer" for i in range(7))
        units = apps + once + timers
        packet = {
            "schema": identity.SCHEMA,
            "scope_sha256": m.scope_digest(),
            "units": {u: {"configuration_sha256": "a" * 64,
                          "originally_active": u in apps + timers}
                      for u in units},
            "resume_authorized": False,
            "financial_release_authorized": False,
        }
        with ExitStack() as stack:
            for name, value in (("UNITS", units), ("APPS", apps),
                                ("ONESHOTS", once), ("TIMERS", timers)):
                stack.enter_context(patch.object(m, name, value))
            stack.enter_context(patch.object(identity.os, "geteuid", return_value=0))
            stack.enter_context(patch.object(identity, "collect_producer_identities",
                                             return_value=packet))
            result = identity.inspect_readonly(runner=self.runner)
            self.assertEqual(result["status"], "IDENTITIES_OBSERVED_ONLY")
            self.assertEqual(result["units"], 18)
            self.assertEqual((result["active_apps"], result["active_timers"],
                              result["inactive_oneshots"]), (4, 7, 7))
            self.assertFalse(result["signed_capture"])
            self.assertFalse(result["global_writers_fenced"])
            self.assertFalse(result["resume_authorized"])
            self.assertFalse(result["financial_release_authorized"])
            self.assertEqual(result["identity_observation_sha256"],
                             identity.sha(m.canonical(packet)))
            packet["units"][timers[0]]["originally_active"] = False
            with self.assertRaisesRegex(m.MaintenanceError,
                                        "PRODUCER_PRESTATE_CHANGED_NOT_SAFE_TO_ASSUME"):
                identity.inspect_readonly(runner=self.runner)

    def test_nonroot_inspect_refuses_before_reading_sensitive_sources(self):
        with (patch.object(identity.os, "geteuid", return_value=1000),
              patch.object(identity, "collect_producer_identities") as collect):
            with self.assertRaisesRegex(m.MaintenanceError,
                                        "ROOT_REQUIRED_FOR_PRIVATE_SOURCE_OBSERVATION"):
                identity.inspect_readonly(runner=self.runner)
            collect.assert_not_called()

    def test_cli_refuses_inputs_and_redacts_underlying_errors(self):
        for args, error, expected in (
            (["identity.py", "--enroll"], None, "NO_USER_INPUTS_ACCEPTED"),
            (["identity.py"], RuntimeError("LEAK_MY_PRIVATE_ENV_PATH_AND_KEY"),
             "INSPECT_REFUSED_RuntimeError"),
        ):
            with self.subTest(args=args), patch.object(identity.sys, "argv", args):
                buf = io.StringIO()
                with redirect_stdout(buf):
                    with patch.object(identity, "inspect_readonly",
                                      side_effect=error) as inspector:
                        status = identity._main()
                result = json.loads(buf.getvalue())
                self.assertIn(result["reason"], (expected,))
                self.assertFalse(result["financial_release_authorized"])
                self.assertNotIn("LEAK_MY_PRIVATE_ENV_PATH_AND_KEY", buf.getvalue())
                self.assertNotEqual(status, 0)

    def test_stale_capture_receipt_fails_closed(self):
        packet = self.capture()
        packet["units"][self.timer].pop("configuration_sha256")
        with self.assertRaisesRegex(m.MaintenanceError, "RESUME_CAPTURE_IDENTITIES_MISSING"):
            identity.verify_producer_identities(packet, runner=self.runner)
        self.assertFalse(packet["resume_authorized"])

    def test_replaced_environment_bytes_refused(self):
        packet = self.capture()
        self.secret_revision = 1
        with self.assertRaisesRegex(m.MaintenanceError, "PRODUCER_CONFIGURATION_DRIFT"):
            identity.verify_producer_identities(packet, runner=self.runner)

    def test_mid_capture_rotation_refused(self):
        self.drift_at = len(self.units) + 1
        with self.assertRaisesRegex(m.MaintenanceError, "PRODUCER_IDENTITIES_CHANGED_DURING_CAPTURE"):
            self.capture()

    def test_active_oneshot_refused(self):
        self.active[self.once] = "active"
        with self.assertRaisesRegex(m.MaintenanceError, "ACTIVE_OR_UNSTABLE_ONESHOT_REFUSED"):
            self.capture()

    def test_invalid_environment_file_syntax_refused(self):
        self.invalid_env = True
        with self.assertRaisesRegex(m.MaintenanceError, "UNPARSEABLE_PRODUCER_ENVIRONMENT_FILES"):
            self.capture()

    def test_owned_gate_requires_exact_content(self):
        baseline = self.capture()
        self.gated = True
        report = identity.verify_producer_identities(
            baseline, runner=self.runner, allow_owned_gate=True)
        self.assertFalse(report["financial_release_authorized"])
        # Gate ownership missing means no resume, even if all other files match.
        with patch.object(m, "expected_dropin", return_value=b"mismatched"):
            with self.assertRaisesRegex(m.MaintenanceError, "OWNED_GATE_CHANGED_OR_MISSING"):
                identity.verify_producer_identities(
                    baseline, runner=self.runner, allow_owned_gate=True)
        with self.assertRaisesRegex(m.MaintenanceError, "EXISTING_GATE_CANNOT_BE_PRESTATE"):
            self.capture()


if __name__ == "__main__":
    unittest.main()

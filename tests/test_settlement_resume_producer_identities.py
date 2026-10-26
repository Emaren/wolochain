"""Adversarial tests for read-only 18-unit pre-resume identity sealing.

All systemd calls and file reads are mocked; no production units or secrets used.
"""
import importlib.util
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
        self.drift_at = None
        self.invalid_env = False
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
        p = {name: "" for name in identity.CONFIG_PROPERTIES}
        p.update({"Id": unit, "FragmentPath": "/etc/systemd/system/" + unit,
                  "ActiveState": self.active[unit],
                  "MainPID": "100" if self.active[unit] == "active" and unit == self.app else "0",
                  "DropInPaths": str(self.files[unit]) if self.gated else "",
                  "EnvironmentFiles": ("/etc/demo.env (ignore_errors=no)"
                                       if unit == self.app else ""),
                  "Environment": "API_TOKEN=DO_NOT_LEAK_THIS_SECRET",
                  "ExecStart": "{ path=/opt/demo; argv[]=/opt/demo ; }",
                  "Restart": ""})
        if self.invalid_env and unit == self.app:
            p["EnvironmentFiles"] = '"/etc/file name" (ignore_errors=yes)'
        return p

    def show(self, unit, runner):
        p = self.properties(unit)
        return {key: p[key] for key in ("Id", "FragmentPath", "DropInPaths",
                                       "ActiveState", "MainPID")}

    def runner(self, args):
        self.assertEqual(args[:3], ["systemctl", "--no-pager", "show"])
        self.assertEqual(args[4], "--")
        p = self.properties(args[5])
        return "\n".join(key + "=" + p[key] for key in identity.CONFIG_PROPERTIES)

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

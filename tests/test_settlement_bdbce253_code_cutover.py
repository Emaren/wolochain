"""Offline fault-injection contracts for EXACT two-service code switch.

No real systemd, Wolo files, RPC, fund movements, or home directory changes.
Mocks the only permitted service/filesystem operations at the Live boundary.
"""
from __future__ import annotations

from dataclasses import dataclass
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "settlement-bdbce253-code-cutover.py"


def load():
    spec = importlib.util.spec_from_file_location("wolo_code_cutover_test_only", SCRIPT)
    obj = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = obj
    spec.loader.exec_module(obj)
    return obj


@dataclass
class Unit:
    running: bool = True
    exe: str = ""
    pid: int = 0


class FakeLive:
    def __init__(self, source):
        self.s = source
        self.units = {
            source.PRIMARY: Unit(True, source.OLD, 1012),
            source.FOUNDER: Unit(True, source.OLD, 1010),
            source.CONSENSUS: Unit(True, source.NODE, 1009),
        }
        self.dropins = {n: "old" for n in source.SERVICES}
        self.loaded = dict(self.dropins)
        self.commands = []
        self.fail_once = None
        self.requests = {"primary": b"accepted:stable-tx", "founder": b"claim:889:pending"}
        self.original_requests = dict(self.requests)

    def failure(self, key):
        if self.fail_once == key:
            self.fail_once = None
            raise RuntimeError("injected " + key)

    def check_binary(self, path, expected):
        self.failure("check_binary")
        valid = {self.s.OLD: self.s.OLD_SHA, self.s.NEW: self.s.NEW_SHA,
                 self.s.NODE: self.s.NODE_SHA}
        assert valid.get(path) == expected

    def show(self, unit, field):
        u = self.units[unit]
        if field == "MainPID":
            return str(u.pid if u.running else 0)
        if field == "ActiveState":
            return "active" if u.running else "inactive"
        if field == "FragmentPath":
            return "/etc/systemd/system/" + unit
        if field == "DropInPaths":
            return str(self.dropin(unit)) if self.loaded[unit] == "new" else ""
        raise AssertionError("unreviewed field " + field)

    def exe(self, pid):
        return next(u.exe for u in self.units.values() if u.pid == pid and u.running)

    def file_sha(self, path):
        pid = int(path.split("/")[2])
        exe = self.exe(pid)
        return {self.s.OLD: self.s.OLD_SHA, self.s.NEW: self.s.NEW_SHA,
                self.s.NODE: self.s.NODE_SHA}[exe]

    def dropin(self, unit):
        assert unit in self.s.SERVICES
        return Path(f"/etc/systemd/system/{unit}.d/{self.s.OVERRIDE}")

    def check_unit_fragment(self, unit):
        assert unit in self.s.SERVICES
        self.failure("fragment:" + unit)

    def read_dropin(self, unit):
        return self.dropins[unit]

    def add_dropin(self, unit):
        self.failure("add:" + unit)
        assert self.dropins[unit] == "old"
        self.commands.append("add:" + unit)
        self.dropins[unit] = "new"

    def remove_dropin(self, unit):
        self.failure("remove:" + unit)
        assert self.dropins[unit] == "new"
        self.commands.append("remove:" + unit)
        self.dropins[unit] = "old"

    def systemctl(self, action, unit=None):
        self.failure(action + ":" + (unit or "all"))
        assert action in ("stop", "start", "daemon-reload")
        assert unit in self.s.SERVICES or unit is None and action == "daemon-reload"
        self.commands.append(f"{action}:{unit or 'all'}")
        if action == "daemon-reload":
            self.loaded = dict(self.dropins)
            return
        u = self.units[unit]
        if action == "stop":
            u.running = False
        else:
            u.running = True
            u.exe = self.s.NEW if self.loaded[unit] == "new" else self.s.OLD
            u.pid += 30

    def health(self, port):
        self.failure("health:" + str(port))
        assert port in (8092, 8093)
        unit = self.s.PRIMARY if port == 8092 else self.s.FOUNDER
        assert self.units[unit].running

    def assert_no_node_or_ledger_change(self):
        assert self.units[self.s.CONSENSUS].pid == 1009
        assert self.units[self.s.CONSENSUS].exe == self.s.NODE
        assert self.units[self.s.CONSENSUS].running
        assert all(self.s.CONSENSUS not in cmd for cmd in self.commands)
        assert self.requests == self.original_requests


class GuardedTwoServiceCutover(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.s = load()

    def test_python_syntax(self):
        subprocess.run([sys.executable, "-m", "py_compile", str(SCRIPT)],
                       check=True, capture_output=True)

    def test_exact_two_service_live_allowlist(self):
        s = self.s
        self.assertEqual(s.SERVICES, (s.PRIMARY, s.FOUNDER))
        with self.assertRaisesRegex(s.Blocked, "consensus service mutation"):
            # Do not construct Live on real services.
            s.Live.systemctl(s.Live(), "stop", s.CONSENSUS)
        with self.assertRaisesRegex(s.Blocked, "unreviewed"):
            s.Live.systemctl(s.Live(), "stop", "aoe2hdbets-web.service")

    def test_normal_code_switch_and_approved_code_only_rollback(self):
        s = self.s
        fake = FakeLive(s)
        ctl = s.Cutover(fake)
        self.assertEqual(ctl.inspect(), "old")
        self.assertEqual(ctl.promote(), "new")
        self.assertEqual(ctl.inspect(), "new")
        self.assertEqual(fake.dropins[s.PRIMARY], "new")
        self.assertEqual(fake.dropins[s.FOUNDER], "new")
        ctl.code_only_recover(1009)
        self.assertEqual(ctl.inspect(), "old")
        fake.assert_no_node_or_ledger_change()

    def test_fault_after_every_side_effect_rolls_back_code_not_money(self):
        s = self.s
        failures = [
            "stop:" + s.PRIMARY, "stop:" + s.FOUNDER,
            "add:" + s.PRIMARY, "add:" + s.FOUNDER,
            "daemon-reload:all",
            "start:" + s.PRIMARY, "start:" + s.FOUNDER,
            "health:8092", "health:8093",
        ]
        for point in failures:
            with self.subTest(point=point):
                fake = FakeLive(s)
                fake.fail_once = point
                with self.assertRaisesRegex(RuntimeError, "injected"):
                    s.Cutover(fake).promote()
                self.assertEqual(s.Cutover(fake).inspect(), "old")
                fake.assert_no_node_or_ledger_change()

    def test_crash_after_stop_without_written_override_can_recover(self):
        s = self.s
        fake = FakeLive(s)
        for unit in s.SERVICES:
            fake.systemctl("stop", unit)
        self.assertEqual(s.Cutover(fake).state(allow_partial=True), "old")
        s.Cutover(fake).code_only_recover(1009)
        self.assertEqual(s.Cutover(fake).inspect(), "old")
        fake.assert_no_node_or_ledger_change()

    def test_crash_after_first_written_override_before_reload_recovers(self):
        s = self.s
        fake = FakeLive(s)
        for unit in s.SERVICES:
            fake.systemctl("stop", unit)
        fake.add_dropin(s.PRIMARY)
        self.assertEqual(s.Cutover(fake).state(allow_partial=True), "partial")
        s.Cutover(fake).code_only_recover(1009)
        self.assertEqual(s.Cutover(fake).inspect(), "old")
        fake.assert_no_node_or_ledger_change()

    def test_foreign_override_and_node_drift_block(self):
        s = self.s
        fake = FakeLive(s)
        fake.loaded[s.PRIMARY] = "new"
        with self.assertRaisesRegex(s.Blocked, "unsynchronized"):
            s.Cutover(fake).inspect()
        fake.loaded[s.PRIMARY] = "old"
        fake.units[s.CONSENSUS].exe = "evil"
        with self.assertRaises(s.Blocked):
            s.Cutover(fake).promote()
        fake.assert_no_node_or_ledger_change = lambda: None
        self.assertFalse(fake.commands)

    def test_mutation_from_cli_needs_operator_permit(self):
        for mode in ("promote", "rollback", "recover-interrupted"):
            with self.subTest(mode=mode):
                # Run no root as well: either root or absent permit denies.
                proc = subprocess.run(
                    [sys.executable, str(SCRIPT), "--mode", mode],
                    capture_output=True, text=True, timeout=5, check=False,
                )
                self.assertEqual(proc.returncode, 2)
                self.assertIn("BLOCKED:", proc.stderr)

    def test_permit_syntax_is_exact_and_requires_root_and_freshness(self):
        s = self.s
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "permit.json"
            p.write_text(json.dumps({"approved": True}))
            with self.assertRaisesRegex(s.Blocked, "root:root"):
                s.load_release_permit(p)
            p.chmod(0o600)
            # CI user is not root; fake protected stat without mutating host.
            st = p.stat()
            class FakeStat:
                st_uid = 0
                st_gid = 0
                st_mode = 0o100600
                st_size = st.st_size
            original = Path.stat
            def fake_stat(obj, *a, **kw):
                return FakeStat() if obj == p else original(obj, *a, **kw)
            with patch.object(Path, "stat", new=fake_stat):
                with self.assertRaisesRegex(s.Blocked, "fields missing"):
                    s.load_release_permit(p)

    def test_no_automatic_app_writer_resume_or_any_consensus_mutation(self):
        src = SCRIPT.read_text()
        self.assertNotIn("systemctl restart", src)
        self.assertNotIn("pg_restore", src)
        self.assertNotIn("shutil.copytree", src)
        self.assertIn("PAYOUT_PRODUCERS_STILL_FENCED_REQUIRED=true", src)
        self.assertIn("NO_PAYOUT_PRODUCER_RESUME=true", src)


if __name__ == "__main__":
    unittest.main()

"""Offline fault-injection contracts for EXACT two-service code switch.

No real systemd, Wolo files, RPC, fund movements, or home directory changes.
Mocks the only permitted service/filesystem operations at the Live boundary.
"""
from __future__ import annotations

from dataclasses import dataclass
import importlib.util
import contextlib
import io
import json
import re
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import URLError

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
        ctl = s.Cutover(fake, authorize=lambda: None)
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
                    s.Cutover(fake, authorize=lambda: None).promote()
                self.assertEqual(s.Cutover(fake, authorize=lambda: None).inspect(), "old")
                fake.assert_no_node_or_ledger_change()

    def test_first_transient_connection_refusal_waits_then_succeeds(self):
        # systemd-active can precede the localhost listener binding.
        s = self.s
        fake = FakeLive(s)
        actual_health = fake.health
        seen = {"refusals": 0}

        def delayed(port):
            if port == 8092 and fake.dropins[s.PRIMARY] == "new" and seen["refusals"] == 0:
                seen["refusals"] += 1
                raise URLError(ConnectionRefusedError("listener still binding"))
            return actual_health(port)

        fake.health = delayed
        with patch.object(s, "STARTUP_HEALTH_POLL_SECONDS", 0):
            self.assertEqual(s.Cutover(fake, authorize=lambda: None).promote(), "new")
        self.assertEqual(seen["refusals"], 1)
        self.assertTrue(all(fake.dropins[u] == "new" for u in s.SERVICES))
        fake.assert_no_node_or_ledger_change()

    def test_persistent_transport_fault_has_bounded_wait_and_rolls_back(self):
        s = self.s
        fake = FakeLive(s)
        healthy = fake.health

        def unavailable(port):
            if fake.dropins[s.PRIMARY] == "new":
                raise URLError(ConnectionRefusedError("refused"))
            return healthy(port)

        fake.health = unavailable
        with patch.object(s, "STARTUP_HEALTH_GRACE_SECONDS", 0):
            with self.assertRaisesRegex(s.Blocked, "bounded health deadline"):
                s.Cutover(fake, authorize=lambda: None).promote()
        self.assertEqual(s.Cutover(fake, authorize=lambda: None).inspect(), "old")
        fake.assert_no_node_or_ledger_change()

    def test_semantic_health_failure_fails_immediately_not_retried(self):
        s = self.s
        fake = FakeLive(s)
        healthy = fake.health
        errors = []

        def wrong_chain(port):
            if fake.dropins[s.PRIMARY] == "new":
                errors.append(port)
                raise s.Blocked("settlement lane chain/health mismatch")
            return healthy(port)

        fake.health = wrong_chain
        with self.assertRaisesRegex(s.Blocked, "chain/health mismatch"):
            s.Cutover(fake, authorize=lambda: None).promote()
        self.assertEqual(errors, [8092])
        self.assertEqual(s.Cutover(fake, authorize=lambda: None).inspect(), "old")
        fake.assert_no_node_or_ledger_change()

    def test_crash_after_stop_without_written_override_can_recover(self):
        s = self.s
        fake = FakeLive(s)
        for unit in s.SERVICES:
            fake.systemctl("stop", unit)
        self.assertEqual(s.Cutover(fake, authorize=lambda: None).state(allow_partial=True), "old")
        s.Cutover(fake, authorize=lambda: None).code_only_recover(1009)
        self.assertEqual(s.Cutover(fake, authorize=lambda: None).inspect(), "old")
        fake.assert_no_node_or_ledger_change()

    def test_crash_after_first_written_override_before_reload_recovers(self):
        s = self.s
        fake = FakeLive(s)
        for unit in s.SERVICES:
            fake.systemctl("stop", unit)
        fake.add_dropin(s.PRIMARY)
        self.assertEqual(s.Cutover(fake, authorize=lambda: None).state(allow_partial=True), "partial")
        s.Cutover(fake, authorize=lambda: None).code_only_recover(1009)
        self.assertEqual(s.Cutover(fake, authorize=lambda: None).inspect(), "old")
        fake.assert_no_node_or_ledger_change()

    def test_foreign_override_and_node_drift_block(self):
        s = self.s
        fake = FakeLive(s)
        fake.loaded[s.PRIMARY] = "new"
        with self.assertRaisesRegex(s.Blocked, "unsynchronized"):
            s.Cutover(fake, authorize=lambda: None).inspect()
        fake.loaded[s.PRIMARY] = "old"
        fake.units[s.CONSENSUS].exe = "evil"
        with self.assertRaises(s.Blocked):
            s.Cutover(fake, authorize=lambda: None).promote()
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
            # Protected ownership is simulated on the exact fixture FD; the
            # source validator never trusts a separate path stat for reading.
            helper = ReleasePermitAcquisition()
            helper.s = s
            with helper.protected(p):
                with self.assertRaisesRegex(s.Blocked, "fields missing"):
                    s.load_release_permit(p)

    def test_no_automatic_app_writer_resume_or_any_consensus_mutation(self):
        src = SCRIPT.read_text()
        self.assertNotIn("systemctl restart", src)
        self.assertNotIn("pg_restore", src)
        self.assertNotIn("shutil.copytree", src)
        self.assertIn("PAYOUT_PRODUCERS_STILL_FENCED_REQUIRED=true", src)
        self.assertIn("NO_PAYOUT_PRODUCER_RESUME=true", src)


class ReleasePermitAcquisition(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.s = load()

    def document(self, now=None):
        s = self.s
        now = now or s.datetime.now(s.timezone.utc)
        return {"schema": "aoe2war.wolochain.two-settlement-code-only.v1",
                "candidateRevision": s.REV, "candidateSha256": s.NEW_SHA,
                "operator": "reviewed-operator", "approval": s.EXACT_APPROVAL,
                "witnessedControls": sorted(s.ATTESTED),
                "issuedAtUtc": (now - s.timedelta(minutes=1)).isoformat(),
                "expiresAtUtc": (now + s.timedelta(seconds=1)).isoformat()}

    @contextlib.contextmanager
    def protected(self, path):
        # Simulate protected root ownership on the exact opened fixture inode;
        # no chown, host privilege, production file or real permit is needed.
        import types
        s = self.s
        path.chmod(0o600)
        original_path_stat, original_fstat = Path.stat, s.os.fstat
        initial = original_path_stat(path)
        def root_metadata(st):
            fields = ("st_dev", "st_ino", "st_mode", "st_size", "st_mtime_ns", "st_ctime_ns", "st_nlink")
            return types.SimpleNamespace(**{key:getattr(st, key) for key in fields}, st_uid=0, st_gid=0)
        def path_stat(obj, *args, **kwargs):
            st = original_path_stat(obj, *args, **kwargs)
            return root_metadata(st) if obj == path else st
        def fd_stat(fd):
            st = original_fstat(fd)
            return root_metadata(st) if (st.st_dev, st.st_ino) == (initial.st_dev, initial.st_ino) else st
        with patch.object(Path, "stat", new=path_stat), patch.object(s.os, "fstat", side_effect=fd_stat):
            yield

    def test_default_clock_is_sampled_after_actual_permit_io(self):
        s = self.s
        real_datetime = s.datetime
        clock = {"now": real_datetime.now(s.timezone.utc)}
        class Clock:
            fromisoformat = staticmethod(real_datetime.fromisoformat)
            @staticmethod
            def now(_tz):
                return clock["now"]
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "permit.json"
            p.write_text(json.dumps(self.document(clock["now"])))
            after = clock["now"] + s.timedelta(seconds=2)
            path_read, fd_read = Path.read_bytes, s.os.read
            def delayed_path(obj):
                data = path_read(obj)
                clock["now"] = after
                return data
            def delayed_fd(fd, limit):
                data = fd_read(fd, limit)
                clock["now"] = after
                return data
            with self.protected(p), patch.object(s, "datetime", Clock), \
                 patch.object(Path, "read_bytes", new=delayed_path), patch.object(s.os, "read", side_effect=delayed_fd):
                with self.assertRaisesRegex(s.Blocked, "expired"):
                    s.load_release_permit(p)

    def test_duplicate_json_fields_cannot_become_operator_approval(self):
        s = self.s
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "permit.json"
            raw = json.dumps(self.document())
            p.write_text(raw.replace('"operator": "reviewed-operator"', '"operator": "different-operator", "operator": "reviewed-operator"'))
            with self.protected(p), self.assertRaisesRegex(s.Blocked, "duplicate"):
                s.load_release_permit(p)

    def test_unsafe_opened_descriptor_metadata_is_refused(self):
        import types
        s = self.s
        for change in ({"st_uid": 1}, {"st_gid": 1}, {"st_mode": 0o100640},
                       {"st_mode": 0o010600}, {"st_size": 8192}):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as td:
                p = Path(td) / "permit.json"
                p.write_text(json.dumps(self.document()))
                with self.protected(p):
                    prior = s.os.fstat
                    def unsafe(fd):
                        st = prior(fd)
                        return types.SimpleNamespace(**{**vars(st), **change})
                    with patch.object(s.os, "fstat", side_effect=unsafe), self.assertRaises(s.Blocked):
                        s.load_release_permit(p)

    def test_path_swap_cannot_read_a_replacement_symlink_target(self):
        s = self.s
        with tempfile.TemporaryDirectory() as td:
            p, other = Path(td) / "permit.json", Path(td) / "unapproved.json"
            p.write_text(json.dumps(self.document()))
            other.write_text(json.dumps({**self.document(), "operator": "unapproved-operator"}))
            open_fd, path_read = s.os.open, Path.read_bytes
            swapped = False
            def swap():
                nonlocal swapped
                if not swapped:
                    p.rename(Path(td) / "original.json")
                    p.symlink_to(other)
                    swapped = True
            def replaced_read(obj):
                swap()
                return path_read(obj)
            def replaced_open(path, *args, **kwargs):
                fd = open_fd(path, *args, **kwargs)
                if str(path) == str(p):
                    swap()
                return fd
            with self.protected(p), patch.object(Path, "read_bytes", new=replaced_read), \
                 patch.object(s.os, "open", side_effect=replaced_open), self.assertRaises(s.Blocked):
                s.load_release_permit(p)

    def test_growth_after_metadata_check_is_bounded_and_refused(self):
        s = self.s
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "permit.json"
            p.write_text(json.dumps(self.document()))
            path_read, fd_read = Path.read_bytes, s.os.read
            grew, limits = False, []
            def grow():
                nonlocal grew
                if not grew:
                    with p.open("ab") as stream:
                        stream.write(b" " * 9000)
                    grew = True
            def growing_path(obj):
                grow()
                return path_read(obj)
            def growing_fd(fd, limit):
                limits.append(limit)
                grow()
                return fd_read(fd, limit)
            with self.protected(p), patch.object(Path, "read_bytes", new=growing_path), \
                 patch.object(s.os, "read", side_effect=growing_fd), self.assertRaises(s.Blocked):
                s.load_release_permit(p)
            self.assertTrue(limits)
            self.assertLessEqual(sum(limits), 8192)

    def test_permit_descriptor_closes_on_read_metadata_and_parse_errors(self):
        import types
        s = self.s
        for failure in ("read", "metadata", "parse"):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as td:
                p = Path(td) / "permit.json"
                raw = json.dumps(self.document())
                if failure == "parse":
                    raw = raw.replace('"operator": "reviewed-operator"', '"operator": "first", "operator": "reviewed-operator"')
                p.write_text(raw)
                opened, closed = [], []
                original_open, original_close, original_fstat = s.os.open, s.os.close, s.os.fstat
                def opening(*args, **kwargs):
                    fd = original_open(*args, **kwargs)
                    opened.append(fd)
                    return fd
                def closing(fd):
                    closed.append(fd)
                    original_close(fd)
                with self.protected(p), patch.object(s.os, "open", side_effect=opening), \
                     patch.object(s.os, "close", side_effect=closing), contextlib.ExitStack() as stack:
                    if failure == "read":
                        stack.enter_context(patch.object(s.os, "read", side_effect=OSError("fixture read error")))
                    if failure == "metadata":
                        protected_stat = s.os.fstat
                        def unsafe(fd):
                            return types.SimpleNamespace(**{**vars(protected_stat(fd)), "st_uid": 1})
                        stack.enter_context(patch.object(s.os, "fstat", side_effect=unsafe))
                    with self.assertRaises(s.Blocked):
                        s.load_release_permit(p)
                self.assertEqual(opened, closed)
                self.assertEqual(len(opened), 1)
                with self.assertRaises(OSError):
                    original_fstat(opened[0])

    def test_deeply_nested_malformed_json_returns_typed_refusal(self):
        s = self.s
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "permit.json"
            p.write_text('{"nested":' + '[' * 1500 + '0' + ']' * 1500 + '}')
            with self.protected(p), self.assertRaises(s.Blocked):
                s.load_release_permit(p)
            # Python JSON implementations have different native nesting
            # limits. Exercise the recursion-refusal path deterministically.
            with self.protected(p), patch.object(s.json, "loads", side_effect=RecursionError("fixture nesting limit")), \
                 self.assertRaisesRegex(s.Blocked, "invalid release permit JSON"):
                s.load_release_permit(p)

    def test_explicit_now_fixture_still_validates_the_same_public_shape(self):
        s = self.s
        now = s.datetime(2026, 10, 18, tzinfo=s.timezone.utc)
        doc = self.document(now)
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "permit.json"
            p.write_text(json.dumps(doc))
            with self.protected(p):
                self.assertEqual(s.load_release_permit(p, now=now), doc)


class ReleasePermitFreshness(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.s = load()

    def run_promote(self, fake, state, *, mode="promote"):
        s = self.s
        original = {"operator": "reviewed-operator", "expiresAtUtc": "original-expiry"}
        def read(_path):
            state["checks"] += 1
            if state.get("expired"):
                raise s.Blocked("expired release permit")
            if state.get("revoked"):
                raise FileNotFoundError("revoked fixture permit")
            if state.get("changed"):
                return {**original, "operator": "different-operator"}
            return dict(original)
        @contextlib.contextmanager
        def locked():
            if state.get("expire_at_lock"):
                state["expired"] = True
            yield
        stderr = io.StringIO()
        with patch.object(s.os, "geteuid", return_value=0), \
             patch.object(s, "Live", return_value=fake), \
             patch.object(s, "load_release_permit", side_effect=read), \
             patch.object(s, "acquire_mutation_lock", side_effect=locked), \
             patch.object(sys, "argv", [str(SCRIPT), "--mode", mode, "--permit", "/fixture/permit"]), \
             contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(stderr):
            result = s.main()
        return result, stderr.getvalue()

    def test_expiry_during_slow_preflight_means_zero_mutations(self):
        s = self.s
        fake = FakeLive(s)
        state = {"checks": 0}
        health = fake.health
        def preflight(port):
            health(port)
            state["expired"] = True
        fake.health = preflight
        result, _ = self.run_promote(fake, state)
        self.assertEqual(result, 2)
        self.assertEqual(fake.commands, [])
        fake.assert_no_node_or_ledger_change()

    def test_expiry_between_forward_steps_only_completes_old_code_recovery(self):
        s = self.s
        for point in ("stop:" + s.PRIMARY, "stop:" + s.FOUNDER,
                      "add:" + s.PRIMARY, "add:" + s.FOUNDER,
                      "daemon-reload:all", "start:" + s.PRIMARY):
            with self.subTest(point=point):
                fake = FakeLive(s)
                state = {"checks": 0}
                systemctl, add = fake.systemctl, fake.add_dropin
                new_starts_after_expiry = []
                def control(action, unit=None):
                    if state.get("expired") and action == "start" and fake.loaded[unit] == "new":
                        new_starts_after_expiry.append(unit)
                    systemctl(action, unit)
                    if action + ":" + (unit or "all") == point:
                        state["expired"] = True
                def override(unit):
                    add(unit)
                    if "add:" + unit == point:
                        state["expired"] = True
                fake.systemctl, fake.add_dropin = control, override
                result, _ = self.run_promote(fake, state)
                self.assertEqual(result, 2)
                self.assertEqual(new_starts_after_expiry, [])
                self.assertTrue(all(fake.dropins[unit] == "old" and fake.loaded[unit] == "old" for unit in s.SERVICES))
                self.assertTrue(all(fake.units[unit].running and fake.units[unit].exe == s.OLD for unit in s.SERVICES))
                fake.assert_no_node_or_ledger_change()

    def test_changed_or_revoked_permit_after_first_mutation_cannot_continue_rollout(self):
        s = self.s
        for failure in ("changed", "revoked"):
            with self.subTest(failure=failure):
                fake = FakeLive(s)
                state = {"checks": 0}
                control = fake.systemctl
                def first_stop(action, unit=None):
                    control(action, unit)
                    if action == "stop" and unit == s.PRIMARY:
                        state[failure] = True
                fake.systemctl = first_stop
                result, _ = self.run_promote(fake, state)
                self.assertEqual(result, 2)
                self.assertFalse(any(command.startswith("add:") for command in fake.commands))
                self.assertTrue(all(fake.units[unit].exe == s.OLD and fake.units[unit].running for unit in s.SERVICES))
                fake.assert_no_node_or_ledger_change()

    def test_expiry_during_new_runtime_verification_rolls_back_instead_of_reporting_success(self):
        s = self.s
        fake = FakeLive(s)
        state = {"checks": 0}
        health = fake.health
        def verification(port):
            health(port)
            if fake.loaded[s.PRIMARY] == "new":
                state["expired"] = True
        fake.health = verification
        result, _ = self.run_promote(fake, state)
        self.assertEqual(result, 2)
        self.assertTrue(all(fake.units[unit].running and fake.units[unit].exe == s.OLD for unit in s.SERVICES))
        fake.assert_no_node_or_ledger_change()

    def test_changed_or_revoked_authority_during_preflight_has_zero_mutations(self):
        s = self.s
        for failure in ("changed", "revoked"):
            with self.subTest(failure=failure):
                fake = FakeLive(s)
                state = {"checks": 0}
                health = fake.health
                def preflight(port):
                    health(port)
                    state[failure] = True
                fake.health = preflight
                result, _ = self.run_promote(fake, state)
                self.assertEqual(result, 2)
                self.assertEqual(fake.commands, [])

    def test_original_permit_snapshot_does_not_adopt_renewed_or_mutated_authority(self):
        s = self.s
        original = {"operator": "reviewer", "expiresAtUtc": "original"}
        with patch.object(s, "load_release_permit", return_value=original):
            authority = s.ReleaseAuthority(Path("/fixture/permit"))
            original["expiresAtUtc"] = "renewed"
            with self.assertRaisesRegex(s.Blocked, "changed since original"):
                authority.check()

    def test_unbound_mutation_api_refuses_before_any_side_effect(self):
        s = self.s
        fake = FakeLive(s)
        with self.assertRaisesRegex(s.Blocked, "fresh bound release authority"):
            s.Cutover(fake).promote()
        with self.assertRaisesRegex(s.Blocked, "fresh bound release authority"):
            s.Cutover(fake).code_only_recover(1009)
        self.assertEqual(fake.commands, [])

    def test_started_rollback_can_finish_only_old_code_cleanup_after_expiry(self):
        s = self.s
        fake = FakeLive(s)
        for unit in s.SERVICES:
            fake.dropins[unit] = fake.loaded[unit] = "new"
            fake.units[unit].exe = s.NEW
        state = {"checks": 0}
        control = fake.systemctl
        def expire_after_stop(action, unit=None):
            control(action, unit)
            if action == "stop" and unit == s.PRIMARY:
                state["expired"] = True
        fake.systemctl = expire_after_stop
        result, _ = self.run_promote(fake, state, mode="rollback")
        self.assertEqual(result, 0)
        self.assertEqual(state["checks"], 2)
        self.assertEqual(len(fake.commands), 7)
        self.assertFalse(any(command.startswith("add:") for command in fake.commands))
        self.assertTrue(all(fake.units[unit].running and fake.units[unit].exe == s.OLD for unit in s.SERVICES))
        fake.assert_no_node_or_ledger_change()

    def test_rollback_or_recovery_with_expiry_after_initial_validation_has_zero_mutations(self):
        s = self.s
        for mode in ("rollback", "recover-interrupted"):
            with self.subTest(mode=mode):
                fake = FakeLive(s)
                for unit in s.SERVICES:
                    fake.dropins[unit] = fake.loaded[unit] = "new"
                    fake.units[unit].exe = s.NEW
                if mode == "recover-interrupted":
                    fake.units[s.PRIMARY].running = False
                state = {"checks": 0, "expire_at_lock": True}
                result, _ = self.run_promote(fake, state, mode=mode)
                self.assertEqual(result, 2)
                self.assertEqual(fake.commands, [])



class SettlementSourceAuthority(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.s = load()

    def state(self, *, runtime="old", revision=None, clean=True, visible=True):
        s = self.s
        fake = FakeLive(s)
        for unit in s.SERVICES:
            fake.dropins[unit] = fake.loaded[unit] = runtime
            fake.units[unit].exe = s.NEW if runtime == "new" else s.OLD
        source = {"revision": revision or s.OLD_REV, "clean": clean,
                  "tracked_index_visible": visible}
        fake.source_checkout = lambda: dict(source)
        return fake, s.Cutover(fake, authorize=lambda: None)

    def assert_observation_only(self, receipt, fake):
        for field in ("release_authorized", "financial_drain_certified",
                      "custody_authorized", "claim_889_resolved", "production_mutated"):
            self.assertIs(receipt[field], False)
        self.assertEqual(fake.commands, [])
        fake.assert_no_node_or_ledger_change()

    def test_old_runtime_and_old_checkout_require_both_real_transitions(self):
        fake, ctl = self.state()
        receipt = ctl.source_authority()
        self.assertEqual(receipt["status"], "BLOCKED")
        self.assertTrue(receipt["code_cutover_required"])
        self.assertTrue(receipt["source_transition_required"])
        self.assertFalse(receipt["source_transition_runtime_prerequisite_met"])
        self.assertEqual(receipt["expected_revision"], self.s.REV)
        self.assert_observation_only(receipt, fake)

    def test_checkout_only_advance_never_clears_old_runtime(self):
        fake, ctl = self.state(revision=self.s.REV)
        receipt = ctl.source_authority()
        self.assertFalse(receipt["source_runtime_aligned"])
        self.assertTrue(receipt["code_cutover_required"])
        self.assertFalse(receipt["source_transition_required"])
        self.assertIn("PROTECTED_TWO_SERVICE_CODE_CUTOVER_REQUIRED", receipt["blockers"])
        self.assert_observation_only(receipt, fake)

    def test_real_new_runtime_precedes_source_checkout_transition(self):
        fake, ctl = self.state(runtime="new")
        receipt = ctl.source_authority()
        self.assertFalse(receipt["source_runtime_aligned"])
        self.assertFalse(receipt["code_cutover_required"])
        self.assertTrue(receipt["source_transition_required"])
        self.assertTrue(receipt["source_transition_runtime_prerequisite_met"])
        self.assert_observation_only(receipt, fake)

    def test_both_new_align_only_source_authority_with_all_financial_holds(self):
        fake, ctl = self.state(runtime="new", revision=self.s.REV)
        receipt = ctl.source_authority()
        self.assertTrue(receipt["source_runtime_aligned"])
        self.assertEqual(receipt["status"], "SOURCE_RUNTIME_ALIGNED_FINANCIAL_HOLD")
        self.assertEqual(receipt["blockers"], [])
        self.assertEqual(receipt["live_settlement_sha256"], self.s.NEW_SHA)
        self.assertEqual(receipt["settlement_pids"], {unit: fake.units[unit].pid for unit in self.s.SERVICES})
        self.assertEqual(receipt["consensus_pid"], 1009)
        self.assertTrue(receipt["observed_at_utc"].endswith("Z"))
        self.s.datetime.fromisoformat(receipt["observed_at_utc"].replace("Z", "+00:00"))
        self.assert_observation_only(receipt, fake)

    def test_dirty_hidden_or_unreviewed_checkout_never_aligns(self):
        for args in ({"clean": False}, {"clean": False, "visible": False}, {"clean": True, "visible": False},
                     {"revision": "a" * 40}):
            with self.subTest(args=args):
                case = {"runtime": "new", "revision": self.s.REV, **args}
                fake, ctl = self.state(**case)
                receipt = ctl.source_authority()
                self.assertFalse(receipt["source_runtime_aligned"])
                self.assert_observation_only(receipt, fake)

    def test_source_changing_during_read_never_returns_alignment(self):
        fake, ctl = self.state(runtime="new", revision=self.s.REV)
        observations = iter([{"revision": self.s.REV,"clean":True,"tracked_index_visible":True},
                             {"revision": self.s.OLD_REV,"clean":True,"tracked_index_visible":True}])
        fake.source_checkout = lambda: next(observations)
        with self.assertRaisesRegex(self.s.Blocked, "source changed"):
            ctl.source_authority()
        self.assertEqual(fake.commands, [])

    def test_settlement_rollback_exit_or_pid_change_during_second_git_refuses_alignment(self):
        s = self.s
        for change in ("rollback", "exit", "pid"):
            with self.subTest(change=change):
                fake, ctl = self.state(runtime="new", revision=s.REV)
                original = fake.source_checkout
                calls = 0
                def checkout():
                    nonlocal calls
                    calls += 1
                    if calls == 2:
                        if change == "rollback":
                            for unit in s.SERVICES:
                                fake.dropins[unit] = fake.loaded[unit] = "old"
                                fake.units[unit].exe = s.OLD
                        elif change == "exit":
                            fake.units[s.PRIMARY].running = False
                        else:
                            fake.units[s.PRIMARY].pid += 1
                    return original()
                fake.source_checkout = checkout
                with self.assertRaises(s.Blocked):
                    ctl.source_authority()
                self.assertEqual(fake.commands, [])

    def test_settlement_pid_change_during_last_health_refuses_alignment(self):
        s = self.s
        fake, ctl = self.state(runtime="new", revision=s.REV)
        after_source = False
        original_source, original_health = fake.source_checkout, fake.health
        calls = 0
        def checkout():
            nonlocal calls, after_source
            calls += 1
            after_source = calls == 2
            return original_source()
        def health(port):
            original_health(port)
            if after_source and port == 8093:
                fake.units[s.FOUNDER].pid += 1
        fake.source_checkout, fake.health = checkout, health
        with self.assertRaises(s.Blocked):
            ctl.source_authority()
        self.assertEqual(fake.commands, [])

    def test_mixed_runtime_and_consensus_drift_refuse_source_gate(self):
        fake, ctl = self.state(runtime="new", revision=self.s.REV)
        fake.dropins[self.s.FOUNDER] = fake.loaded[self.s.FOUNDER] = "old"
        with self.assertRaisesRegex(self.s.Blocked, "mixed service"):
            ctl.source_authority()
        fake, ctl = self.state(runtime="new", revision=self.s.REV)
        fake.units[self.s.CONSENSUS].exe = "unreviewed"
        with self.assertRaisesRegex(self.s.Blocked, "consensus running identity"):
            ctl.source_authority()
        self.assertEqual(fake.commands, [])

    def test_bounded_inspection_refuses_excess_stdout_or_stderr(self):
        for stream in ("stdout", "stderr"):
            with self.subTest(stream=stream):
                with self.assertRaisesRegex(self.s.Blocked, "output exceeds limit"):
                    self.s.Live().command(sys.executable, "-c", "import sys;sys."+stream+".write('x'*1048577)")

    def test_real_git_read_only_hidden_index_and_ignored_source_guards(self):
        s = self.s
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            def git(*args):
                return subprocess.run(["git", "-C", td, *args], check=True,
                                      capture_output=True, text=True).stdout.strip()
            git("init", "--quiet")
            (root / "source.go").write_text("package source\n")
            (root / ".gitignore").write_text("cache\n")
            git("add", ".")
            git("-c", "user.name=Offline Fixture", "-c", "user.email=fixture@example.invalid",
                "commit", "--quiet", "-m", "source fixture")
            before = (root / ".git/index").read_bytes()
            with patch.object(s, "CHECKOUT", td):
                self.assertTrue(s.Live().source_checkout()["clean"])
                self.assertEqual((root / ".git/index").read_bytes(), before)
                git("update-index", "--assume-unchanged", "source.go")
                self.assertFalse(s.Live().source_checkout()["tracked_index_visible"])
                git("update-index", "--no-assume-unchanged", "source.go")
                git("update-index", "--skip-worktree", "source.go")
                self.assertFalse(s.Live().source_checkout()["clean"])
                git("update-index", "--no-skip-worktree", "source.go")
                (root / "cache").write_text("ignored source contamination")
                self.assertFalse(s.Live().source_checkout()["clean"])
                (root / "cache").unlink()
                (root / "untracked").write_text("preserve me")
                self.assertFalse(s.Live().source_checkout()["clean"])
                self.assertTrue((root / "untracked").exists())

    def test_inherited_git_repository_overlay_cannot_redirect_source_authority(self):
        s = self.s
        with tempfile.TemporaryDirectory() as td:
            roots = [Path(td) / name for name in ("actual", "overlay")]
            for root in roots:
                root.mkdir()
                def git(*args):
                    return subprocess.run(["git", "-C", str(root), *args], check=True,
                                          capture_output=True, text=True).stdout.strip()
                git("init", "--quiet")
                (root / "source.go").write_text("package " + root.name + "\n")
                git("add", ".")
                git("-c", "user.name=Offline Fixture", "-c", "user.email=fixture@example.invalid",
                    "commit", "--quiet", "-m", root.name)
            actual, overlay = roots
            expected = subprocess.check_output(["git", "-C", str(actual), "rev-parse", "HEAD"], text=True).strip()
            with patch.object(s, "CHECKOUT", str(actual)), patch.dict(s.os.environ, {
                "GIT_DIR": str(overlay / ".git"), "GIT_WORK_TREE": str(overlay),
                "GIT_INDEX_FILE": str(overlay / ".git/index"),
                "GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "core.worktree", "GIT_CONFIG_VALUE_0": str(overlay),
            }):
                result = s.Live().source_checkout()
            self.assertEqual(result["revision"], expected)
            self.assertTrue(result["clean"])

    def test_read_only_main_never_loads_permit_or_takes_mutation_lock(self):
        s = self.s
        fake, _ = self.state()
        output = io.StringIO()
        with patch.object(s.os, "geteuid", return_value=0), \
             patch.object(s, "Live", return_value=fake), \
             patch.object(s, "load_release_permit", side_effect=AssertionError("permit read")), \
             patch.object(s, "acquire_mutation_lock", side_effect=AssertionError("mutation lock")), \
             patch.object(sys, "argv", [str(SCRIPT), "--mode", "source-authority"]), \
             contextlib.redirect_stdout(output), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(s.main(), 2)
        receipt = json.loads(output.getvalue())
        self.assertTrue(receipt["code_cutover_required"])
        self.assertFalse(receipt["production_mutated"])
        self.assertEqual(fake.commands, [])

    def test_operator_source_transition_is_self_contained_and_gated_before_mutations(self):
        text = (ROOT / "docs/mainnet-settlement-runbook.md").read_text()
        block = re.search(r"```sh\n(\(\nset -eu.*?\n\))\n```", text, re.S)[1]
        with tempfile.NamedTemporaryFile("w", suffix=".sh") as stream:
            stream.write(block)
            stream.flush()
            subprocess.run(["bash", "-n", stream.name], check=True, capture_output=True)
        self.assertEqual(block.count("\nrequire_source_transition\n"), 2)
        self.assertLess(block.index("\nrequire_source_transition\n"), block.index("wgit fetch "))
        self.assertLess(block.rindex("\nrequire_source_transition\n"), block.index("wgit merge --ff-only"))
        self.assertIn('"code_cutover_required": False', block)
        self.assertIn('"checkout_revision": "' + self.s.OLD_REV + '"', block)
        self.assertIn('"release_authorized": False', block)
        self.assertIn('"source_runtime_aligned": False', block)
        self.assertIn('type(r.get(k)) is type(v)', block)
        self.assertIn('core.hooksPath=/dev/null', block)

    def test_read_only_mode_never_accepts_a_finance_permit(self):
        args = [sys.executable, str(SCRIPT), "--mode", "source-authority", "--permit", "/never/read/permit"]
        proc = subprocess.run(args, capture_output=True, text=True, timeout=5)
        self.assertEqual(proc.returncode, 2)
        self.assertIn("BLOCKED:", proc.stderr)


if __name__ == "__main__":
    unittest.main()

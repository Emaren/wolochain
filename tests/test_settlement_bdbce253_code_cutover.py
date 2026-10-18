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
            self.assertEqual(s.Cutover(fake).promote(), "new")
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
                s.Cutover(fake).promote()
        self.assertEqual(s.Cutover(fake).inspect(), "old")
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
            s.Cutover(fake).promote()
        self.assertEqual(errors, [8092])
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
        return fake, s.Cutover(fake)

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

"""Offline permit/fence/backup faults; no real systemd, Docker or PostgreSQL.

The runner and root-private I/O boundary are replaced explicitly. These tests
qualify refusal/recovery behavior, never human approvals or live quiescence.
"""
from __future__ import annotations

from contextlib import ExitStack
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import importlib.util
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/settlement_financial_maintenance.py"
SPEC = importlib.util.spec_from_file_location("financial_maintenance_test_only", SCRIPT)
MOD = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MOD
SPEC.loader.exec_module(MOD)
NOW = datetime(2026, 10, 24, 12, tzinfo=timezone.utc)


def synthetic_private_write(path, raw):
    """Root-private authority boundary substitute for non-root temporary tests."""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(raw)


def settlement_fixture(root, snapshot):
    volume = root / "volume"
    (snapshot / "proof").mkdir(parents=True, exist_ok=True)
    if not (snapshot / "proof/RECEIPT.txt").exists():
        (snapshot / "proof/RECEIPT.txt").write_bytes(b"synthetic settlement snapshot receipt")
    for lane, live in (("primary", "settlement-state"), ("founder", "founder-rewards-settlement-state")):
        for path in (volume / "wolochain-mainnet" / live, snapshot / "state" / lane):
            path.mkdir(parents=True)
            (path / "request.json").write_bytes(b'{"claim":889,"status":"pending","retry":false}')
    return volume


def docker_command(argv):
    return ["docker"] + list(argv[len(MOD.DOCKER):]) if list(argv[:len(MOD.DOCKER)]) == MOD.DOCKER else argv


def valid_permit(*, now=NOW):
    """Synthetic approvals only; never written to an operator permit path."""
    return {
        "schema": MOD.SCHEMA, "action": "fence-backup-isolated-restore",
        "scope_sha256": MOD.scope_digest(), "tool_sha256": MOD.digest(SCRIPT.read_bytes()),
        "packet_sha256": "1" * 64, "procedure_sha256": "2" * 64,
        "not_before": (now - timedelta(seconds=1)).isoformat().replace("+00:00", "Z"),
        "expires_at": (now + timedelta(minutes=29)).isoformat().replace("+00:00", "Z"),
        "approval_refs": {role: {"identity": "synthetic " + role,
                                  "approval_sha256": MOD.digest(role.encode())}
                          for role in MOD.ROLE_NAMES},
        "attestations": dict.fromkeys(MOD.ATTESTATIONS, True),
        "max_total_bytes": 1 << 20,
        "databases": {lane: {"env_path": "/etc/test-only/" + lane + ".env",
                            "env_sha256": MOD.digest(lane.encode()),
                            "database_sha256": MOD.digest(("test_" + lane).encode()),
                            "financial_tables": ["claims", "payments"], "postgres_major": 16}
                      for lane in ("hd", "de")},
        "restore_image": "postgres@sha256:" + "a" * 64,
    }


class FakeSystemd:
    def __init__(self):
        self.active = dict.fromkeys(MOD.UNITS, True)
        self.calls = []
        self.jobs = []
        self.fail_stop = None
        self.foreign_condition = False
        self.loaded = False
        self.pid_after_stop = None

    def __call__(self, argv, **kwargs):
        self.calls.append(list(argv))
        if argv[:3] == ["systemctl", "--no-pager", "show"]:
            unit = argv[-1]
            active = self.active[unit]
            fields = {"Id": unit, "LoadState": "loaded", "ActiveState": "active" if active else "inactive",
                      "SubState": "running" if active else "dead", "MainPID": "101" if active else "0",
                      "ControlGroup": "", "UnitFileState": "enabled", "Triggers": "", "TriggeredBy": "",
                      "Restart": "always", "Persistent": "yes",
                      "FragmentPath": "/etc/systemd/system/" + unit,
                      "DropInPaths": str(MOD.dropin(unit)) if self.loaded else ""}
            if unit == self.pid_after_stop and not active:
                fields["MainPID"] = "999"
            return "\n".join(f"{k}={v}" for k, v in fields.items()) + "\n"
        if argv[:2] == ["systemctl", "daemon-reload"]:
            self.loaded = True
            return ""
        if argv[:2] == ["systemctl", "stop"]:
            unit = argv[-1]
            if unit == self.fail_stop:
                raise MOD.MaintenanceError("INJECTED_STOP_FAILURE")
            self.active[unit] = False
            return ""
        if argv[0] == "busctl":
            if "ListJobs" in argv:
                return json.dumps({"type": "a(usssoo)", "data": [self.jobs]})
            if "LoadUnit" in argv:
                return json.dumps({"type": "o", "data": ["/org/freedesktop/systemd1/unit/test"]})
            condition = (["ConditionPathExists", False, True, str(MOD.HOLD), 0]
                         if self.loaded and not self.foreign_condition else None)
            return json.dumps({"type": "a(sbbsi)", "data": [condition] if condition else []})
        raise AssertionError("Unreviewed subprocess: " + str(argv))


class SystemdJobsTests(unittest.TestCase):
    def test_real_typed_empty_response_only_is_zero_jobs(self):
        expected = ["busctl", "--system", "--json=short", "call",
            "org.freedesktop.systemd1", "/org/freedesktop/systemd1",
            "org.freedesktop.systemd1.Manager", "ListJobs"]
        def actual_api(argv):
            self.assertEqual(argv, expected)
            return '{"type":"a(usssoo)","data":[[]]}'
        MOD.no_jobs(actual_api)
        for value in ('No jobs running.', '[]', '{}', '{"type":"a(usssoo)","data":[]}',
                      '{"type":"wrong","data":[[]]}',
                      '{"type":"a(usssoo)","data":[[[1,"unrelated.service","start","waiting","/job/1","/unit/1"]]]}'):
            with self.subTest(value=value), self.assertRaisesRegex(MOD.MaintenanceError, "PENDING_OR_UNKNOWN_SYSTEMD_JOB"):
                MOD.no_jobs(lambda _: value)


class ReloadJobDrainTests(unittest.TestCase):
    def test_reload_jobs_must_finish_and_original_authority_must_still_be_fresh(self):
        permit = valid_permit()
        blocked = MOD.MaintenanceError("PENDING_OR_UNKNOWN_SYSTEMD_JOB")
        with patch.object(MOD, "validate_permit") as authority, patch.object(MOD, "no_jobs", side_effect=[blocked, None]) as jobs, patch.object(MOD.time, "sleep"):
            MOD.wait_for_no_jobs(lambda _: "", permit)
            self.assertEqual(jobs.call_count, 2)
            self.assertEqual(authority.call_count, 2)
        with patch.object(MOD, "validate_permit", side_effect=[None, MOD.MaintenanceError("APPROVED_WINDOW_EXPIRED")]), patch.object(MOD, "no_jobs", side_effect=blocked), patch.object(MOD.time, "sleep"):
            with self.assertRaisesRegex(MOD.MaintenanceError, "APPROVED_WINDOW_EXPIRED"):
                MOD.wait_for_no_jobs(lambda _: "", permit)
        with patch.object(MOD, "validate_permit"), patch.object(MOD, "no_jobs", side_effect=blocked), patch.object(MOD.time, "monotonic", side_effect=[0, 2]):
            with self.assertRaisesRegex(MOD.MaintenanceError, "PENDING_OR_UNKNOWN_SYSTEMD_JOB"):
                MOD.wait_for_no_jobs(lambda _: "", permit, seconds=1)


class PermitTests(unittest.TestCase):
    def test_fence_survives_reboot_and_has_no_auto_resume_action(self):
        self.assertEqual(MOD.HOLD.parent, Path("/etc/wolochain-financial-maintenance"))
        self.assertIn(b"ConditionPathExists=!", MOD.expected_dropin())
        self.assertEqual(len(MOD.APPS), 4)
        self.assertEqual(len(MOD.FAMILIES), 6)
        self.assertEqual(MOD.LOCK, Path("/run/lock/aoe2war-wolo-two-settlement-code-only.lock"))
        self.assertEqual(MOD.DOCKER, ["docker", "--host=unix:///var/run/docker.sock"])

    def test_exact_synthetic_contract_is_accepted_without_claiming_certification(self):
        value = valid_permit()
        self.assertIs(MOD.validate_permit(value, now=NOW), value)

    def test_missing_extra_or_repurposed_scope_is_rejected(self):
        cases = []
        missing = valid_permit(); del missing["packet_sha256"]; cases.append(missing)
        extra = valid_permit(); extra["enable_custody"] = True; cases.append(extra)
        for field, changed in (("action", "unfence"), ("scope_sha256", "b" * 64),
                               ("tool_sha256", "c" * 64), ("packet_sha256", "0" * 64)):
            value = valid_permit(); value[field] = changed; cases.append(value)
        for value in cases:
            with self.subTest(value=value), self.assertRaises(MOD.MaintenanceError):
                MOD.validate_permit(value, now=NOW)

    def test_not_yet_valid_expired_and_over_30_minute_windows_fail(self):
        for start, end in ((NOW + timedelta(seconds=1), NOW + timedelta(minutes=20)),
                           (NOW - timedelta(minutes=20), NOW),
                           (NOW - timedelta(minutes=1), NOW + timedelta(minutes=30))):
            value = valid_permit()
            value["not_before"] = start.isoformat().replace("+00:00", "Z")
            value["expires_at"] = end.isoformat().replace("+00:00", "Z")
            with self.subTest(start=start, end=end), self.assertRaises(MOD.MaintenanceError):
                MOD.validate_permit(value, now=NOW)

    def test_missing_human_or_external_scope_does_not_become_an_approval(self):
        for role in MOD.ROLE_NAMES:
            value = valid_permit(); del value["approval_refs"][role]
            with self.subTest(role=role), self.assertRaises(MOD.MaintenanceError):
                MOD.validate_permit(value, now=NOW)
        for attestation in MOD.ATTESTATIONS:
            value = valid_permit(); value["attestations"][attestation] = False
            with self.subTest(attestation=attestation), self.assertRaises(MOD.MaintenanceError):
                MOD.validate_permit(value, now=NOW)

    def test_same_database_unsafe_tables_unpinned_image_and_boolean_budget_fail(self):
        values = []
        value = valid_permit(); value["databases"]["de"]["database_sha256"] = value["databases"]["hd"]["database_sha256"]; values.append(value)
        value = valid_permit(); value["databases"]["hd"]["financial_tables"] = ["claims;DROP DATABASE postgres"]; values.append(value)
        value = valid_permit(); value["restore_image"] = "postgres:latest"; values.append(value)
        value = valid_permit(); value["max_total_bytes"] = True; values.append(value)
        for value in values:
            with self.subTest(value=value), self.assertRaises(MOD.MaintenanceError):
                MOD.validate_permit(value, now=NOW)


class FenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.stack = ExitStack(); self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(MOD, "HOLD", self.root / "hold/HOLD"))
        self.stack.enter_context(patch.object(MOD, "SYSTEMD", self.root / "systemd"))
        MOD.SYSTEMD.mkdir()
        self.stack.enter_context(patch.object(MOD, "clock", return_value=NOW))
        self.stack.enter_context(patch.object(MOD.os, "geteuid", return_value=0))
        # Only synthetic temp paths are root-attributed; actual private I/O tests
        # exercise no live files and never weaken the production helper.
        original_lstat = Path.lstat
        def root_lstat(path, *args, **kwargs):
            result = original_lstat(path, *args, **kwargs)
            if path == self.root or self.root in path.parents:
                fields = list(result); fields[4] = fields[5] = 0
                return os.stat_result(fields)
            return result
        self.stack.enter_context(patch.object(Path, "lstat", root_lstat))
        self.stack.enter_context(patch.object(MOD, "private_read", side_effect=lambda path, *args: Path(path).read_bytes()))
        self.stack.enter_context(patch.object(MOD, "write_new", side_effect=synthetic_private_write))
        self.permit = self.root / "permit.json"
        self.permit.write_bytes(MOD.canonical(valid_permit()))
        self.receipt = self.root / "fence.json"
        self.runner = FakeSystemd()

    def do_fence(self):
        return MOD.fence(self.permit, self.receipt, runner=self.runner)

    def test_gates_are_loaded_before_stops_and_timer_order_is_exact(self):
        value = self.do_fence()
        reload_index = self.runner.calls.index(["systemctl", "daemon-reload"])
        stops = [call for call in self.runner.calls if call[:2] == ["systemctl", "stop"]]
        self.assertEqual([call[-1] for call in stops], list(MOD.TIMERS + MOD.ONESHOTS + MOD.APPS))
        self.assertTrue(all(self.runner.calls.index(call) > reload_index for call in stops))
        self.assertTrue(MOD.HOLD.is_file())
        self.assertTrue(all(MOD.dropin(unit).read_bytes() == MOD.expected_dropin() for unit in MOD.UNITS))
        self.assertFalse(value["resume_authorized"])
        self.assertFalse(any(call[:2] == ["systemctl", "start"] for call in self.runner.calls))

    def test_each_partial_stop_failure_retains_every_gate_and_never_resumes(self):
        for failed_unit in MOD.UNITS:
            with self.subTest(unit=failed_unit), tempfile.TemporaryDirectory() as temp:
                with patch.object(MOD, "HOLD", self.root / Path(temp).name / "hold/HOLD"), \
                     patch.object(MOD, "SYSTEMD", self.root / Path(temp).name / "systemd"):
                    MOD.SYSTEMD.mkdir(parents=True)
                    # This sub-scope has its own scope digest and fresh permit.
                    self.permit.write_bytes(MOD.canonical(valid_permit()))
                    fake = FakeSystemd(); fake.fail_stop = failed_unit
                    with self.assertRaisesRegex(MOD.MaintenanceError, "INJECTED_STOP_FAILURE"):
                        MOD.fence(self.permit, self.receipt, runner=fake)
                    self.assertTrue(MOD.HOLD.is_file())
                    self.assertTrue(all(MOD.dropin(unit).is_file() for unit in MOD.UNITS))
                    self.assertFalse(self.receipt.exists())
                    self.assertFalse(any(call[:2] == ["systemctl", "start"] for call in fake.calls))

    def test_foreign_effective_condition_blocks_before_any_stop(self):
        self.runner.foreign_condition = True
        with self.assertRaisesRegex(MOD.MaintenanceError, "ACTIVATION_GATE_NOT_EFFECTIVE"):
            self.do_fence()
        self.assertTrue(MOD.HOLD.is_file())
        self.assertFalse(any(call[:2] == ["systemctl", "stop"] for call in self.runner.calls))

    def test_pending_jobs_before_fence_cause_no_file_or_service_mutation(self):
        self.runner.jobs = [{"unit": "aoe2hdbets-web.service", "type": "start"}]
        with self.assertRaisesRegex(MOD.MaintenanceError, "PENDING_OR_UNKNOWN_SYSTEMD_JOB"):
            self.do_fence()
        self.assertFalse(MOD.HOLD.exists())
        self.assertFalse(any(call[:2] == ["systemctl", "stop"] for call in self.runner.calls))

    def test_inactive_unit_with_remaining_pid_is_not_drain(self):
        self.runner.pid_after_stop = MOD.ONESHOTS[0]
        with self.assertRaisesRegex(MOD.MaintenanceError, "PRODUCER_NOT_FENCED"):
            self.do_fence()
        self.assertTrue(MOD.HOLD.exists())
        self.assertFalse(self.receipt.exists())

    def test_window_expiring_during_io_keeps_gates_and_stops_forward_work(self):
        expired = False
        def runner(argv, **kwargs):
            nonlocal expired
            value = self.runner(argv, **kwargs)
            if argv[:2] == ["systemctl", "stop"]:
                expired = True
            return value
        with patch.object(MOD, "clock", side_effect=lambda: NOW + timedelta(minutes=31) if expired else NOW):
            with self.assertRaisesRegex(MOD.MaintenanceError, "APPROVED_WINDOW_UNAVAILABLE"):
                MOD.fence(self.permit, self.receipt, runner=runner)
        self.assertTrue(MOD.HOLD.exists())
        self.assertEqual(sum(call[:2] == ["systemctl", "stop"] for call in self.runner.calls), 1)
        self.assertFalse(any(call[:2] == ["systemctl", "start"] for call in self.runner.calls))

    def test_readonly_nested_fence_verification_does_not_reacquire_global_lock(self):
        self.do_fence()
        with patch.object(MOD.fcntl, "flock", side_effect=AssertionError("nested lock forbidden")):
            value = MOD.verify_current_fence(self.receipt, MOD.scope_digest(), runner=self.runner)
        self.assertFalse(value["resume_authorized"])

    def test_expired_window_still_observes_retained_fence_without_authorizing_admission(self):
        self.do_fence()
        with patch.object(MOD, "clock", return_value=NOW + timedelta(minutes=31)):
            with self.assertRaisesRegex(MOD.MaintenanceError, "APPROVED_WINDOW_UNAVAILABLE"):
                MOD.verify_current_fence(self.receipt, MOD.scope_digest(), runner=self.runner)
            value = MOD.verify_retained_fence(self.receipt, MOD.scope_digest(), runner=self.runner)
        self.assertEqual(set(value["units"]), set(MOD.UNITS))
        self.assertFalse(value["original_window_current"])
        self.assertFalse(value["admission_authorized"])
        self.assertFalse(value["resume_authorized"])

    def test_replaced_permit_hold_or_dropin_invalidates_current_fence(self):
        self.do_fence()
        original = self.permit.read_bytes()
        changed = valid_permit(); changed["packet_sha256"] = "3" * 64
        self.permit.write_bytes(MOD.canonical(changed))
        with self.assertRaisesRegex(MOD.MaintenanceError, "FENCE_PERMIT_ROTATED"):
            MOD.verify_current_fence(self.receipt, MOD.scope_digest(), runner=self.runner)
        self.permit.write_bytes(original)
        MOD.HOLD.write_bytes(b"foreign hold")
        with self.assertRaisesRegex(MOD.MaintenanceError, "OWNED_HOLD_MISSING_OR_CHANGED"):
            MOD.verify_current_fence(self.receipt, MOD.scope_digest(), runner=self.runner)

    def test_active_timer_reappearing_or_new_job_invalidates_fence(self):
        self.do_fence()
        self.runner.active[MOD.TIMERS[0]] = True
        with self.assertRaisesRegex(MOD.MaintenanceError, "PRODUCER_NOT_FENCED"):
            MOD.verify_current_fence(self.receipt, MOD.scope_digest(), runner=self.runner)
        self.runner.active[MOD.TIMERS[0]] = False
        self.runner.jobs = [{"unit": MOD.APPS[0], "type": "start"}]
        with self.assertRaisesRegex(MOD.MaintenanceError, "PENDING_OR_UNKNOWN_SYSTEMD_JOB"):
            MOD.verify_current_fence(self.receipt, MOD.scope_digest(), runner=self.runner)

    def test_dropin_api_has_no_consensus_or_settlement_scope(self):
        for unit in ("wolochaind-mainnet.service", "wolochain-mainnet-settlement.service",
                     "wolochain-founder-rewards-settlement.service", "unknown.service"):
            with self.subTest(unit=unit), self.assertRaisesRegex(MOD.MaintenanceError, "UNREVIEWED_UNIT"):
                MOD.dropin(unit)


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        # Substitute protected source ownership only; execute actual pinned bytes.
        self.source = patch.object(MOD, "private_read", side_effect=lambda path, *args: Path(path).read_bytes())
        self.source.start()
        self.addCleanup(self.source.stop)

    def catalog(self, **changes):
        value = {"database": "test_hd", "readonly": "on", "major": 16,
                 "privilege": [True, True], "existing": ["test_hd"],
                 "sessions": [], "prepared_transactions": 0}
        value.update(changes)
        return value

    def test_underprivileged_or_incomplete_catalog_cannot_certify_census(self):
        for changes in ({"privilege": [False, False]},
                        {"privilege": [1, False]}, {"privilege": None},
                        {"existing": []}, {"existing": ["test_de"]},
                        {"sessions": [[987, "test_hd", None, "writer", None]]},
                        {"sessions": [[987, "test_hd", "idle", "writer", "client backend"]]},
                        {"prepared_transactions": 1}, {"prepared_transactions": None},
                        {"prepared_transactions": True}, {"prepared_transactions": "0"},
                        {"sessions": None}):
            answers = [json.dumps(self.catalog(**changes)), '{}', '{}', '[]', '[]']
            with self.subTest(changes=changes), patch.object(MOD, "psql", side_effect=answers), \
                 patch.object(MOD, "private_read", side_effect=lambda path, *args: Path(path).read_bytes()), \
                 self.assertRaisesRegex(MOD.MaintenanceError, "DATABASE_NOT_EXCLUSIVELY_QUIESCED"):
                MOD.financial_census(valid_permit()["databases"]["hd"], {}, None)

    def test_observer_source_pin_is_checked_before_any_database_command(self):
        path = SCRIPT.with_name("settlement_pg_quiescence_observer.py")
        self.assertEqual(MOD.digest(path.read_bytes()), MOD.PG_OBSERVER_SHA256)
        for raw in (path.read_bytes() + b"\nraise RuntimeError('tampered')\n", b""):
            with self.subTest(bytes=len(raw)), patch.object(MOD, "private_read", return_value=raw), \
                 patch.object(MOD, "psql") as psql, \
                 self.assertRaisesRegex(MOD.MaintenanceError, "PG_OBSERVER_SOURCE_DRIFT"):
                MOD.financial_census(valid_permit()["databases"]["hd"], {}, None)
            psql.assert_not_called()
        with patch.object(MOD, "private_read", side_effect=FileNotFoundError), \
             patch.object(MOD, "psql") as psql, \
             self.assertRaisesRegex(MOD.MaintenanceError, "PG_OBSERVER_SOURCE_UNAVAILABLE"):
            MOD.financial_census(valid_permit()["databases"]["hd"], {}, None)
        psql.assert_not_called()

    def test_shared_observer_keeps_observation_separate_from_quiescence(self):
        observer = MOD.pg_observer()
        for superuser, all_stats in ((True, False), (False, True)):
            value = observer.validate_catalog_observation(("test_hd",), [superuser, all_stats],
                ["test_hd"], [[987, "test_hd", "idle", "writer", "client backend"]], 2)
            self.assertEqual((value.other_sessions, value.prepared_transactions), (1, 2))
        for inventory in ((), ("test_hd", "test_hd"), ("bad-name",)):
            with self.subTest(inventory=inventory), self.assertRaises(observer.Hold):
                observer.validate_catalog_observation(inventory, [True, True], [], [], 0)

    def env(self, raw, **changes):
        contract = dict(valid_permit()["databases"]["hd"], env_sha256=MOD.digest(raw))
        contract.update(changes)
        with patch.object(MOD, "private_read", return_value=raw):
            return MOD.pg_environment(contract)

    def test_private_connection_is_exact_local_readonly_and_not_in_argv(self):
        env = self.env(b'DATABASE_URL="postgresql://role:private%20secret@127.0.0.1:5432/test_hd"\n')
        self.assertEqual(env["PGDATABASE"], "test_hd")
        self.assertEqual(env["PGPASSWORD"], "private secret")
        self.assertIn("default_transaction_read_only=on", env["PGOPTIONS"])
        self.assertNotIn("DATABASE_URL", env)
        calls = []
        def runner(argv, **kwargs):
            calls.append((argv, kwargs)); return "1"
        self.assertEqual(MOD.psql("SELECT 1;", env, runner), "1")
        self.assertNotIn("private", " ".join(calls[0][0]))
        self.assertIn("--no-psqlrc", calls[0][0])
        self.assertIn("--set=ON_ERROR_STOP=1", calls[0][0])
        self.assertIn("--set=AUTOCOMMIT=on", calls[0][0])

    def test_wrong_database_remote_host_overrides_duplicate_url_and_env_drift_fail(self):
        for raw in (b"DATABASE_URL=postgresql://u:p@127.0.0.1/wrong\n",
                    b"DATABASE_URL=postgresql://u:p@production.example/test_hd\n",
                    b"DATABASE_URL=postgresql://u:p@127.0.0.1/test_hd?options=-creadonly=off\n",
                    b"DATABASE_URL=postgresql://u:p@127.0.0.1/test_hd\nDATABASE_URL=postgresql://u:p@127.0.0.1/test_hd\n"):
            with self.subTest(raw=raw), self.assertRaises(MOD.MaintenanceError):
                self.env(raw)
        with self.assertRaisesRegex(MOD.MaintenanceError, "DATABASE_ENV_DRIFT"):
            self.env(b"DATABASE_URL=postgresql://u:p@127.0.0.1/test_hd\n", env_sha256="1" * 64)

    def test_database_readonly_version_and_exclusive_sessions_are_required(self):
        contract = valid_permit()["databases"]["hd"]
        good = self.catalog()
        for field, value in (("database", "test_de"), ("readonly", "off"),
                             ("major", 15), ("major", True), ("prepared_transactions", 1)):
            meta = dict(good, **{field: value})
            with self.subTest(field=field), patch.object(MOD, "psql", return_value=json.dumps(meta)), \
                 self.assertRaisesRegex(MOD.MaintenanceError, "DATABASE_NOT_EXCLUSIVELY_QUIESCED"):
                MOD.financial_census(contract, {}, lambda *a, **k: None)

    def test_census_includes_complete_rows_constraints_and_sequences_without_sum(self):
        answers = iter([json.dumps(self.catalog()),
                        '{"rows":"947","sha256":"' + "a" * 64 + '"}',
                        '{"rows":"1","sha256":"' + "b" * 64 + '"}',
                        '[{"conname":"claims_owner_fk","convalidated":true}]',
                        '[{"sequencename":"claims_id_seq","last_value":947}]'])
        calls = []
        def fake(sql, env, runner):
            calls.append(sql); return next(answers)
        with patch.object(MOD, "psql", side_effect=fake):
            value = MOD.financial_census(valid_permit()["databases"]["hd"], {}, None)
        self.assertEqual(value["tables"]["claims"]["rows"], "947")
        self.assertIn("pg_get_constraintdef", calls[-2])
        self.assertIn("pg_sequences", calls[-1])
        self.assertIn("pg_has_role", calls[0])
        self.assertIn("pg_catalog.pg_prepared_xacts", calls[0])
        self.assertNotIn("autovacuum worker", calls[0])
        self.assertTrue(MOD.SHA.fullmatch(value["constraints_sha256"]))
        self.assertNotIn("sum(", " ".join(calls).lower())


class RestoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name); self.output = self.root / "backup"; self.output.mkdir()
        self.fence = self.root / "fence.json"; self.fence.write_bytes(b"synthetic fence")
        (self.output / "INCOMPLETE").write_bytes(b"still unverified")
        for lane in ("hd", "de"):
            (self.output / (lane + ".dump")).write_bytes(b"synthetic archive " + lane.encode())
        self.permit = valid_permit()
        self.census = {"tables": {"claims": {"rows": "947", "sha256": "b" * 64}},
                       "constraints_sha256": "c" * 64, "sequences_sha256": "d" * 64,
                       "postgres_major": 16}
        self.snapshot = self.root / "snapshot"
        volume = settlement_fixture(self.root, self.snapshot)
        self.manifest = {"scope_sha256": MOD.scope_digest(), "fence_receipt_sha256": MOD.file_sha(self.fence),
                         "isolated_restore_verified": False,
                         "settlement_snapshot": str(self.snapshot),
                         "settlement_snapshot_receipt_sha256": MOD.file_sha(self.snapshot / "proof/RECEIPT.txt"),
                         "databases": {lane: {"sha256": MOD.file_sha(self.output / (lane + ".dump"))}
                                       for lane in ("hd", "de")},
                         "financial_censuses": {lane: deepcopy(self.census) for lane in ("hd", "de")}}
        (self.output / "backup.json").write_bytes(MOD.canonical(self.manifest))
        self.calls = []
        self.stack = ExitStack(); self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(MOD, "BACKUPS", self.root))
        self.stack.enter_context(patch.object(MOD, "SNAPSHOT_ROOT", self.root))
        self.stack.enter_context(patch.object(MOD, "VOLUME", volume))
        self.stack.enter_context(patch.object(MOD, "clock", return_value=NOW))
        self.stack.enter_context(patch.object(MOD, "write_new", side_effect=synthetic_private_write))
        self.stack.enter_context(patch.object(MOD, "verify_current_fence", return_value={"permit": self.permit}))
        self.stack.enter_context(patch.object(MOD, "private_json", side_effect=lambda path: (json.loads(Path(path).read_bytes()), MOD.file_sha(path))))
        self.stack.enter_context(patch.object(MOD, "private_read", side_effect=lambda path, *args: Path(path).read_bytes()))
        self.stack.enter_context(patch.object(MOD, "financial_census", return_value=self.census))
        self.scratch = self.root / "scratch-owned"
        self.scratch.mkdir()
        self.stack.enter_context(patch.object(MOD, "make_restore_scratch", return_value=self.scratch))
        self.stack.enter_context(patch.object(MOD, "cleanup_restore_scratch"))

    def runner(self, argv, **kwargs):
        argv = docker_command(argv)
        self.calls.append((list(argv), kwargs))
        if argv[:3] == ["docker", "image", "inspect"]:
            return "sha256:synthetic-image"
        if argv[:2] == ["docker", "run"]:
            return "e" * 64
        if argv[:2] == ["docker", "inspect"]:
            return json.dumps([{"Id": "e" * 64,
                "Config": {"Image": self.permit["restore_image"], "User": "999:999",
                           "Labels": {"wolo.financial-maintenance": MOD.scope_digest()}},
                "HostConfig": {"NetworkMode": "none", "ReadonlyRootfs": True, "Privileged": False},
                "Mounts": [{"Type": "bind", "Source": str(self.scratch),
                            "Destination": "/var/lib/postgresql/data", "RW": True}]}])
        if argv[-2:] == ["cat", "/proc/1/comm"]:
            return "postgres\n"
        return ""

    def test_unknown_or_mismatched_restore_never_removes_incomplete(self):
        with patch.object(MOD, "financial_census", return_value={"tables": "mismatch"}):
            with self.assertRaisesRegex(MOD.MaintenanceError, "RESTORED_FINANCIAL_INTEGRITY_MISMATCH"):
                MOD.restore_isolated(self.fence, self.output, runner=self.runner)
        self.assertTrue((self.output / "INCOMPLETE").is_file())
        self.assertFalse((self.output / "restore.json").exists())
        self.assertTrue(any(call[:3] == ["docker", "rm", "--force"] for call, _ in self.calls))

    def test_archive_checksum_change_blocks_before_starting_container(self):
        (self.output / "hd.dump").write_bytes(b"changed archive")
        with self.assertRaisesRegex(MOD.MaintenanceError, "DATABASE_DUMP_CHECKSUM_MISMATCH"):
            MOD.restore_isolated(self.fence, self.output, runner=self.runner)
        self.assertFalse(self.calls)
        self.assertTrue((self.output / "INCOMPLETE").is_file())

    def test_actual_restore_failure_keeps_hold_and_never_returns_verified(self):
        def failed(argv, **kwargs):
            result = self.runner(argv, **kwargs)
            if "pg_restore" in argv:
                raise MOD.MaintenanceError("INJECTED_RESTORE_FAILURE")
            return result
        with self.assertRaisesRegex(MOD.MaintenanceError, "INJECTED_RESTORE_FAILURE"):
            MOD.restore_isolated(self.fence, self.output, runner=failed)
        self.assertTrue((self.output / "INCOMPLETE").is_file())
        self.assertFalse((self.output / "restore.json").exists())

    def test_wrong_network_or_host_mount_never_executes_restore_or_removes_foreign_container(self):
        for mutation in (lambda detail: detail["HostConfig"].update(NetworkMode="bridge"),
                         lambda detail: detail.update(Mounts=[{"Type": "bind", "Source": "/"}]),
                         lambda detail: detail.update(Id="f" * 64)):
            self.calls.clear()
            def tampered(argv, **kwargs):
                result = self.runner(argv, **kwargs)
                if docker_command(argv)[:2] == ["docker", "inspect"]:
                    details = json.loads(result); mutation(details[0]); return json.dumps(details)
                return result
            with self.subTest(mutation=mutation), self.assertRaises(MOD.MaintenanceError):
                MOD.restore_isolated(self.fence, self.output, runner=tampered)
            self.assertFalse(any("pg_restore" in call or call[:2] == ["docker", "rm"]
                                 for call, _ in self.calls))
            self.assertTrue((self.output / "INCOMPLETE").is_file())

    def test_success_is_isolated_restore_receipt_not_live_financial_authority(self):
        receipt = MOD.restore_isolated(self.fence, self.output, runner=self.runner)
        self.assertTrue(receipt["both_financial_censuses_match"])
        for key in ("production_state_restored", "off_host_copy_verified",
                    "independent_witness_attested", "financial_release_authorized"):
            self.assertFalse(receipt[key])
        run = next(call for call, _ in self.calls if call[:2] == ["docker", "run"])
        self.assertIn("--network=none", run)
        self.assertIn("--pull=never", run)
        self.assertIn("--cap-drop=ALL", run)
        self.assertIn("--mount", run)
        mount = run[run.index("--mount") + 1]
        self.assertEqual(mount, "type=bind,src=" + str(self.scratch) +
                         ",dst=/var/lib/postgresql/data,bind-propagation=rprivate")
        self.assertNotIn("/var/lib/postgresql/data:rw,noexec", " ".join(run))
        self.assertIn("--memory=2g", run)
        self.assertFalse(any("PGPASSWORD" in str(call) or "DATABASE_URL" in str(call) for call, _ in self.calls))
        restores = [call for call, _ in self.calls if "pg_restore" in call]
        self.assertEqual(len(restores), 2)
        self.assertTrue(all("--exit-on-error" in call and "--single-transaction" in call for call in restores))

    def test_final_backup_import_requires_verified_restore_scope_and_unchanged_manifest(self):
        MOD.restore_isolated(self.fence, self.output, runner=self.runner)
        path = self.output / "restore.json"
        original = json.loads(path.read_bytes())
        result = MOD.verify_current_backup(path, MOD.scope_digest(), MOD.file_sha(self.fence))
        self.assertTrue(result["isolated_restore_verified"])
        self.assertFalse(result["independent_witness_attested"])
        self.assertFalse(result["financial_release_authorized"])
        for field, value in (("scope_sha256", "f" * 64), ("isolated_restore_verified", False),
                             ("both_financial_censuses_match", False), ("network", "bridge")):
            changed = dict(original, **{field: value}); path.write_bytes(MOD.canonical(changed))
            with self.subTest(field=field), self.assertRaises(MOD.MaintenanceError):
                MOD.verify_current_backup(path, MOD.scope_digest(), MOD.file_sha(self.fence))
        path.write_bytes(MOD.canonical(original))
        with self.assertRaisesRegex(MOD.MaintenanceError, "FINAL_ISOLATED_RESTORE_RECEIPT_REQUIRED"):
            MOD.verify_current_backup(self.output / "backup.json", MOD.scope_digest(), MOD.file_sha(self.fence))
        changed = dict(self.manifest, extra="changed after restore")
        (self.output / "backup.json").write_bytes(MOD.canonical(changed))
        with self.assertRaisesRegex(MOD.MaintenanceError, "ISOLATED_BACKUP_AUTHORITY_UNVERIFIED"):
            MOD.verify_current_backup(path, MOD.scope_digest(), MOD.file_sha(self.fence))


class BackupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name); self.backups = self.root / "backups"; self.backups.mkdir()
        self.output = self.backups / "new-capture"
        self.fence = self.root / "fence.json"; self.fence.write_bytes(b"synthetic fence")
        self.snapshot_root = self.root / "settlement"; self.snapshot = self.snapshot_root / "new-snapshot"
        (self.snapshot / "proof").mkdir(parents=True)
        (self.snapshot / "proof/RECEIPT.txt").write_bytes(b"synthetic snapshot receipt")
        volume = settlement_fixture(self.root, self.snapshot)
        self.permit = valid_permit()
        self.census = {"tables": {"claims": {"rows": "947", "sha256": "a" * 64}}}
        self.calls = []
        self.stack = ExitStack(); self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(MOD, "BACKUPS", self.backups))
        self.stack.enter_context(patch.object(MOD, "VOLUME", volume))
        self.stack.enter_context(patch.object(MOD, "clock", return_value=NOW))
        self.stack.enter_context(patch.object(MOD, "write_new", side_effect=synthetic_private_write))
        self.stack.enter_context(patch.object(MOD, "SNAPSHOT_ROOT", self.snapshot_root))
        self.stack.enter_context(patch.object(MOD, "verify_current_fence", return_value={"permit": self.permit}))
        self.stack.enter_context(patch.object(MOD, "pg_environment", return_value={"PGDATABASE": "synthetic"}))
        self.stack.enter_context(patch.object(MOD, "financial_census", return_value=self.census))
        self.stack.enter_context(patch.object(MOD.os.path, "ismount", return_value=True))
        self.stack.enter_context(patch.object(MOD.os, "statvfs", return_value=type("Capacity", (), {
            "f_bavail": 1 << 30, "f_frsize": 4096})()))

    def runner(self, argv, **kwargs):
        self.calls.append((list(argv), kwargs))
        if argv[0] == "bash":
            return "PASS private two-service snapshot completed at " + str(self.snapshot) + "\n"
        if argv[0] == "pg_dump":
            Path(argv[argv.index("--file") + 1]).write_bytes(b"synthetic full custom archive")
            return ""
        raise AssertionError("Unreviewed backup subprocess: " + str(argv))

    def test_backup_stays_incomplete_until_actual_isolated_restore(self):
        value = MOD.backup(self.fence, self.output, runner=self.runner)
        self.assertTrue((self.output / "INCOMPLETE").is_file())
        self.assertTrue((self.output / "backup.json").is_file())
        for key in ("isolated_restore_verified", "off_host_copy_verified", "financial_release_authorized"):
            self.assertFalse(value[key])
        self.assertEqual(set(value["databases"]), {"hd", "de"})
        dumps = [(call, kwargs) for call, kwargs in self.calls if call[0] == "pg_dump"]
        self.assertEqual(len(dumps), 2)
        self.assertTrue(all("--format=custom" in call and kwargs["file_limit"] > 0 for call, kwargs in dumps))

    def test_cross_database_change_rejects_even_when_each_individual_dump_was_stable(self):
        calls = 0
        def census(*args):
            nonlocal calls
            calls += 1
            return {"changed": True} if calls == 5 else self.census
        with patch.object(MOD, "financial_census", side_effect=census):
            with self.assertRaisesRegex(MOD.MaintenanceError, "CROSS_DATABASE_QUIESCENCE_LOST"):
                MOD.backup(self.fence, self.output, runner=self.runner)
        self.assertTrue((self.output / "INCOMPLETE").is_file())
        self.assertFalse((self.output / "backup.json").exists())

    def test_unverified_settlement_snapshot_prevents_any_database_dump(self):
        (self.snapshot / "INCOMPLETE").write_bytes(b"failed snapshot")
        with self.assertRaisesRegex(MOD.MaintenanceError, "SETTLEMENT_SNAPSHOT_UNVERIFIED"):
            MOD.backup(self.fence, self.output, runner=self.runner)
        self.assertFalse(any(call[0] == "pg_dump" for call, _ in self.calls))
        self.assertTrue((self.output / "INCOMPLETE").is_file())

    def test_changed_adjacent_snapshot_helper_is_never_executed(self):
        original_read = Path.read_bytes
        def changed(path):
            return b"#!/bin/bash\nexit 0\n" if path.name == "settlement-dual-service-snapshot.sh" else original_read(path)
        with patch.object(Path, "read_bytes", changed):
            with self.assertRaises(MOD.MaintenanceError):
                MOD.backup(self.fence, self.output, runner=self.runner)
        self.assertFalse(self.calls)
        self.assertTrue((self.output / "INCOMPLETE").is_file())

    def test_capacity_refusal_happens_before_any_new_backup_directory(self):
        with patch.object(MOD.os, "statvfs", return_value=type("Capacity", (), {"f_bavail": 0, "f_frsize": 4096})()):
            with self.assertRaisesRegex(MOD.MaintenanceError, "BACKUP_CAPACITY_INSUFFICIENT"):
                MOD.backup(self.fence, self.output, runner=self.runner)
        self.assertFalse(self.output.exists())
        self.assertFalse(self.calls)


class CliTests(unittest.TestCase):
    def test_global_cutover_lock_contention_blocks_before_any_operation(self):
        with tempfile.TemporaryDirectory() as temp, ExitStack() as stack:
            lock = Path(temp) / "held.lock"; lock.write_bytes(b"already held by paired controller")
            stack.enter_context(patch.object(MOD, "LOCK", lock))
            stack.enter_context(patch.object(MOD.os, "geteuid", return_value=0))
            mutation = stack.enter_context(patch.object(MOD, "fence", side_effect=AssertionError("must not enter")))
            stack.enter_context(patch.object(MOD, "run", side_effect=AssertionError("must not run")))
            printed = stack.enter_context(patch("builtins.print"))
            with lock.open("a") as held:
                MOD.fcntl.flock(held, MOD.fcntl.LOCK_EX | MOD.fcntl.LOCK_NB)
                self.assertEqual(MOD.main(["--mode", "fence", "--permit", "/etc/synthetic-only.json",
                                           "--fence-receipt", "/root/synthetic-only.json"]), 2)
            mutation.assert_not_called()
            self.assertEqual(lock.read_bytes(), b"already held by paired controller")
            result = json.loads(printed.call_args.args[0])
            self.assertEqual(result["status"], "BLOCKED")
            self.assertTrue(result["hold_must_remain"])

    def test_default_scope_is_nonmutating_and_not_success_authority(self):
        with patch.object(MOD, "run", side_effect=AssertionError("no child allowed")), \
             patch.object(MOD, "write_new", side_effect=AssertionError("no writes allowed")), \
             patch("builtins.print") as printed:
            self.assertEqual(MOD.main([]), 3)
        value = json.loads(printed.call_args.args[0])
        self.assertFalse(value["activation_or_resume_authorized"])


@unittest.skipUnless(os.environ.get("RUN_WOLO_ISOLATED_RESTORE_TESTS") == "1",
                     "explicit local-only Docker restore opt-in required")
class ActualIsolatedRestoreTests(unittest.TestCase):
    def test_real_pg_archives_restore_with_constraints_sequences_and_corruption_refusal(self):
        """Actual PostgreSQL, pg_dump, pg_restore, SQL hashes and container guards.

        The sole mocked authority is synthetic protected host/fence I/O. This
        never invokes systemd, accesses live databases, or mounts host paths.
        """
        image = os.environ.get("WOLO_RESTORE_TEST_IMAGE", "")
        self.assertRegex(image, r"\Apostgres@sha256:[0-9a-f]{64}\Z")
        self.assertEqual(MOD.DOCKER, ["docker", "--host=unix:///var/run/docker.sock"])
        self.assertTrue(MOD.run(MOD.DOCKER + ["info", "--format", "{{.ServerVersion}}"] ).strip())
        name = "wolo-restore-test-only-" + secrets.token_hex(12)
        container = MOD.run(MOD.DOCKER + ["run", "--detach", "--pull=never", "--name", name,
            "--network=none", "--read-only", "--cap-drop=ALL", "--security-opt=no-new-privileges",
            "--user=999:999", "--pids-limit=128", "--memory=1g", "--cpus=2",
            "--tmpfs", "/var/lib/postgresql/data:rw,noexec,nosuid,size=1073741824,mode=1777",
            "--tmpfs", "/var/run/postgresql:rw,noexec,nosuid,size=16777216,mode=1777",
            "--env=PGDATA=/var/lib/postgresql/data/isolated",
            "--env=POSTGRES_HOST_AUTH_METHOD=trust", image,
            "postgres", "-c", "max_prepared_transactions=16"]).strip()
        self.assertRegex(container, r"\A[0-9a-f]{64}\Z")
        self.addCleanup(MOD.run, MOD.DOCKER + ["rm", "--force", container])
        prefix = MOD.DOCKER + ["exec", "--interactive", "--user=999:999", container]
        until = time.monotonic() + 30
        while True:
            try:
                MOD.require(MOD.run(prefix + ["cat", "/proc/1/comm"], timeout=3).strip() == "postgres",
                            "FIXTURE_POSTGRES_STILL_INITIALIZING")
                MOD.run(prefix + ["pg_isready", "--host=/var/run/postgresql", "--username=postgres"], timeout=3)
                break
            except MOD.MaintenanceError:
                self.assertLess(time.monotonic(), until, "fixture PostgreSQL startup failed")
                time.sleep(0.25)

        def sql(db, statement, user="postgres"):
            return MOD.run(prefix + ["psql", "--quiet", "--host=/var/run/postgresql", "--username=" + user,
                "--dbname=" + db, "--no-psqlrc", "--tuples-only", "--no-align", "--set=ON_ERROR_STOP=1"],
                input=statement, timeout=60).strip()

        with tempfile.TemporaryDirectory() as temp, ExitStack() as stack:
            # Only host protected-file ownership is synthetic; the catalog
            # policy executes the actual pinned observer and actual psql.
            stack.enter_context(patch.object(MOD, "private_read", side_effect=lambda path, *args: Path(path).read_bytes()))
            root = Path(temp); output = root / "backup"; output.mkdir()
            fence = root / "fence.json"; fence.write_bytes(b"SYNTHETIC TEST AUTHORITY; NEVER LIVE")
            (output / "INCOMPLETE").write_bytes(b"actual isolated fixture not yet restored")
            snapshot = root / "snapshot"; volume = settlement_fixture(root, snapshot)
            permit = valid_permit(now=MOD.clock()); permit["restore_image"] = image
            permit["max_total_bytes"] = 64 << 20
            censuses, dumps = {}, {}
            for lane in ("hd", "de"):
                db = "test_" + lane
                MOD.run(prefix + ["createdb", "--host=/var/run/postgresql", "--username=postgres", db])
                sql(db, "CREATE TABLE claims(id bigserial PRIMARY KEY, amount bigint NOT NULL CHECK(amount>=0), "
                    "state text NOT NULL CHECK(state IN ('held','pending'))); "
                    "CREATE TABLE payments(id bigserial PRIMARY KEY, claim_id bigint NOT NULL UNIQUE REFERENCES claims(id), "
                    "amount bigint NOT NULL CHECK(amount>0)); "
                    "INSERT INTO claims(amount,state) VALUES(300000000,'held'),(100000000,'pending'); "
                    "INSERT INTO payments(claim_id,amount) VALUES(2,100000000);")
                major = int(sql(db, "SHOW server_version_num;")) // 10000
                permit["databases"][lane]["postgres_major"] = major
                def actual_census_runner(argv, **kwargs):
                    self.assertEqual(argv[0], "psql")
                    return sql(db, "SET default_transaction_read_only=on; SET timezone='UTC';\n" + kwargs["input"])
                if lane == "hd":
                    sql(db, "CREATE ROLE wolo_hidden_writer LOGIN; CREATE ROLE wolo_no_stats LOGIN;")
                    writer = subprocess.Popen(prefix + ["psql", "--quiet", "--host=/var/run/postgresql",
                        "--username=wolo_hidden_writer", "--dbname=" + db, "--no-psqlrc",
                        "--command=SELECT pg_sleep(60);"], stdin=subprocess.DEVNULL,
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    try:
                        until = time.monotonic() + 5
                        while sql(db, "SELECT count(*) FROM pg_catalog.pg_stat_activity "
                                       "WHERE usename='wolo_hidden_writer';") == "0":
                            self.assertIsNone(writer.poll(), "disposable writer unexpectedly exited")
                            self.assertLess(time.monotonic(), until, "disposable writer failed to connect")
                            time.sleep(0.05)
                        self.assertGreater(int(sql(db, "SELECT count(*) FROM pg_catalog.pg_stat_activity "
                            "WHERE datname=current_database() AND pid<>pg_backend_pid() "
                            "AND backend_type IS NULL;", user="wolo_no_stats")), 0)
                        def low_census_runner(argv, **kwargs):
                            return sql(db, "SET default_transaction_read_only=on;\n" + kwargs["input"],
                                       user="wolo_no_stats")
                        with self.assertRaisesRegex(MOD.MaintenanceError, "DATABASE_NOT_EXCLUSIVELY_QUIESCED"):
                            MOD.financial_census(permit["databases"][lane], {}, low_census_runner)
                        # Full monitoring privilege reveals the active writer;
                        # visibility alone never authorizes a backup.
                        sql(db, "GRANT pg_read_all_stats TO wolo_no_stats;")
                        with self.assertRaisesRegex(MOD.MaintenanceError, "DATABASE_NOT_EXCLUSIVELY_QUIESCED"):
                            MOD.financial_census(permit["databases"][lane], {}, low_census_runner)
                    finally:
                        sql(db, "SELECT pg_terminate_backend(pid) FROM pg_catalog.pg_stat_activity "
                                "WHERE usename='wolo_hidden_writer';")
                        writer.wait(timeout=5)
                    # This survives disconnect and has no active writer to
                    # count. The shared validator must reject the prepared debt.
                    sql(db, "BEGIN; SELECT 1; PREPARE TRANSACTION 'wolo_fixture_prepared';")
                    try:
                        with self.assertRaisesRegex(MOD.MaintenanceError, "DATABASE_NOT_EXCLUSIVELY_QUIESCED"):
                            MOD.financial_census(permit["databases"][lane], {}, actual_census_runner)
                    finally:
                        sql(db, "ROLLBACK PREPARED 'wolo_fixture_prepared';")
                censuses[lane] = MOD.financial_census(permit["databases"][lane], {}, actual_census_runner)
                archive = output / (lane + ".dump")
                with archive.open("xb") as stream:
                    result = subprocess.run(prefix + ["pg_dump", "--host=/var/run/postgresql", "--username=postgres",
                        "--format=custom", "--dbname=" + db], stdin=subprocess.DEVNULL, stdout=stream,
                        stderr=subprocess.PIPE, timeout=60, check=False)
                self.assertEqual(result.returncode, 0, "isolated fixture dump failed")
                self.assertGreater(archive.stat().st_size, 0)
                self.assertLess(archive.stat().st_size, 1 << 20)
                dumps[lane] = {"sha256": MOD.file_sha(archive), "bytes": archive.stat().st_size}
            manifest = {"scope_sha256": MOD.scope_digest(), "fence_receipt_sha256": MOD.file_sha(fence),
                "isolated_restore_verified": False, "settlement_snapshot": str(snapshot),
                "settlement_snapshot_receipt_sha256": MOD.file_sha(snapshot / "proof/RECEIPT.txt"),
                "databases": dumps, "financial_censuses": censuses}
            (output / "backup.json").write_bytes(MOD.canonical(manifest))
            stack.enter_context(patch.object(MOD, "BACKUPS", root))
            stack.enter_context(patch.object(MOD, "VOLUME", volume))
            stack.enter_context(patch.object(MOD, "verify_current_fence", return_value={"permit": permit}))
            stack.enter_context(patch.object(MOD, "private_json", side_effect=lambda path: (
                json.loads(Path(path).read_bytes()), MOD.file_sha(path))))
            stack.enter_context(patch.object(MOD, "write_new", side_effect=synthetic_private_write))
            # The real Docker integration fixture uses a disposable temp bind
            # because CI runners cannot provision protected root-owned VPS
            # scratch. Admission/ownership guards remain tested separately.
            generated_pgdata = []
            def remove_ci_scratch(path):
                # CI runner cannot traverse PostgreSQL-created UID 999,
                # mode-0700 directories. Restrict sudo cleanup to exact
                # disposable test children under this unique /tmp root.
                self.assertEqual(path.parent, root)
                self.assertRegex(path.name, r"\\Afixture-pgdata-[0-9]+\\Z")
                cleaned = subprocess.run(
                    ["sudo", "-n", "/usr/bin/rm", "-rf", "--", str(path)],
                    capture_output=True, timeout=15, check=False)
                self.assertEqual(cleaned.returncode, 0, "CI fixture cleanup failed")
            def make_ci_scratch(_budget):
                path = root / ("fixture-pgdata-" + str(len(generated_pgdata)))
                path.mkdir()
                path.chmod(0o777)
                generated_pgdata.append(path)
                stack.callback(remove_ci_scratch, path)
                return path
            stack.enter_context(patch.object(MOD, "make_restore_scratch",
                                             side_effect=make_ci_scratch))
            stack.enter_context(patch.object(MOD, "cleanup_restore_scratch",
                                             side_effect=remove_ci_scratch))
            # Corrupt but rehashed archive reaches actual pg_restore, which must
            # refuse; recomputing checksum must not launder invalid archive bytes.
            original = (output / "hd.dump").read_bytes()
            (output / "hd.dump").write_bytes(b"not a PostgreSQL custom archive")
            manifest["databases"]["hd"]["sha256"] = MOD.file_sha(output / "hd.dump")
            (output / "backup.json").write_bytes(MOD.canonical(manifest))
            with self.assertRaises(MOD.MaintenanceError):
                MOD.restore_isolated(fence, output)
            self.assertTrue((output / "INCOMPLETE").exists())
            self.assertFalse((output / "restore.json").exists())
            (output / "hd.dump").write_bytes(original)
            manifest["databases"]["hd"]["sha256"] = MOD.file_sha(output / "hd.dump")
            (output / "backup.json").write_bytes(MOD.canonical(manifest))
            receipt = MOD.restore_isolated(fence, output)
            self.assertTrue(receipt["both_financial_censuses_match"])
            self.assertFalse(receipt["financial_release_authorized"])
            self.assertFalse(receipt["independent_witness_attested"])
            self.assertFalse((output / "INCOMPLETE").exists())


if __name__ == "__main__":
    unittest.main()

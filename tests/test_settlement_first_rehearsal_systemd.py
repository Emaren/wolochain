"""Actual systemd/SIGKILL mechanics on an explicitly disposable Linux CI VM.

No production root/test-path override exists in the controller. This fixture
uses only its watchdog mode and deliberately has NO recovery permit, chain,
keyring, settlement executable, live producer fence or financial certification.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import uuid

ROOT = Path(__file__).resolve().parents[1]
ENABLED = (sys.platform.startswith("linux") and os.geteuid() == 0 and
           os.environ.get("CI") == "true" and os.environ.get("WOLO_DISPOSABLE_SYSTEMD_TEST") == "1")


@unittest.skipUnless(ENABLED, "requires explicit disposable root Linux/systemd CI authorization")
class DisposableSystemdWatchdog(unittest.TestCase):
    def command(self, *args):
        return subprocess.check_output(args, text=True, stderr=subprocess.STDOUT, timeout=20).strip()

    def require_disposable_host(self):
        self.assertFalse(Path("/mnt/HC_Volume_105319120").exists(), "production volume detected")
        self.assertTrue(Path("/run/systemd/system").is_dir(), "no real systemd manager")
        for unit in ("wolochaind-mainnet.service", "wolochain-mainnet-settlement.service",
                     "wolochain-founder-rewards-settlement.service"):
            state = subprocess.run(["systemctl", "show", "--property=LoadState", "--value", unit],
                                   text=True, capture_output=True, timeout=10)
            self.assertIn(state.stdout.strip(), ("not-found", ""), "production unit detected")
        for port in (8092, 8093):
            with socket.socket() as probe:
                probe.settimeout(.2)
                self.assertNotEqual(probe.connect_ex(("127.0.0.1", port)), 0, "protected listener detected")

    def test_actual_custom_units_cannot_reactivate_while_owned_hold_exists(self):
        self.require_disposable_host()
        spec = importlib.util.spec_from_file_location("disposable_actual_fence",
                                                     ROOT / "scripts/settlement_financial_maintenance.py")
        maintenance = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(maintenance)
        self.assertFalse(maintenance.HOLD.parent.exists(), "pre-existing maintenance state")
        fragments = {}
        for unit in maintenance.UNITS:
            state = subprocess.run(["systemctl", "show", "--property=LoadState", "--value", unit],
                                   text=True, capture_output=True, timeout=10)
            self.assertEqual(state.stdout.strip(), "not-found", "pre-existing producer unit")
            self.assertFalse((maintenance.SYSTEMD / unit).exists())
            self.assertFalse((maintenance.SYSTEMD / (unit + ".d")).exists())
        with tempfile.TemporaryDirectory(prefix="wolo-16-unit-fixture-", dir="/var/lib") as temp:
            fixture = Path(temp)
            permit_path, receipt_path = fixture / "TEST-ONLY-permit.json", fixture / "fence.json"
            now = maintenance.clock()
            from datetime import timedelta
            permit = {"schema": maintenance.SCHEMA, "action": "fence-backup-isolated-restore",
                "scope_sha256": maintenance.scope_digest(),
                "tool_sha256": maintenance.digest(Path(maintenance.__file__).read_bytes()),
                "packet_sha256": "1" * 64, "procedure_sha256": "2" * 64,
                "not_before": (now - timedelta(seconds=1)).isoformat().replace("+00:00", "Z"),
                "expires_at": (now + timedelta(minutes=20)).isoformat().replace("+00:00", "Z"),
                "approval_refs": {role: {"identity": "CI-TEST-ONLY-" + role,
                    "approval_sha256": maintenance.digest(role.encode())} for role in maintenance.ROLE_NAMES},
                "attestations": dict.fromkeys(maintenance.ATTESTATIONS, True), "max_total_bytes": 1 << 20,
                "databases": {lane: {"env_path": "/etc/CI-TEST-ONLY/" + lane + ".env",
                    "env_sha256": maintenance.digest(lane.encode()),
                    "database_sha256": maintenance.digest(("CI-TEST-ONLY-" + lane).encode()),
                    "financial_tables": ["test_only_claims"], "postgres_major": 16} for lane in ("hd", "de")},
                "restore_image": "postgres@sha256:" + "a" * 64}
            # Structural fixtures in a deliberately empty CI host; no actual
            # finance reviewer, backup, database or production approval claimed.
            maintenance.write_new(permit_path, maintenance.canonical(permit))
            try:
                for unit in maintenance.UNITS:
                    if unit.endswith(".timer"):
                        raw = ("[Unit]\nDescription=TEST ONLY disposable financial gate timer\n"
                               "[Timer]\nOnActiveSec=24h\nUnit=" + unit.replace(".timer", ".service") + "\n")
                    else:
                        command = ("/usr/bin/sleep 90" if unit in maintenance.APPS else
                                   "/usr/bin/touch " + str(fixture / (unit + ".ran")))
                        raw = ("[Unit]\nDescription=TEST ONLY disposable financial gate service\n"
                               "[Service]\nType=" + ("simple" if unit in maintenance.APPS else "oneshot") +
                               "\nExecStart=" + command + "\n")
                    path = maintenance.SYSTEMD / unit
                    with path.open("x") as output:
                        output.write(raw)
                    fragments[path] = raw.encode()
                self.command("systemctl", "daemon-reload")
                for unit in maintenance.APPS:
                    self.command("systemctl", "start", unit)
                deadline = time.monotonic() + 10
                while True:
                    try:
                        maintenance.no_jobs(maintenance.run)
                        break
                    except maintenance.MaintenanceError:
                        self.assertLess(time.monotonic(), deadline, "queued/unknown systemd jobs prevent safe fixture")
                        time.sleep(.1)
                original_run = maintenance.run
                def traced_fixture_command(argv, **kwargs):
                    try:
                        return original_run(argv, **kwargs)
                    except maintenance.MaintenanceError:
                        # Fixture-only systemd argv contains no credentials;
                        # production runner continues to suppress argv/stderr.
                        print("DISPOSABLE_FAILED_SYSTEMD_COMMAND=" + json.dumps(argv))
                        raise
                maintenance.run = traced_fixture_command
                self.assertEqual(maintenance.main(["--mode", "fence", "--permit", str(permit_path),
                    "--fence-receipt", str(receipt_path)]), 0)
                before = maintenance.digest(maintenance.private_read(maintenance.HOLD))
                for unit in maintenance.UNITS:
                    # Real manual starts against custom /etc unit fragments.
                    self.command("systemctl", "start", unit)
                    self.assertEqual(self.command("systemctl", "show", "--property=ActiveState", "--value", unit),
                                     "inactive")
                    maintenance.effective_condition(unit, maintenance.run)
                result = maintenance.verify_current_fence(receipt_path, maintenance.scope_digest())
                self.assertEqual(len(result["units"]), 16)
                self.assertFalse(result["resume_authorized"])
                self.assertEqual(maintenance.digest(maintenance.private_read(maintenance.HOLD)), before)
                self.assertFalse(list(fixture.glob("*.ran")))
                print(json.dumps({"scope": "DISPOSABLE_ACTUAL_16_UNIT_ACTIVATION_ONLY",
                    "actual_custom_etc_conditions_verified": 16, "manual_reactivation_denied": 16,
                    "actual_live_producer_isolation_certified": False, "production_authorized": False}))
            finally:
                # Cleanup is ONLY the prechecked, newly created CI fixtures.
                # There is intentionally no analogous production resume mode.
                for unit in maintenance.UNITS:
                    subprocess.run(["systemctl", "stop", unit], capture_output=True, timeout=20)
                for path, raw in fragments.items():
                    gate = maintenance.dropin(path.name)
                    if gate.exists():
                        self.assertEqual(gate.read_bytes(), maintenance.expected_dropin())
                        gate.unlink()
                        gate.parent.rmdir()
                    self.assertEqual(path.read_bytes(), raw, "foreign fixture replacement; preserve evidence")
                    path.unlink()
                if maintenance.HOLD.exists():
                    self.assertEqual(maintenance.HOLD.read_bytes(), maintenance.canonical({
                        "scope_sha256": maintenance.scope_digest(),
                        "permit_sha256": maintenance.digest(permit_path.read_bytes())}))
                    maintenance.HOLD.unlink()
                    maintenance.HOLD.parent.rmdir()
                self.command("systemctl", "daemon-reload")

    def test_watchdog_survives_controller_sigkill_and_requires_new_human_authority(self):
        self.require_disposable_host()
        execution = uuid.uuid4().hex
        controller_unit = f"wolo-rehearsal-fixture-controller-{execution}.service"
        watcher_unit = f"aoe2war-wolo-first-rehearsal-{execution}.service"
        with tempfile.TemporaryDirectory(prefix="wolo-systemd-fixture-", dir="/var/lib") as temporary:
            tools = Path(temporary)
            for filename in ("settlement-bdbce253-code-cutover.py", "settlement_financial_maintenance.py"):
                shutil.copyfile(ROOT / "scripts" / filename, tools / filename)
                (tools / filename).chmod(0o600)
            spec = importlib.util.spec_from_file_location("disposable_wolo_watchdog", tools / "settlement-bdbce253-code-cutover.py")
            source = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(source)
            now = source.datetime.now(source.timezone.utc)
            stamp = lambda value: value.isoformat().replace("+00:00", "Z")
            permit = {"schema": source.REHEARSAL_SCHEMA, "executionId": execution,
                "candidateRevision": source.REV, "candidateSha256": source.NEW_SHA,
                "originalSha256": source.OLD_SHA, "consensusSha256": source.NODE_SHA,
                "owner": "CI-FIXTURE-NOT-HUMAN", "operator": "CI-FIXTURE-NOT-OPERATOR",
                "recoveryWitness": "CI-FIXTURE-NOT-WITNESS",
                "approvalRefs": {key: hashlib.sha256(key.encode()).hexdigest() for key in
                    ("owner", "operator", "chainReviewer", "financeReviewer", "recoveryWitness")},
                "fenceReceiptPath": str(tools / "NO-FINANCIAL-FENCE.json"),
                "backupReceiptPath": str(tools / "NO-FINANCIAL-BACKUP.json"),
                "windowStartUtc": stamp(now - source.timedelta(seconds=5)),
                "windowEndUtc": stamp(now + source.timedelta(minutes=5)),
                "issuedAtUtc": stamp(now - source.timedelta(seconds=1)),
                "expiresAtUtc": stamp(now + source.timedelta(minutes=3)),
                "approval": source.REHEARSAL_APPROVAL,
                "witnessedControls": sorted(source.REHEARSAL_CONTROLS)}
            for key in ("packetSha256", "procedureSha256", "backupReceiptSha256", "fenceScopeSha256",
                        "fenceReceiptSha256"):
                permit[key] = hashlib.sha256(("CI-NONCERTIFYING-" + key).encode()).hexdigest()
            permit["toolSha256"] = source.sha_file(tools / "settlement-bdbce253-code-cutover.py")
            permit["fenceToolSha256"] = source.sha_file(tools / "settlement_financial_maintenance.py")
            source.REHEARSAL_ROOT.mkdir(mode=0o700, exist_ok=True)
            journal = source.REHEARSAL_ROOT / execution
            journal.mkdir(mode=0o700)
            path = journal / "session.json"
            try:
                self.command("systemd-run", "--unit=" + controller_unit, "--property=Type=exec",
                             "/usr/bin/python3", "-c", "import time; time.sleep(90)")
                pid = int(self.command("systemctl", "show", "--property=MainPID", "--value", controller_unit))
                identity = source.process_identity(pid)
                self.assertIsNotNone(identity)
                source.record_once(path, {"schema": "aoe2war.wolochain.rehearsal-session.v1",
                    "permit": permit, "permitPath": str(tools / "SYNTHETIC-NOT-AN-EXECUTION-PERMIT"),
                    "controllerIdentity": identity, "consensusPid": pid,
                    "createdAtUtc": stamp(source.datetime.now(source.timezone.utc)), "watchdogUnit": watcher_unit})
                session = source.load_session(path)
                # Real launch, readiness handshake, process/boot/InvocationID binding.
                source.start_watchdog(source.Live(), path, session)
                original_watcher = source.supervisor_identity(source.Live(), watcher_unit)
                fixture_state = journal / "TEST-ONLY-financial-state"
                fixture_state.write_bytes(b"accepted100:UNKNOWN;claim889:preserved;NO-RETRY\n")
                before = source.sha_file(fixture_state)
                self.command("systemctl", "kill", "--signal=KILL", controller_unit)
                deadline = time.monotonic() + 10
                while not (journal / "controller-lost.json").exists() and time.monotonic() < deadline:
                    time.sleep(.1)
                self.assertTrue((journal / "controller-lost.json").is_file())
                time.sleep(2)  # verify it remains supervised without automatically recovering
                self.assertEqual(source.supervisor_identity(source.Live(), watcher_unit), original_watcher)
                self.assertEqual(self.command("systemctl", "is-active", watcher_unit), "active")
                self.assertFalse((journal / "completed.json").exists())
                self.assertFalse(list(journal.glob("recovery-attempt-*.json")))
                self.assertEqual(source.sha_file(fixture_state), before)
                logs = self.command("journalctl", "-u", watcher_unit, "--no-pager", "--output=cat", "-n", "20")
                self.assertIn("HOLD_AWAITING_FRESH_HUMAN_RECOVERY_AUTHORITY", logs)
                print(json.dumps({"scope": "DISPOSABLE_SYSTEMD_SUPERVISION_ONLY",
                    "controller_sigkill_observed": True, "watchdog_survived": True,
                    "automatic_recovery_attempted": False, "financial_state_changed": False,
                    "actual_settlement_round_trip_tested": False,
                    "independent_financial_attestation": False, "production_authorized": False}))
            finally:
                for unit in (watcher_unit, controller_unit):
                    subprocess.run(["systemctl", "stop", unit], capture_output=True, timeout=20)
                    subprocess.run(["systemctl", "reset-failed", unit], capture_output=True, timeout=20)
                shutil.rmtree(journal)


if __name__ == "__main__":
    unittest.main()

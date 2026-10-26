"""Actual crypto + durable witness replay tests; disposable, NEVER production GO."""
import base64
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import settlement_solo_runtime as r
import settlement_solo_owner_intent_review as o
import settlement_maintenance_nonce_store as n
import settlement_financial_maintenance as m
import test_settlement_solo_owner_intent_review as intent_fixtures
from test_settlement_financial_maintenance import valid_permit

NOW = datetime(2026, 10, 26, 14, tzinfo=timezone.utc)
ISO = lambda t: t.strftime("%Y-%m-%dT%H:%M:%SZ")


class RuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Reuse the existing real disposable crypto fixture, not production keys.
        intent_fixtures.SoloOwnerIntentionTests.setUpClass()

    @classmethod
    def tearDownClass(cls):
        intent_fixtures.SoloOwnerIntentionTests.tearDownClass()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name).resolve()
        self.nonces = self.folder / "nonces"
        self.nonces.mkdir(mode=0o700)
        self.e = {"schema": o.ENROLL_SCHEMA, "owner_key_id": "actual-human-owner",
                  "public_key_pem": intent_fixtures.SoloOwnerIntentionTests.pem, "valid_from": ISO(NOW - timedelta(days=1)),
                  "valid_until": ISO(NOW + timedelta(days=1)), "revoked": False}
        self.c = {"schema": r.CONFIG_SCHEMA, "owner_enrollment_sha256": r.sha(o.canonical(self.e)),
                  "owner_der_sha256": intent_fixtures.SoloOwnerIntentionTests.der_hash, "source_commit": "a" * 40,
                  "host_identity_sha256": "b" * 64,
                  "controller_files": dict.fromkeys(r.SOURCES, "1" * 64),
                  "crypto": dict.fromkeys(("runtime", "witness"), {
                      "path": str(Path(shutil.which("openssl")).resolve()),
                      "sha256": r.sha(Path(shutil.which("openssl")).read_bytes())}),
                  "witness": {"host": "owner-witness.example", "user": "wolo_witness", "port": 22,
                    "identity_path": "/root/protected/ssh", "known_hosts_path": "/root/protected/known_hosts",
                    "known_hosts_sha256": r.sha(b"known hosts"), "host_identity_sha256": "c" * 64}}
        self.q = {"schema": r.SCHEMA, "chain_id": "wolo-1", "phase": "live_capture",
                  "operation": r.OPS["live_capture"], "source_commit": self.c["source_commit"],
                  "host_identity_sha256": self.c["host_identity_sha256"], "scope_sha256": "d" * 64,
                  "procedure_sha256": "e" * 64, "nonce": "f" * 32,
                  "not_before": ISO(NOW - timedelta(seconds=10)),
                  "expires_at": ISO(NOW + timedelta(minutes=20)),
                  "previous_phase_receipt_sha256": None}

    def signed(self, *, domain=r.DOMAIN, schema=r.PACKET_SCHEMA):
        raw = domain + o.canonical({"owner_key_id": self.e["owner_key_id"], "request": self.q})
        msg = self.folder / "message"
        msg.write_bytes(raw)
        sig = subprocess.run(["openssl", "pkeyutl", "-sign", "-rawin", "-inkey",
            str(intent_fixtures.SoloOwnerIntentionTests.private), "-in", str(msg)], check=True, capture_output=True).stdout
        return o.canonical({"schema": schema, "owner_key_id": self.e["owner_key_id"],
                            "request": deepcopy(self.q), "signature_b64": base64.b64encode(sig).decode()})

    def consume(self, packet=None, config=None):
        with patch.object(r, "host_identity", return_value="c" * 64):
            return r.consume_witness(self.c if config is None else config, o.canonical(self.e),
                self.signed() if packet is None else packet, nonce_root=self.nonces, now=NOW)

    def test_new_production_domain_real_signature_and_durable_consumption(self):
        packet = self.signed()
        ack = self.consume(packet)
        self.assertEqual(ack["packet_sha256"], r.sha(packet))
        self.assertTrue(ack["fresh_consumption_confirmed"])
        self.assertEqual(len(list(self.nonces.glob("nonce-*"))), 1)
        self.assertNotIn("financial_release_authorized", ack)
        with self.assertRaisesRegex(n.ReservationRefused, "NONCE_ALREADY_RESERVED"):
            self.consume(packet)

    def test_vps_rollback_does_not_remove_offhost_consumption(self):
        packet = self.signed()
        self.consume(packet)
        # Brand-new local ledger simulates complete VPS disk rollback.
        local = self.folder / "rolled-back-vps"
        local.mkdir(mode=0o700)
        with self.assertRaisesRegex(n.ReservationRefused, "NONCE_ALREADY_RESERVED"):
            self.consume(packet)
        self.assertFalse(list(local.iterdir()))

    def test_concurrent_witness_requests_exactly_one_can_be_admitted(self):
        packet = self.signed()
        def attempt(_):
            try:
                return r.consume_witness(self.c, o.canonical(self.e), packet,
                    nonce_root=self.nonces, now=NOW)["fresh_consumption_confirmed"]
            except n.ReservationRefused:
                return False
        with patch.object(r, "host_identity", return_value="c" * 64), ThreadPoolExecutor(max_workers=4) as pool:
            self.assertEqual(sum(pool.map(attempt, range(4))), 1)

    def test_offline_signature_cannot_be_relabelled_as_runtime_authority(self):
        packet = self.signed(domain=o.DOMAIN)
        with self.assertRaisesRegex(o.AuthorityHold, "INVALID_PUBLIC_KEY_OR_SIGNATURE"):
            self.consume(packet)
        self.assertEqual(list(self.nonces.iterdir()), [])

    def test_forged_revoked_wrong_host_source_or_funded_phase_never_burns_nonce(self):
        original = deepcopy(self.q)
        for field, bad in (("source_commit", "0" * 40), ("host_identity_sha256", "a" * 64),
                           ("phase", "funded_activate"), ("chain_id", "other-1")):
            self.q = dict(original, **{field: bad})
            with self.subTest(field=field), self.assertRaises(o.AuthorityHold):
                self.consume()
        self.q = original
        self.e["revoked"] = True
        self.c["owner_enrollment_sha256"] = r.sha(o.canonical(self.e))
        with self.assertRaisesRegex(o.AuthorityHold, "OWNER_PUBLIC_ENROLLMENT_INVALID"):
            self.consume()
        self.assertEqual(list(self.nonces.iterdir()), [])

    def test_pinned_absolute_openssl_ignores_untrusted_path_and_detects_drift(self):
        packet = self.signed()
        with patch.dict(os.environ, {"PATH": "/not-the-login-shell"}):
            self.assertTrue(self.consume(packet)["fresh_consumption_confirmed"])
        self.q["nonce"] = "1" * 32
        self.c["crypto"]["witness"] = dict(self.c["crypto"]["witness"], sha256="0" * 64)
        with self.assertRaisesRegex(o.AuthorityHold, "PINNED_OPENSSL_DRIFT"):
            self.consume()
        self.assertEqual(len(list(self.nonces.glob("nonce-*"))), 1)

    def test_owner_mac_witness_paths_preserve_canonical_no_symlink_policy(self):
        config, ledger = r.witness_paths("darwin")
        self.assertEqual(str(config), "/private/etc/wolochain-financial-maintenance/authority/solo-witness.json")
        self.assertTrue(str(ledger).startswith("/private/var/"))
        self.assertEqual(str(r.witness_paths("linux")[0]), "/etc/wolochain-financial-maintenance/authority/solo-witness.json")

    def test_rotated_fence_is_rejected_on_the_stable_parsed_read(self):
        with patch.object(m, "private_json", return_value=({}, "b" * 64)), \
             patch.object(m, "inactive_observation") as observed:
            with self.assertRaisesRegex(m.MaintenanceError, "SIGNED_FENCE_CHANGED_AT_USE"):
                m.verify_retained_fence(Path("/root/fence"), m.scope_digest(),
                                        expected_receipt_sha256="a" * 64)
            observed.assert_not_called()

    def test_manifest_rotation_after_initial_hash_is_rejected_at_parse(self):
        phase = {"phase": "offline_verify", "live_actions_allowed": False,
                 "max_total_bytes": 1 << 20, "not_before": ISO(NOW - timedelta(seconds=1)),
                 "expires_at": ISO(NOW + timedelta(minutes=1)),
                 "artifacts": {"fence_receipt_sha256": "a" * 64,
                               "backup_manifest_sha256": "a" * 64}}
        output = self.folder / "backup"
        output.mkdir()
        permit = valid_permit(now=NOW)
        with patch.object(m, "BACKUPS", self.folder), patch.object(m, "clock", return_value=NOW), \
             patch.object(m, "file_sha", return_value="a" * 64), \
             patch.object(m, "verify_retained_fence", return_value={"permit": permit}), \
             patch.object(m, "private_json", return_value=({}, "b" * 64)), patch.object(m, "run") as run:
            with self.assertRaisesRegex(m.MaintenanceError, "SIGNED_MANIFEST_CHANGED_AT_USE"):
                m.restore_isolated(Path("/root/fence"), output, phase_window=phase)
            run.assert_not_called()

    def test_same_host_witness_and_expired_window_are_refused(self):
        self.c["witness"]["host_identity_sha256"] = self.c["host_identity_sha256"]
        with self.assertRaisesRegex(o.AuthorityHold, "SEPARATELY_ENROLLED_WITNESS_REQUIRED"):
            r.load_config(o.canonical(self.c))
        self.c["witness"]["host_identity_sha256"] = "c" * 64
        with patch.object(r, "host_identity", return_value="b" * 64):
            with self.assertRaisesRegex(o.AuthorityHold, "WITNESS_NOT_SEPARATE_HOST"):
                r.consume_witness(self.c, o.canonical(self.e), self.signed(), nonce_root=self.nonces, now=NOW)
        self.q["expires_at"] = ISO(NOW)
        with self.assertRaisesRegex(o.AuthorityHold, "SOLO_RUNTIME_WINDOW_INVALID"):
            self.consume()

    def test_crash_partial_record_is_never_reused(self):
        packet = self.signed()
        self.consume(packet)
        record = next(self.nonces.glob("nonce-*"))
        record.write_bytes(b'{"partial":')
        with self.assertRaisesRegex(n.ReservationRefused, "NONCE_RECORD_CORRUPT"):
            self.consume(packet)

    def test_enrollment_expiring_inside_phase_is_refused_before_witness_write(self):
        self.e["valid_until"] = ISO(NOW + timedelta(minutes=1))
        self.c["owner_enrollment_sha256"] = r.sha(o.canonical(self.e))
        with self.assertRaisesRegex(o.AuthorityHold, "OWNER_ENROLLMENT_MUST_COVER_ENTIRE_PHASE"):
            self.consume()
        self.assertEqual(list(self.nonces.iterdir()), [])

    def test_rotated_permit_is_refused_before_any_fence_mutation(self):
        permit = valid_permit(now=NOW)
        # Structurally valid replacement still cannot use the original signature.
        with patch.object(m, "private_json", return_value=(permit, "b" * 64)), \
             patch.object(m, "write_new") as write, patch.object(m, "run") as run:
            with self.assertRaisesRegex(m.MaintenanceError, "SIGNED_PERMIT_CHANGED_BEFORE_FENCE"):
                m.fence(Path("/root/permit"), Path("/root/fence"), expected_permit_sha256="a" * 64)
            write.assert_not_called()
            run.assert_not_called()

    def test_rotated_sealed_archives_refused_before_restore_io(self):
        phase = {"artifacts": {"fence_receipt_sha256": "a" * 64,
                               "backup_manifest_sha256": "b" * 64}}
        with patch.object(m, "file_sha", return_value="c" * 64), patch.object(m, "run") as run:
            with self.assertRaisesRegex(m.MaintenanceError, "SIGNED_ARCHIVES_CHANGED_BEFORE_RESTORE"):
                m.restore_isolated(Path("/root/fence"), Path("/root/backup"), phase_window=phase)
            run.assert_not_called()

    def test_offline_restore_has_separate_long_window_and_prior_receipt(self):
        self.q.update(phase="offline_verify", operation=r.OPS["offline_verify"],
                      expires_at=ISO(NOW + timedelta(hours=3)), previous_phase_receipt_sha256="1" * 64)
        self.assertEqual(self.consume()["phase"], "offline_verify")
        self.q["nonce"] = "1" * 32
        self.q["expires_at"] = ISO(NOW + timedelta(hours=4))
        with self.assertRaisesRegex(o.AuthorityHold, "SOLO_RUNTIME_WINDOW_INVALID"):
            self.consume()

    def test_new_solo_permit_does_not_weaken_old_five_role_contract(self):
        permit = valid_permit(now=NOW)
        # Fixture loads its own maintenance module; bind to this module's source.
        permit["tool_sha256"] = m.digest(Path(m.__file__).read_bytes())
        permit["approval_refs"] = {"owner": permit["approval_refs"]["owner"]}
        with self.assertRaisesRegex(m.MaintenanceError, "FIVE_SCOPED_HUMAN_APPROVALS_REQUIRED"):
            m.validate_permit(permit, now=NOW)
        permit["schema"] = m.SOLO_SCHEMA
        self.assertEqual(m.validate_permit(permit, now=NOW), permit)
        permit["attestations"]["claim_889_preserved"] = False
        with self.assertRaisesRegex(m.MaintenanceError, "EXTERNAL_FENCES_UNATTESTED"):
            m.validate_permit(permit, now=NOW)

    def transport(self, packet, response, *, error=None):
        key = self.folder / "transport-key-placeholder"
        key.write_bytes(b"NOT A REAL KEY; transport is mocked")
        key.chmod(0o600)
        self.c["witness"]["identity_path"] = str(key)
        st = key.stat()
        # No SSH, secrets, or real machine is reached by this fixture.
        fake_stat = type("RootStat", (), {"st_mode": st.st_mode, "st_uid": 0, "st_nlink": 1})()
        real_lstat = Path.lstat
        def lstat(path):
            return fake_stat if path == key else real_lstat(path)
        with patch.object(m, "private_read", return_value=b"known hosts"), \
             patch.object(Path, "lstat", lstat), patch.object(m, "run", return_value=response, side_effect=error) as run:
            result = r.consume_remote(self.c, packet)
            args = run.call_args.args[0]
            self.assertIn("-oStrictHostKeyChecking=yes", args)
            self.assertIn("-oForwardAgent=no", args)
            self.assertEqual(args[-1], r.REMOTE_COMMAND)
            self.assertEqual(run.call_args.kwargs["timeout"], 10)
            return result

    def test_ssh_response_must_bind_exact_packet_phase_and_record(self):
        packet = self.signed()
        ack = self.consume(packet)
        self.assertEqual(self.transport(packet, o.canonical(ack).decode()), ack)
        for field, bad in (("packet_sha256", "1" * 64), ("request_sha256", "1" * 64),
                           ("record_sha256", "1" * 64), ("phase", "resume"),
                           ("witness_host_identity_sha256", "b" * 64),
                           ("fresh_consumption_confirmed", False)):
            with self.subTest(field=field), self.assertRaisesRegex(o.AuthorityHold, "WITNESS_CONSUMPTION_RESPONSE_INVALID"):
                self.transport(packet, o.canonical(dict(ack, **{field: bad})).decode())

    def test_remote_timeout_is_uncertain_and_never_retried(self):
        packet = self.signed()
        with self.assertRaisesRegex(o.AuthorityHold, "WITNESS_OUTCOME_UNCERTAIN"):
            self.transport(packet, "", error=m.MaintenanceError("BOUNDED_COMMAND_TIMEOUT"))


    def admission_fixture(self):
        from types import SimpleNamespace
        args = SimpleNamespace(mode="solo-capture", packet=Path("/root/packet"),
            procedure=Path("/root/procedure"), writer_inventory=Path("/root/writers"),
            permit=Path("/root/permit"), fence_receipt=Path("/root/fence"),
            output=m.BACKUPS / "synthetic-only", previous_review=None)
        permit = valid_permit(now=NOW)
        permit.update(schema=m.SOLO_SCHEMA, tool_sha256=m.digest(Path(m.__file__).read_bytes()),
                      not_before=self.q["not_before"], expires_at=self.q["expires_at"])
        self.q["scope_sha256"] = m.scope_digest()
        core = {k: v for k, v in permit.items()
                if k not in {"packet_sha256", "procedure_sha256", "approval_refs"}}
        observations = {"observation_path": "/root/observation", "observation_sha256": r.sha(b"fixture")}
        writers = {"schema": "wolo.solo-maintenance-writer-evidence.v1",
                   "writers": dict.fromkeys(r.WRITERS, observations)}
        proc = {"schema": r.PROCEDURE_SCHEMA, "mode": args.mode,
                "permit_core_sha256": r.sha(m.canonical(core)),
                "fence_receipt_path": str(args.fence_receipt), "output_path": str(args.output),
                "previous_phase_receipt_path": None,
                "runtime_binaries": dict.fromkeys(r.RUNTIME_UNITS, "1" * 64),
                "writer_inventory_sha256": r.sha(o.canonical(writers))}
        self.q["procedure_sha256"] = r.sha(o.canonical(proc))
        packet = self.signed()
        permit["packet_sha256"] = r.sha(packet)
        permit["procedure_sha256"] = self.q["procedure_sha256"]
        signed = o.parse(packet)
        permit["approval_refs"] = {"owner": {"identity": self.e["owner_key_id"],
            "approval_sha256": r.sha(base64.b64decode(signed["signature_b64"]))}}
        files = {r.CONFIG: o.canonical(self.c), r.ENROLLMENT: o.canonical(self.e),
                 args.packet: packet, args.procedure: o.canonical(proc),
                 args.writer_inventory: o.canonical(writers), Path("/root/observation"): b"fixture"}
        return args, permit, files

    def admit(self, args, permit, files, *, remote_error=None, runtime_effect=None):
        from contextlib import ExitStack
        local = self.folder / "local"
        local.mkdir(mode=0o700, exist_ok=True)
        with ExitStack() as stack:
            stack.enter_context(patch.object(m, "private_read", side_effect=lambda path, **_: files[Path(path)]))
            stack.enter_context(patch.object(m, "private_json", return_value=(permit, r.sha(o.canonical(permit)))))
            stack.enter_context(patch.object(m, "clock", return_value=NOW))
            frozen = stack.enter_context(patch.object(o, "datetime"))
            frozen.now.return_value = NOW
            frozen.strptime.side_effect = datetime.strptime
            stack.enter_context(patch.object(r, "source_check"))
            stack.enter_context(patch.object(r, "verify_runtime", side_effect=runtime_effect))
            stack.enter_context(patch.object(r, "NONCE_ROOT", local))
            remote = stack.enter_context(patch.object(r, "consume_remote", return_value={"fixture": True},
                                                     side_effect=remote_error))
            result = r.authenticate_and_reserve(args)
            return result, remote.call_count

    def test_prepare_emits_exact_unsigned_payload_without_consuming(self):
        args, _, files = self.admission_fixture()
        with patch.object(n, "reserve_once") as reserve, patch.object(r, "consume_remote") as remote:
            challenge = r.prepare(self.c, o.canonical(self.e), files[args.procedure],
                                  args.mode, now=NOW)
            self.assertEqual(challenge["status"], "UNSIGNED_NONAUTHORIZING")
            self.assertFalse(challenge["financial_release_authorized"])
            payload = base64.b64decode(challenge["signing_message_b64"], validate=True)
            self.assertEqual(payload, r.DOMAIN + o.canonical({"owner_key_id": self.e["owner_key_id"],
                                                            "request": challenge["request"]}))
            reserve.assert_not_called()
            remote.assert_not_called()
        self.assertEqual(list(self.nonces.iterdir()), [])

    def test_real_admission_consumes_remote_then_local_and_binds_every_input(self):
        args, permit, files = self.admission_fixture()
        result, calls = self.admit(args, permit, files)
        self.assertEqual(calls, 1)
        self.assertTrue(result["live_actions_allowed"])
        self.assertEqual(result["max_total_bytes"], permit["max_total_bytes"])
        self.assertEqual(len(list((self.folder / "local").glob("nonce-*"))), 1)
        self.assertNotIn("financial_release_authorized", result)

    def test_admission_tampering_or_missing_observation_precedes_nonce(self):
        args, permit, files = self.admission_fixture()
        for path in (args.procedure, Path("/root/observation")):
            changed = dict(files, **{})
            changed[path] = b'{}'
            with self.subTest(path=path), patch.object(r, "consume_remote") as remote:
                with self.assertRaises(o.AuthorityHold):
                    self.admit(args, permit, changed)
                remote.assert_not_called()
        self.assertFalse(list((self.folder / "local").iterdir()))

    def test_uncertain_offhost_consumption_does_not_burn_local_or_dispatch(self):
        args, permit, files = self.admission_fixture()
        with self.assertRaisesRegex(o.AuthorityHold, "WITNESS_OUTCOME_UNCERTAIN"):
            self.admit(args, permit, files, remote_error=o.AuthorityHold("WITNESS_OUTCOME_UNCERTAIN"))
        self.assertFalse(list((self.folder / "local").iterdir()))

    def test_expiry_during_final_runtime_io_consumes_but_refuses(self):
        args, permit, files = self.admission_fixture()
        calls = []
        def runtime(_):
            calls.append(True)
            if len(calls) == 2:
                # Simulate I/O finishing beyond the approval deadline.
                o.datetime.now.return_value = NOW + timedelta(hours=1)
        with self.assertRaisesRegex(o.AuthorityHold, "SOLO_RUNTIME_WINDOW_INVALID"):
            self.admit(args, permit, files, runtime_effect=runtime)
        self.assertEqual(len(list((self.folder / "local").glob("nonce-*"))), 1)

    def test_cli_dispatch_is_inside_original_lease_and_has_no_funded_path(self):
        import contextlib
        import io
        from types import SimpleNamespace
        lock = self.folder / "lock"
        # Only authority/filesystem boundaries are replaced. main's actual lease
        # and route dispatch run; the existing synthetic systemd suite covers I/O.
        raw = ["--mode", "solo-capture", "--packet", "/root/packet",
               "--procedure", "/root/procedure", "--writer-inventory", "/root/writers",
               "--permit", "/root/permit", "--fence-receipt", "/root/fence",
               "--output", "/root/backup", "--completion-receipt", str(self.folder / "complete")]
        actual_fstat = os.fstat
        def root_fstat(fd):
            st = actual_fstat(fd)
            return SimpleNamespace(st_mode=st.st_mode, st_uid=0, st_nlink=st.st_nlink)
        req = dict(self.q, live_actions_allowed=True, max_total_bytes=1 << 20,
                   witness_receipt={"synthetic": True}, artifacts={"permit_sha256": "2" * 64})
        with patch.object(m, "LOCK", lock), patch.object(m.os, "geteuid", return_value=0), \
             patch.object(m.os, "fstat", side_effect=root_fstat), patch.object(m, "clock", return_value=NOW), \
             patch.object(r, "authenticate_and_reserve", return_value=req) as admit, \
             patch.object(m, "fence", return_value={"synthetic": True}) as fence, patch.object(m, "backup") as backup, \
             patch.object(m, "file_sha", return_value="1" * 64), patch.object(m, "write_new") as write, \
             contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(m.main(raw), 0)
            admit.assert_called_once()
            fence.assert_called_once_with(Path("/root/permit"), Path("/root/fence"),
                                          expected_permit_sha256="2" * 64)
            backup.assert_called_once_with(Path("/root/fence"), Path("/root/backup"),
                                           expected_fence_sha256=m.digest(m.canonical({"synthetic": True})))
            receipt = json.loads(write.call_args.args[1])
            self.assertFalse(receipt["financial_release_authorized"])
            self.assertFalse(receipt["global_writers_fenced"])



if __name__ == "__main__":
    unittest.main()

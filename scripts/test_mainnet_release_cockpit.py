"""Offline contracts for the non-authorizing mainnet cockpit."""
from __future__ import annotations

import importlib.util
import json
import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

FILE = Path(__file__).with_name("mainnet-release-cockpit.py")
SPEC = importlib.util.spec_from_file_location("cockpit", FILE)
cockpit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cockpit)


class CockpitTests(unittest.TestCase):
    def service(self, sha, start="100"):
        def mocked(unit, names):
            return {
                "ActiveState": "active", "MainPID": "1012",
                "ExecMainStartTimestampMonotonic": start,
            }
        with patch.object(cockpit, "props", side_effect=mocked), patch.object(
            cockpit, "executable_digest", return_value=sha
        ):
            return cockpit.observe_service(
                "wolochain-mainnet-settlement.service", cockpit.HISTORICAL_SETTLEMENT
            )

    def test_matching_historical_is_not_certification(self):
        result = self.service(cockpit.HISTORICAL_SETTLEMENT)
        self.assertEqual(result["historicalComparison"], "MATCH_HISTORICAL")
        self.assertTrue(result["processStable"])

    def test_changed_digest_detected(self):
        self.assertEqual(
            self.service("f" * 64)["historicalComparison"],
            "DIFFERENT_FROM_HISTORICAL",
        )

    def test_unreadable_digest_is_unverified(self):
        self.assertEqual(self.service(None)["historicalComparison"], "UNVERIFIED")

    def test_pid_race_invalidates_digest(self):
        with patch.object(cockpit, "props", side_effect=[
            {"ActiveState": "active", "MainPID": "1012", "ExecMainStartTimestampMonotonic": "1"},
            {"ActiveState": "active", "MainPID": "1013", "ExecMainStartTimestampMonotonic": "2"},
        ]), patch.object(
            cockpit, "executable_digest", return_value=cockpit.HISTORICAL_SETTLEMENT
        ):
            result = cockpit.observe_service("x", cockpit.HISTORICAL_SETTLEMENT)
        self.assertEqual(result["historicalComparison"], "UNVERIFIED")
        self.assertIsNone(result["executableSha256"])

    def test_malformed_gate_index_fails_closed(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "gate.json"
            path.write_text("{bad json")
            self.assertTrue(
                all(x == "UNVERIFIED" for x in cockpit.read_gate_index(str(path)).values())
            )

    def test_receipts_private_and_existing_file_never_overwritten(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "witness.json"
            cockpit.write_new_receipt(str(target), '{"status":"HOLD"}\n')
            self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o600)
            self.assertEqual(target.read_text(), '{"status":"HOLD"}\n')
            with self.assertRaises(FileExistsError):
                cockpit.write_new_receipt(str(target), '{"status":"UNAUTHORIZED"}\n')
            self.assertEqual(target.read_text(), '{"status":"HOLD"}\n')

    def test_symlinked_input_cannot_be_treated_as_gate_evidence(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "real.json"
            alias = Path(folder) / "alias.json"
            target.write_text(json.dumps({
                "schema": "aoe2war.wolo.financial-release-checklist.v1",
                "controls": {x: {"status": "ATTESTED"} for x in cockpit.GATES},
            }))
            alias.symlink_to(target)
            self.assertEqual(
                set(cockpit.read_gate_index(str(alias)).values()), {"UNVERIFIED"}
            )
            with self.assertRaises(FileExistsError):
                cockpit.write_new_receipt(str(alias), '{"status":"BAD"}')
            self.assertIn('"ATTESTED"', target.read_text())

    def test_oversized_previous_evidence_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "oversized.json"
            path.write_bytes(b" " * (cockpit.MAX_RECEIPT_BYTES + 1))
            with self.assertRaises(ValueError):
                cockpit.load_bounded_json(str(path))

    def test_attested_index_does_not_authorize(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "gate.json"
            path.write_text(json.dumps({
                "schema": "aoe2war.wolo.financial-release-checklist.v1",
                "controls": {x: {"status": "ATTESTED"} for x in cockpit.GATES},
            }))
            with patch.object(cockpit, "command", return_value=cockpit.HISTORICAL_SOURCE), patch.object(
                cockpit, "observe_service", return_value={"historicalComparison": "MATCH_HISTORICAL"}
            ), patch.object(cockpit, "observe_timer", return_value={"activeState": "inactive"}):
                result = cockpit.assess(str(path))
        self.assertFalse(result["financialReleaseAuthorized"])
        self.assertFalse(result["custodyCertified"])
        self.assertFalse(result["mainnetCanaryAuthorized"])
        self.assertEqual(result["financialProducerIsolation"], "UNVERIFIED_NOT_CERTIFIED")

    def test_active_timer_proves_not_fenced(self):
        with patch.object(cockpit, "command", return_value=cockpit.HISTORICAL_SOURCE), patch.object(
            cockpit, "observe_service", return_value={"historicalComparison": "MATCH_HISTORICAL"}
        ), patch.object(cockpit, "observe_timer", return_value={"activeState": "active"}):
            result = cockpit.assess()
        self.assertEqual(result["financialProducerIsolation"], "NOT_FENCED")
        self.assertEqual(len(result["activeFinancialTimers"]), len(cockpit.TIMERS))
        self.assertFalse(result["financialReleaseAuthorized"])

    def test_delta_names_exact_changed_surface(self):
        services = {
            x: {"executableSha256": "a"*64, "pid": 1012, "activeState": "active"}
            for x in cockpit.SERVICES
        }
        timers = {
            x: {"activeState": "active", "triggers": x.replace(".timer", ".service")}
            for x in cockpit.TIMERS
        }
        previous = {
            "sourceCheckout": "a"*40, "services": services, "financialTimers": timers,
            "canonicalGateIndexSnapshot": {x: "BLOCKED" for x in cockpit.GATES},
        }
        current = json.loads(json.dumps(previous))
        current["services"]["wolochain-mainnet-settlement.service"]["executableSha256"] = "b"*64
        current["financialTimers"][cockpit.TIMERS[0]]["activeState"] = "inactive"
        changes = cockpit.delta(previous, current)
        self.assertEqual(len(changes), 2)
        self.assertTrue(any(x.startswith("EXECUTABLE_CHANGED") for x in changes))
        self.assertTrue(any(x.startswith("TIMER_AUTHORITY_CHANGED") for x in changes))

    def test_readonly_commands_never_use_shell_or_mutations(self):
        calls = []

        def fake_run(args, **kwargs):
            calls.append((args, kwargs))
            return type("Result", (), {"returncode": 0, "stdout": "active"})()

        with patch.object(cockpit.subprocess, "run", side_effect=fake_run):
            cockpit.command(["systemctl", "show", "sample.service"])
        self.assertNotIn("shell", calls[0][1])
        self.assertFalse(any("restart" in str(x) for x in calls))


if __name__ == "__main__":
    unittest.main()

"""Synthetic two-service cutover fault/recovery tests; no VPS/network/systemd."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "settlement_bdbce253_offline_rehearsal.py"
PLAN = ROOT / "scripts" / "settlement-bdbce253-recovery-plan.sh"


def load_rehearsal():
    spec = importlib.util.spec_from_file_location("wolo_offline_simulation", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class SettlementBdbce253OfflineFaultRehearsal(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sim = load_rehearsal()

    def test_all_injected_failures_recover_original_without_payout_rewind(self):
        result = self.sim.run_all()
        self.assertEqual(result["simulated_scenarios"], 8)
        self.assertTrue(all(item["recovered_test_only"] for item in result["scenario_results"]))
        self.assertFalse(result["real_services_changed"])
        self.assertFalse(result["real_consensus_touched"])
        self.assertFalse(result["real_payout_state_touched"])
        self.assertFalse(result["live_rollback_rehearsed"])
        self.assertFalse(result["financial_drain_certified"])
        self.assertFalse(result["cutover_authorized"])

    def test_script_refuses_any_live_or_unrecognized_mode(self):
        for args in ([], ["--apply"], ["--rollback"], ["--rescue"], ["--snapshot"], ["--target", "/"]):
            with self.subTest(args=args):
                result = subprocess.run(
                    [sys.executable, str(SCRIPT), *args],
                    capture_output=True, text=True, timeout=8, check=False,
                )
                self.assertEqual(result.returncode, 2)

    def test_successful_promotion_then_recovery_restores_only_code(self):
        with tempfile.TemporaryDirectory() as tmp:
            rehearsal = self.sim.Rehearsal(Path(tmp))
            before = rehearsal.state_digest()
            self.assertTrue(rehearsal.try_promotion())
            rehearsal.assert_candidate()
            rehearsal.recover_original()
            rehearsal.assert_original()
            self.assertEqual(rehearsal.state_digest(), before)
            self.assertEqual(rehearsal.consensus, rehearsal.consensus_start)
            self.assertTrue(rehearsal.payout_producers_fenced)

    def test_no_mutation_permitted_without_synthetic_ingress_fence(self):
        with tempfile.TemporaryDirectory() as tmp:
            rehearsal = self.sim.Rehearsal(Path(tmp))
            rehearsal.payout_producers_fenced = False
            with self.assertRaises((RuntimeError, AssertionError)):
                rehearsal.try_promotion()
            self.assertFalse(rehearsal.dropin(self.sim.PRIMARY).exists())
            self.assertFalse(rehearsal.dropin(self.sim.FOUNDER).exists())

    def test_foreign_override_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            rehearsal = self.sim.Rehearsal(Path(tmp))
            file = rehearsal.dropin(self.sim.PRIMARY)
            file.write_text("[Service]\nExecStart=/unreviewed\n")
            with self.assertRaisesRegex(RuntimeError, "foreign override"):
                rehearsal.recover_original()
            self.assertEqual(file.read_text(), "[Service]\nExecStart=/unreviewed\n")
            self.assertTrue(rehearsal.units[self.sim.PRIMARY].running)

    def test_dangling_symlink_override_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            rehearsal = self.sim.Rehearsal(Path(tmp))
            file = rehearsal.dropin(self.sim.PRIMARY)
            file.symlink_to("/missing/synthetic-target")
            with self.assertRaisesRegex(RuntimeError, "symlink"):
                rehearsal.recover_original()
            self.assertTrue(file.is_symlink())

    def test_dependent_planner_override_bytes_exactly_match(self):
        planner = PLAN.read_text(encoding="utf-8")
        marker = self.sim.CANDIDATE
        self.assertIn(marker, planner)
        self.assertIn(self.sim.OVERRIDE, planner)
        self.assertIn("# AOE2WAR bdbce253 two-settlement code-only; leave request/run state untouched", planner)
        for fragment in ("[Service]", "ExecStart=", "settlement serve"):
            self.assertIn(fragment, self.sim.override_bytes().decode())

    def test_only_synthetic_state_and_no_external_commands(self):
        source = SCRIPT.read_text(encoding="utf-8")
        for forbidden in (
            "subprocess", "os.system", "os.exec", "os.spawn", "socket.",
            "urllib", "requests.", "paramiko", "psycopg", "systemctl ",
            "ssh ", "sudo ", "shell=True",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)
        self.assertIn("TemporaryDirectory", source)
        self.assertIn("live_rollback_rehearsed\": False", source)


if __name__ == "__main__":
    unittest.main()

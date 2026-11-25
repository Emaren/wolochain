"""Offline C5 current-version dual settlement recovery-state planner contracts.

Never connects to VPS, executes systemd operations, or reads wallets.
"""
from __future__ import annotations

from pathlib import Path
import re
import subprocess
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/settlement-bdbce253-recovery-plan.sh"


class SettlementBdbceRecoveryPlan(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.body = SCRIPT.read_text(encoding="utf-8")

    def test_shell_syntax(self):
        subprocess.run(["bash", "-n", str(SCRIPT)], check=True)

    def test_exact_service_and_artifact_identity(self):
        for symbol in (
            "wolochain-mainnet-settlement.service",
            "wolochain-founder-rewards-settlement.service",
            "wolochaind-mainnet.service",
            "50-aoe2war-bdbce253-settlement-only.conf",
            "bdbce253-UNDEPLOYED/wolochaind-settlement-only-linux-amd64",
            "040126a2884946caf1651a50b7d8115c5a6fb2d5aa94fcbbe150694602d451a5",
            "4b77f622191db7550cb87cafb8f1886a0aadebee3eb6565f9f90036f809e61d3",
            "44d8aed5550d1b33635c734c1a359d0cb69e854093ef8c9a8a3da4f99d416ede",
        ):
            with self.subTest(symbol=symbol):
                self.assertIn(symbol, self.body)

    def test_inspection_cannot_run_mutating_mode_even_as_non_root(self):
        for arg in ("--rollback", "--apply", "--rescue", "--promote", "--snapshot"):
            with self.subTest(arg=arg):
                result = subprocess.run(
                    ["bash", str(SCRIPT), arg],
                    capture_output=True, text=True, timeout=5, check=False,
                )
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                self.assertIn("NOT implemented", result.stderr)

    def test_read_only_no_restart_or_filesystem_mutation_commands(self):
        for forbidden in (
            r"\bsystemctl\s+(?:stop|start|restart|reload|enable|disable|daemon-reload|kill)\b",
            r"\b(?:install|cp|mv|rm|chmod|chown|kill|pkill|touch|tee)\s+",
            r"\b(?:psql|prisma|pg_restore|wolochaind)\s+",
        ):
            with self.subTest(regex=forbidden):
                self.assertIsNone(re.search(forbidden, self.body))
        self.assertIn("NO_REQUEST_OR_RUN_STATE_RESTORED=true", self.body)
        self.assertIn("FINANCIAL_PRODUCERS_FENCED=false", self.body)
        self.assertIn("REHEARSED_ROLLBACK_WATCHDOG_CERTIFIED=false", self.body)
        self.assertIn("ROLLBACK_OR_CUTOVER_AUTHORIZED=false", self.body)

    def test_partial_install_never_considered_safe(self):
        self.assertIn('[[ "$primary_mode" == "$founder_mode" ]]', self.body)
        self.assertIn("mixed settlement code versions/overrides", self.body)
        self.assertIn('[[ "$paths" == "$f" ]]', self.body)
        self.assertIn('cmp -s "$f" <(expected_override)', self.body)
        self.assertIn("consensus PID changed during inspection", self.body)

    def test_unprivileged_inspection_rejected(self):
        import os
        if os.geteuid() == 0:
            self.skipTest("CI running as root")
        result = subprocess.run(
            ["bash", str(SCRIPT), "--inspect"],
            capture_output=True, text=True, timeout=5, check=False,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("root required", result.stderr)


if __name__ == "__main__":
    unittest.main()

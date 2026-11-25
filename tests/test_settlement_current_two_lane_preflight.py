"""Offline checks for the modern WoloChain settlement-only preflight and snapshot.

No VPS, mainnet signer, wallet, state directory or systemd access is required.
"""
from __future__ import annotations

from pathlib import Path
import re
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
PREFLIGHT = ROOT / "scripts/settlement-dual-service-release-preflight.sh"
SNAPSHOT = ROOT / "scripts/settlement-dual-service-snapshot.sh"

CANDIDATE = (
    "/settlement-candidates/bdbce253-UNDEPLOYED/"
    "wolochaind-settlement-only-linux-amd64"
)
OLD_CANDIDATE = (
    "/settlement-candidates/3ea79363/"
    "wolochaind-settlement-only-linux-amd64"
)
NEW_SHA = "44d8aed5550d1b33635c734c1a359d0cb69e854093ef8c9a8a3da4f99d416ede"
SETTLEMENT_SHA = "040126a2884946caf1651a50b7d8115c5a6fb2d5aa94fcbbe150694602d451a5"
NODE_SHA = "4b77f622191db7550cb87cafb8f1886a0aadebee3eb6565f9f90036f809e61d3"
IMPLEMENTATION = "bdbce253c524d6faac14f61cd129ac5072287c3f"


class CurrentTwoLanePreflightTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.preflight = PREFLIGHT.read_text()
        cls.snapshot = SNAPSHOT.read_text()

    def test_both_shell_scripts_syntax(self):
        for script in (PREFLIGHT, SNAPSHOT):
            with self.subTest(path=script.name):
                subprocess.run(["bash", "-n", str(script)], check=True)

    def test_old_and_new_executables_pinned_both_scripts(self):
        for name, body in (("preflight", self.preflight), ("snapshot", self.snapshot)):
            with self.subTest(name=name):
                self.assertIn(CANDIDATE, body)
                self.assertNotIn(OLD_CANDIDATE, body)
                self.assertIn(NEW_SHA, body)
                self.assertIn(SETTLEMENT_SHA, body)
                self.assertIn(NODE_SHA, body)
                self.assertIn("wolochain-mainnet-settlement.service", body)
                self.assertIn("wolochain-founder-rewards-settlement.service", body)
                self.assertIn("wolochaind-mainnet.service", body)

    def test_preflight_rejects_stale_or_modified_candidate(self):
        self.assertIn(IMPLEMENTATION, self.preflight)
        self.assertIn("vcs.modified=false", self.preflight)
        self.assertIn("GOOS=linux", self.preflight)
        self.assertIn("GOARCH=amd64", self.preflight)
        self.assertIn("PARALLEL_HD_DE_SIGNER_FREEZE_CERTIFIED=false", self.preflight)
        self.assertIn("CURRENT_VERSION_ROLLBACK_CERTIFIED=false", self.preflight)

    def test_preflight_never_mutates_services_or_banks(self):
        for forbidden in (
            r"\bsystemctl\s+(?:stop|start|restart|reload|enable|disable|daemon-reload)\b",
            r"\b(?:install|cp|mv|rm|chmod|chown|kill|pkill)\s+",
            r"^\s*(?:wolochaind|prisma|psql|pg_restore)\s+",
        ):
            with self.subTest(pattern=forbidden):
                self.assertIsNone(re.search(forbidden, self.preflight))

    def test_snapshot_requires_explicit_mode_and_never_restores_live_state(self):
        self.assertIn('MODE="${1:---inspect}"', self.snapshot)
        self.assertIn('case "$MODE" in --inspect|--snapshot)', self.snapshot)
        self.assertIn('[[ "$MODE" == "--inspect" ]]', self.snapshot)
        self.assertIn("DO NOT RESTORE STATE BLINDLY", self.snapshot)
        self.assertIn("REPLAY_SAFETY_CERTIFIED=false", self.snapshot)
        self.assertNotIn("systemctl restart", self.snapshot)
        self.assertNotIn("systemctl stop", self.snapshot)

    def test_non_root_wont_operate_preflight(self):
        if hasattr(__import__("os"), "geteuid") and __import__("os").geteuid() == 0:
            self.skipTest("runner is root; cannot assert unprivileged failure")
        run = subprocess.run(
            ["bash", str(PREFLIGHT)],
            capture_output=True, text=True, check=False, timeout=5
        )
        self.assertEqual(run.returncode, 2)
        self.assertIn("use sudo", run.stderr)


if __name__ == "__main__":
    unittest.main()

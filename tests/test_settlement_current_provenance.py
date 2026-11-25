"""Offline guard tests for the exact-source read-only settlement provenance checker.

These tests intentionally never access the VPS, mainnet, keys or systemd services.
"""
from __future__ import annotations

import pathlib
import re
import subprocess
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "settlement-only-provenance.sh"


class SettlementCurrentProvenanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.body = SCRIPT.read_text()

    def test_shell_syntax(self):
        subprocess.run(["bash", "-n", str(SCRIPT)], check=True)

    def test_exact_production_and_reviewed_identity_pins(self):
        self.assertIn(
            'EXPECTED_OLD_SOURCE="78c25985420ee41a6678c42fab8ea8d6c3b1b519"',
            self.body,
        )
        self.assertIn(
            'EXPECTED_NEW_SOURCE="bdbce253c524d6faac14f61cd129ac5072287c3f"',
            self.body,
        )
        self.assertIn(
            'EXPECTED_NODE_SHA="4b77f622191db7550cb87cafb8f1886a0aadebee3eb6565f9f90036f809e61d3"',
            self.body,
        )
        self.assertNotIn('EXPECTED_NEW_SOURCE="3ea79363', self.body)

    def test_candidate_checks_source_digest_architecture_and_symlink(self):
        for fragment in (
            'expected_candidate_sha',
            'vcs.revision',
            'vcs.modified',
            'vcs_value "$candidate" GOOS',
            'vcs_value "$candidate" GOARCH',
            '[[ -f "$candidate" && -r "$candidate" && ! -L "$candidate" ]]',
            'candidate content changed during inspection',
        ):
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, self.body)

    def test_script_is_observer_not_install_or_restart(self):
        for forbidden in (
            r'\bsystemctl\s+(?:start|stop|restart|reload|enable|disable|daemon-reload)\b',
            r'\b(?:cp|mv|install|chmod|chown|rm|kill|pkill)\s+',
        ):
            with self.subTest(pattern=forbidden):
                self.assertIsNone(re.search(forbidden, self.body))
        self.assertIn('check_unit "wolochaind-mainnet.service"', self.body)

    def test_invalid_candidate_digest_fails_before_privileged_checks(self):
        result = subprocess.run(
            ["bash", str(SCRIPT), "--candidate", "/tmp/untrusted", "--sha256", "invalid"],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("64-digit expected SHA256", result.stderr)


if __name__ == "__main__":
    unittest.main()

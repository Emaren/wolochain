"""Offline guard for an obsolete Wolo settlement helper. No systemd or RPC calls."""
from pathlib import Path
import re
import subprocess
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "settlement-two-service-code-rollback.sh"


class LegacySettlementRecoveryQuiescence(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = SCRIPT.read_text(encoding="utf-8")

    def test_mutating_modes_fail_before_root_or_service_checks(self):
        text = self.source
        parse_at = text.index('mode="${1:---inspect}"')
        stop_at = text.index('if [[ "$mode" != "--inspect" ]]; then')
        live_checks_at = text.index('(( EUID == 0 )) || fail')
        self.assertLess(parse_at, stop_at)
        self.assertLess(stop_at, live_checks_at)
        self.assertIn('fail "OBSOLETE_LEGACY_RECOVERY:', text[stop_at:live_checks_at])

    def test_mutating_modes_fail_closed_without_root_or_systemd(self):
        for mode in ("--rollback", "--rescue"):
            with self.subTest(mode=mode):
                result = subprocess.run(
                    ["bash", str(SCRIPT), mode],
                    text=True, capture_output=True, timeout=4, check=False,
                )
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                self.assertIn("OBSOLETE_LEGACY_RECOVERY", result.stderr)
                self.assertNotIn("PASS consensus", result.stdout)

    def test_no_automatic_producer_resume(self):
        text = self.source
        self.assertNotIn("resume_producers()", text)
        self.assertNotIn("resume_producers\n", text)
        self.assertNotIn("restore-units", text)
        self.assertNotRegex(text, r"systemctl\s+(?:start|restart)\s+(?:aoe2hdbets|aoe2dewarwagers|aoe2-wolo)")
        self.assertNotIn("PRODUCERS_RESTORED", text)
        self.assertNotRegex(text, r"systemctl\s+(?:start|stop|restart)\s+")

    def test_quiescence_is_not_financial_approval(self):
        text = self.source
        self.assertIn("FINANCIAL_RESUME_AUTHORIZED=false", text)
        self.assertIn("QUIESCED_RECOVERY_ONLY", text)
        self.assertIn('NODE_UNTOUCHED:', text)


if __name__ == "__main__":
    unittest.main()

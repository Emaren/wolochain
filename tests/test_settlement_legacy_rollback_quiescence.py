"""Offline settlement release-policy guards. No systemd or RPC calls."""
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


class SettlementPreflightBindContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = (SCRIPT.parent / "settlement-dual-service-release-preflight.sh").read_text(encoding="utf-8")
        # Execute the real policy fragment, avoiding every privileged runtime,
        # filesystem, process and network observation in the surrounding tool.
        start = source.index('[[ "$primary_addr" == ')
        end = source.index('echo "PASS primary listen ', start)
        cls.bind_policy = source[start:end]

    def check_binds(self, primary, founder):
        program = ('fail() { printf "BLOCKED: %s\\n" "$*" >&2; exit 2; }\n'
                   'primary_addr="$1"\nfounder_addr="$2"\n' + self.bind_policy)
        return subprocess.run(
            ["bash", "-c", program, "release-bind-test", primary, founder],
            text=True, capture_output=True, timeout=4, check=False,
        )

    def test_exact_primary_and_founder_lanes_pass(self):
        result = self.check_binds("127.0.0.1:8092", "127.0.0.1:8093")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_noncanonical_lanes_fail_closed(self):
        for primary, founder in (
            ("127.0.0.1:8092", "127.0.0.1:8094"),
            ("127.0.0.1:8092", "127.0.0.1:8092"),
            ("127.0.0.1:8092", "127.0.0.1:18093"),
            ("127.0.0.1:8093", "127.0.0.1:8092"),
        ):
            with self.subTest(primary=primary, founder=founder):
                result = self.check_binds(primary, founder)
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                self.assertIn("BLOCKED:", result.stderr)


if __name__ == "__main__":
    unittest.main()

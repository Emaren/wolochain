"""Source-only custody artifact pin contract for the recovered original LIVE proof.

Never signs, loads a vault key, changes production, or authorizes a release.
The exact source is an intentional review decision, not a runtime argument.
"""
from pathlib import Path
import re
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
RECOVERED = "d2b442b0de19837b0001a1137cb00c044d47bd67"
LEGACY = "526d5eb6123f6cc0394b5e78489c668e77e46106"
COMPOSED = "155fcf67fb2127a2227de5ea785e51bdbb0155c0"


class TestRecoveredCustodyArtifactPin(unittest.TestCase):
    def test_reviewed_implementation_is_exact_commit_with_authenticated_source(self):
        resolved = subprocess.check_output(
            ["git", "-C", str(ROOT), "rev-parse", RECOVERED + "^{commit}"],
            text=True, timeout=10,
        ).strip()
        self.assertEqual(resolved, RECOVERED)
        for source in (
            "cmd/wolosatcheld/bank_proof.go",
            "internal/satchel/bank_proof.go",
            "internal/satchel/isolated_lifecycle_test.go",
            "internal/satchelservice/reviewer_original_live_source.go",
            "internal/satchelservice/reviewer_live_witness_owner_game.go",
        ):
            subprocess.run(
                ["git", "-C", str(ROOT), "cat-file", "-e", RECOVERED + ":" + source],
                check=True, timeout=10, stdout=subprocess.DEVNULL,
            )

    def test_workflow_builds_only_exact_source_and_does_not_deploy(self):
        workflow = (
            ROOT / ".github/workflows/custody-backend-satcheld-exact-artifact.yml"
        ).read_text()
        self.assertRegex(workflow, r"(?m)^\s+EXPECTED_SOURCE: " + RECOVERED + r"$")
        self.assertIn("ref: ${{ env.EXPECTED_SOURCE }}", workflow)
        self.assertIn("path: implementation", workflow)
        self.assertIn('test "$(git rev-parse HEAD)" = "$EXPECTED_SOURCE"', workflow)
        self.assertIn("UNDEPLOYED", workflow)
        self.assertIn("NO DEPLOY", workflow)
        self.assertNotRegex(workflow, r"(?m)^\s*(?:deploy|production|mainnet_activation):")

    def test_builder_and_workflow_have_identical_pins_and_preserve_history(self):
        policy = (ROOT / "scripts/settlement-artifact.py").read_text()
        self.assertRegex(policy, r'(?m)^BACKEND_SOURCE = "' + RECOVERED + r'"$')
        self.assertRegex(policy, r'(?m)^EXPECTED_SOURCE = "' + LEGACY + r'"$')
        self.assertRegex(policy, r'(?m)^COMPOSED_SOURCE = "' + COMPOSED + r'"$')
        self.assertIn('"production_authorized": False', policy)
        self.assertIn('"satchel_activation_authorized": False', policy)
        self.assertIn('"financial_readiness_attested": False', policy)

    def test_custody_artifact_contract_records_candidate_not_financial_authority(self):
        text = (ROOT / "docs/war-satchel-exact-source-artifact.md").read_text()
        self.assertIn(RECOVERED, text)
        self.assertIn("UNDEPLOYED", text.upper())
        self.assertIn("no financial", text.lower())
        self.assertNotIn("deployment authorized: true", text.lower())


if __name__ == "__main__":
    unittest.main()

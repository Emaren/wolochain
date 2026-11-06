"""C08 centralized one-human policy proposal cannot authorize funded activity."""
from __future__ import annotations
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/settlement_c08_solo_owner_proposal_hold.py"
PROPOSAL = ROOT / "docs/settlement-contracts/solo-owner-governance-proposal-20261106.json"


def load():
    spec = importlib.util.spec_from_file_location("c08_proposal_hold", SCRIPT)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class C08SoloGovernanceProposalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = load()

    def setUp(self):
        self.policy = json.loads(PROPOSAL.read_text())

    def test_exact_current_draft_is_never_a_funded_permit(self):
        v = self.m.validate(self.policy)
        self.assertEqual(v["status"], "HOLD")
        self.assertFalse(v["financial_release_authorized"])
        self.assertFalse(v["canary_transfer_authorized"])
        self.assertFalse(v["original_financial_constitution_replaced"])

    def test_centralized_one_human_cannot_claim_independence(self):
        for key, value in [
            ("independent_review_claimed", True),
            ("independent_human_review_available", True),
            ("separate_owner_devices_count_as_independent_humans", True),
            ("ai_review_counts_as_human", True),
            ("human_operator_count", 2),
        ]:
            with self.subTest(key=key), self.assertRaises(self.m.PolicyHold):
                v = dict(self.policy, **{key: value})
                self.m.validate(v)

    def test_funded_canary_is_zero_until_new_policy_is_implemented(self):
        for n in (1, 1000000, True, -1):
            with self.subTest(n=n), self.assertRaises(self.m.PolicyHold):
                self.m.validate(dict(self.policy, funded_canary_max_uwolo=n))

    def test_no_legacy_fallback_and_no_unknown_retry(self):
        for key in ("legacy_8092_fallback_allowed", "unknown_auto_retry_allowed"):
            with self.subTest(key=key), self.assertRaises(self.m.PolicyHold):
                self.m.validate(dict(self.policy, **{key: True}))

    def test_unknown_payout_and_historical_debt_cannot_be_waived(self):
        with self.assertRaises(self.m.PolicyHold):
            self.m.validate(dict(self.policy, historical_liabilities_waiver_allowed=True))

    def test_writer_fence_solvency_and_backup_requirements_not_optional(self):
        for key in ("database_writer_fence_required", "independent_chain_proof_required",
                    "independently_reproducible_common_height_solvency_required",
                    "encrypted_offhost_backup_and_isolated_pair_restore_required"):
            with self.subTest(key=key), self.assertRaises(self.m.PolicyHold):
                self.m.validate(dict(self.policy, **{key: False}))

    def test_signed_one_use_and_public_notice_not_cosmetic(self):
        for key in ("next_funded_permit_requires_fresh_exact_owner_signature",
                    "new_permission_version_required",
                    "offhost_one_use_nonce_witness_required",
                    "public_control_disclosure_required",
                    "first_canary_single_operation_only"):
            with self.subTest(key=key), self.assertRaises(self.m.PolicyHold):
                self.m.validate(dict(self.policy, **{key: False}))

    def test_no_silent_old_constitution_conversion(self):
        with self.assertRaises(self.m.PolicyHold):
            self.m.validate(dict(self.policy, old_five_human_permits_auto_convert=True))

    def test_no_early_runtime_8094_8095_access(self):
        for key in ("reviewed_runtime_solo_owner_funded_activation_supported",
                    "active_8094_8095_allowed", "financial_release_authorized"):
            with self.subTest(key=key), self.assertRaises(self.m.PolicyHold):
                self.m.validate(dict(self.policy, **{key: True}))

    def test_no_shortening_notice_or_expanding_future_permit(self):
        for key, value in (("public_notice_min_seconds", 0),
                           ("post_adoption_funded_permit_max_lifetime_seconds", 3600)):
            with self.subTest(key=key), self.assertRaises(self.m.PolicyHold):
                self.m.validate(dict(self.policy, **{key: value}))

    def test_gate_list_exact(self):
        for gates in (["C01"], list(reversed(self.m.GATES)), self.m.GATES + ["C10"]):
            with self.subTest(gates=gates), self.assertRaises(self.m.PolicyHold):
                self.m.validate(dict(self.policy, required_formal_gates=gates))

    def test_extra_fields_and_missing_fields_refused(self):
        with self.assertRaises(self.m.PolicyHold):
            self.m.validate(dict(self.policy, override=True))
        q = dict(self.policy)
        q.pop("financial_release_authorized")
        with self.assertRaises(self.m.PolicyHold):
            self.m.validate(q)

    def test_duplicate_json_keys_fail_closed(self):
        with self.assertRaises(self.m.PolicyHold):
            json.loads('{"owner":1,"owner":2}', object_pairs_hook=self.m.decode_unique)

    def test_cli_valid_proposal_exits_three_hold(self):
        with redirect_stdout(StringIO()) as stream:
            n = self.m.main([str(PROPOSAL)])
        self.assertEqual(n, 3)
        result = json.loads(stream.getvalue())
        self.assertEqual(result["status"], "HOLD")
        self.assertFalse(result["financial_release_authorized"])

    def test_cli_forged_policy_exits_two_stop(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)/"policy.json"
            p.write_text(json.dumps(dict(self.policy, financial_release_authorized=True)))
            with redirect_stdout(StringIO()) as stream:
                result = self.m.main([str(p)])
        self.assertEqual(result, 2)
        self.assertEqual(json.loads(stream.getvalue())["status"], "STOP")


if __name__ == "__main__":
    unittest.main()

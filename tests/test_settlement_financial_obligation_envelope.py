"""Adversarial offline finance observations. Source never signs, broadcasts or mutates."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "settlement_financial_obligation_envelope.py"
spec = importlib.util.spec_from_file_location("settlement_financial_obligation_envelope", SCRIPT)
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)
EVIDENCE = ROOT / "docs" / "settlement-contracts" / "financial-release-evidence-20261018"

def original(name):
    return json.loads((EVIDENCE / name).read_text(encoding="utf-8"))

class ObligationEnvelopeTests(unittest.TestCase):
    def setUp(self):
        self.bank = original("bank-chain-observations.json")
        self.hd = original("hd-liability-observations.json")
        self.journal = original("settlement-state-evidence.json")
        self.digests = ["a" * 64, "b" * 64, "c" * 64]

    def report(self):
        return tool.envelope(self.bank, self.hd, self.journal, *self.digests)

    def rejected(self, match):
        with self.assertRaisesRegex(tool.EvidenceFailure, "^" + match + "$"):
            self.report()

    def test_actual_historical_receipt_is_non_additive_hold(self):
        result = self.report()
        amounts = result["NON_ADDITIVE_observations"]
        self.assertEqual(amounts["unique_same_node_bank_accounts"], 3)
        self.assertEqual(amounts["shared_bank_fingerprints_deduplicated"], 1)
        self.assertEqual(amounts["configured_node_payout_balance_uwolo"], "753294241424")
        self.assertEqual(amounts["configured_node_escrow_balance_uwolo"], "825469500000")
        self.assertEqual(amounts["recorded_hd_pending_claim_count"], 947)
        self.assertEqual(amounts["recorded_hd_pending_requested_uwolo"], "993189000000")
        self.assertEqual(amounts["founder_889_pending_requested_uwolo"], "300000000")
        self.assertTrue(amounts["founder_889_included_in_hd_total_not_additive"])
        self.assertEqual(amounts["journal_deduplicated_recorded_requested_uwolo"], "15787748750000")
        self.assertEqual(amounts["journal_leaf_recorded_requested_uwolo"], "14464748750000")
        self.assertEqual(amounts["journal_aggregate_only_requested_uwolo"], "1323000000000")
        self.assertEqual(amounts["journal_recorded_accepted_count"], 1)
        self.assertIsNone(result["global_liability_upper_bound_uwolo"])
        self.assertFalse(result["global_bank_solvency_certified"])
        self.assertFalse(result["financial_release_authorized"])
        self.assertFalse(result["recorded_claim_journal_overlap_reconciled"])
        self.assertNotIn("surplus", json.dumps(result).lower())
        self.assertNotIn("deficit", json.dumps(result).lower())

    def test_duplicate_escrow_bank_counted_once(self):
        self.bank["bank_role_observations"][1]["roles"][1]["configured_node_bank_uwolo"] = "825469500001"
        self.rejected("BANK_SAME_NODE_BALANCE_CONFLICT")

    def test_different_roles_cannot_share_account_identity(self):
        a = self.bank["bank_role_observations"]
        a[1]["roles"][0]["account_fingerprint_sha256"] = a[0]["roles"][1]["account_fingerprint_sha256"]
        self.rejected("BANK_SHARED_IDENTITY_CONFLICT")

    def test_conflicting_same_identity_even_across_service_lanes(self):
        a = self.bank["bank_role_observations"]
        a[1]["roles"][1]["health_reported_uwolo"] = "825469500001"
        a[1]["roles"][1]["configured_node_bank_uwolo"] = "825469500001"
        self.rejected("BANK_SHARED_IDENTITY_CONFLICT")

    def test_consensus_claim_cannot_create_authentication(self):
        self.bank["consensus_authenticated"] = True
        self.rejected("UNSUPPORTED_AUTHORITY_ASSERTION")

    def test_forged_bank_solvent_boolean_is_refused(self):
        self.bank["reserve_solvency_certified"] = True
        self.rejected("UNSUPPORTED_AUTHORITY_ASSERTION")

    def test_missing_bank_role_cannot_create_coverage(self):
        self.bank["bank_role_observations"].pop()
        self.rejected("BANK_LANE_COVERAGE_INVALID")

    def test_duplicate_lanes_rejected(self):
        self.bank["bank_role_observations"][1]["lane"] = "primary"
        self.rejected("BANK_LANE_DUPLICATED_OR_UNHEALTHY")

    def test_missing_claim889_cannot_remove_obligation(self):
        self.hd["claim_889"]["present"] = False
        self.rejected("FOUNDER_889_HOLD_INVALID")

    def test_forged_claim889_paid_not_accepted(self):
        self.hd["claim_889"]["paid_or_unpaid_proven"] = True
        self.rejected("FOUNDER_889_HOLD_INVALID")

    def test_claim889_must_not_double_count(self):
        self.hd["recorded_hd_claim_groups"].append(copy.deepcopy(
            self.hd["recorded_hd_claim_groups"][1]
        ))
        self.rejected("HD_CLAIM_KIND_DUPLICATED_OR_INVALID")

    def test_invalid_hd_claim_amount_fails(self):
        self.hd["recorded_hd_claim_groups"][0]["recorded_requested_uwolo"] = "0.1"
        self.rejected("INVALID_CANONICAL_UWOLO")

    def test_invalid_claim_record_count_or_amount_fails(self):
        self.hd["recorded_hd_claim_groups"][0]["invalid_amount_count"] = "1"
        self.rejected("HD_CLAIM_COVERAGE_INCOMPLETE")

    def test_journal_claimed_chain_proof_is_rejected(self):
        self.journal["chain_proof_verified"] = True
        self.rejected("UNSUPPORTED_AUTHORITY_ASSERTION")

    def test_bad_journal_digest_or_aggregate_math_rejected(self):
        self.journal["accounting"]["deduplicated_observed_requested_principal_uwolo"] = "1"
        self.rejected("JOURNAL_AMOUNT_OR_COUNT_MISMATCH")

    def test_journal_duplicate_role_status_lanes_are_rejected(self):
        self.journal["accounting"]["amount_groups"].append(
            copy.deepcopy(self.journal["accounting"]["amount_groups"][0])
        )
        self.rejected("JOURNAL_GROUP_DUPLICATED")

    def test_journal_accepted_count_must_match_sum(self):
        self.journal["counts"]["recorded_status_accepted"] = 0
        self.rejected("JOURNAL_AMOUNT_OR_COUNT_MISMATCH")

    def test_no_float_or_overflow(self):
        self.hd["recorded_hd_claim_groups"][0]["recorded_requested_uwolo"] = str(1 << 128)
        self.rejected("UWOLO_BOUND_VIOLATION")

    def test_no_boolean_coercion_for_counts(self):
        self.journal["accounting"]["amount_groups"][0]["request_count"] = True
        self.rejected("INVALID_COUNT")

    def test_input_digests_required(self):
        self.digests[0] = ""
        self.rejected("MISSING_EVIDENCE_DIGEST")

    def test_file_open_refuses_symlink_and_duplicate_key(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "bank.json"
            p.write_text('{"a":1,"a":2}', encoding="utf-8")
            with self.assertRaisesRegex(tool.EvidenceFailure, "^DUPLICATE_JSON_KEY$"):
                tool.read_packet(p)
            p.unlink()
            p.symlink_to("/etc/hosts")
            with self.assertRaisesRegex(tool.EvidenceFailure, "^EVIDENCE_FILE_INVALID$"):
                tool.read_packet(p)

    def test_actual_cli_exits_three_without_mutations(self):
        args = [
            "--bank", str(EVIDENCE / "bank-chain-observations.json"),
            "--hd", str(EVIDENCE / "hd-liability-observations.json"),
            "--journal", str(EVIDENCE / "settlement-state-evidence.json"),
        ]
        with patch.object(tool, "print", create=True) as printer:
            self.assertEqual(tool.main(args), 3)
            text = printer.call_args.args[0]
        doc = json.loads(text)
        self.assertFalse(doc["financial_release_authorized"])
        self.assertFalse(doc["bank_consensus_authenticated"])
        self.assertFalse(doc["production_mutated"])
        self.assertEqual(doc["input_sha256"]["hd"], hashlib.sha256(
            (EVIDENCE / "hd-liability-observations.json").read_bytes()
        ).hexdigest())
        self.assertNotIn("wolo1", text)
        self.assertNotIn("/etc/", text)
        self.assertNotIn("tx_hash", text)

if __name__ == "__main__":
    unittest.main()

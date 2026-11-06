"""Source-only C04/C05 financial HOLD tests; never authorize payout or bank release."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

PATH = Path(__file__).resolve().parents[1] / "scripts" / "settlement_financial_claim_overlap_hold.py"
spec = importlib.util.spec_from_file_location("claim_overlap_hold", PATH)
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)


def example():
    claims = {
        "schema": "wolo.c04.mainnet-hashless-claimed-reconciliation-scope.v1",
        "all_payment_fates_independently_proven": False,
        "marked_claimed_equals_paid": False, "financial_release_authorized": False,
        "refund_or_founder_retry_authorized": False, "production_mutated": False,
        "total_claimed_without_hash_rows": 3, "mainnet_rows": 3,
        "recorded_amount_total_wolo": 213, "mainnet_recorded_amount_wolo": 213,
        "claims": [
            {"claim_id": 10, "era": "mainnet_era", "claim_kind": "bet_payout",
             "recorded_amount_wolo": 200, "source_market_id": 400,
             "claimed_without_payout_tx_hash": True},
            {"claim_id": 11, "era": "mainnet_era", "claim_kind": "bet_refund",
             "recorded_amount_wolo": 10, "source_market_id": 401,
             "claimed_without_payout_tx_hash": True},
            {"claim_id": 12, "era": "mainnet_era", "claim_kind": "founders_bonus",
             "recorded_amount_wolo": 3, "source_market_id": 401,
             "claimed_without_payout_tx_hash": True},
        ],
    }
    overlap = {
        "schema": "wolo.c05.claim-wager-overlap-readonly.v1",
        "claims_paid_or_unpaid_independently_proven": False,
        "financial_release_authorized": False, "retry_authorized": False,
        "production_mutated": False,
        "bet_payout_claims_without_hash": 1, "bet_payout_claimed_wolo": 200,
        "matched_winner_expected_payout_wolo": 200,
        "bet_refund_claims_without_hash": 1, "bet_refund_claimed_wolo": 10,
        "same_market_original_voided_stakes_wolo": 15,
        "one_market_excess_original_staked_amount_not_matched_by_claim_wolo": 5,
        "cases": [
            {"claim_id": 10, "claim_kind": "bet_payout", "market_id": 400,
             "claim_amount_wolo": 200, "same_market_wager_expected_or_original_stake_wolo": 200,
             "same_market_staked_no_payout_wager_count": 1},
            {"claim_id": 11, "claim_kind": "bet_refund", "market_id": 401,
             "claim_amount_wolo": 10, "same_market_wager_expected_or_original_stake_wolo": 15,
             "same_market_staked_no_payout_wager_count": 2},
        ],
    }
    winners = {
        "schema": "wolo.c05.legacy-winner-stake-verifiability.v1",
        "current_payout_due_and_unpaid_proven": False,
        "disjoint_global_liability_bound_proven": False,
        "financial_release_authorized": False, "production_mutated": False,
        "wagers": 2, "indexed_stakes": 1, "unindexed_stakes": 1,
        "indexed_original_payout_wolo": 200, "unindexed_original_payout_wolo": 30,
        "recorded_expected_payout_wolo": 230,
        "records": [
            {"wager_id": 1, "market_id": 400, "stake_tx_hash": "a" * 64, "expected_payout_wolo": 200, "local_index_matches": 1,
             "local_comet_receipt_state": "LOCAL_EXECUTION_CODE_ZERO", "local_comet_tx_code": 0},
            {"wager_id": 2, "market_id": 402, "stake_tx_hash": "b" * 64, "expected_payout_wolo": 30, "local_index_matches": 0,
             "local_comet_receipt_state": "LOCAL_TX_NOT_FOUND", "local_comet_tx_code": None},
        ],
    }
    active = {
        "schema": "wolo.c05.active-stake-escrow-match.v1",
        "global_solvency_certified": False,
        "financial_release_authorized": False, "production_mutated": False,
        "wager_count": 1, "original_principal_uwolo": "4000000",
        "entries": [{
            "wager_id": 5, "tx_hash": "c" * 64, "principal_uwolo": "4000000",
            "indexed_sender_matches_wager_wallet": True,
            "indexed_recipient_matches_original_escrow": True,
            "indexed_amount_matches_original_stake": True,
            "local_comet_proof_present": True, "local_comet_execution_code": 0,
        }],
    }
    hashes = {name: digit * 64 for name, digit in (("claims", "a"), ("overlap", "b"), ("winners", "c"), ("active", "d"))}
    return [claims, overlap, winners, active, hashes]


class GapTests(unittest.TestCase):
    def setUp(self):
        self.data = example()

    def report(self):
        return tool.verify(*self.data)

    def denied(self, error):
        with self.assertRaisesRegex(tool.GapError, "^" + error + "$"):
            self.report()

    def test_valid_evidence_exits_held_without_any_permission(self):
        result = self.report()
        self.assertEqual(result["status"], "HOLD")
        self.assertFalse(result["financial_release_authorized"])
        self.assertFalse(result["full_global_solvency_certified"])
        self.assertFalse(result["bank_consensus_authenticated"])
        self.assertFalse(result["observations_atomic_together"])
        self.assertEqual(result["NON_ADDITIVE"]["hashless_bet_payout_claims_overlap_winning_wager_amount_wolo"], 200)
        self.assertEqual(result["NON_ADDITIVE"]["unadjudicated_voided_stake_difference_wolo"], 5)
        self.assertEqual(result["NON_ADDITIVE"]["legacy_winner_unindexed_recorded_payout_wolo"], 30)
        self.assertNotIn("surplus", json.dumps(result).lower())
        self.assertNotIn("deficit", json.dumps(result).lower())

    def test_claimed_flag_cannot_invent_chain_proof(self):
        self.data[0]["marked_claimed_equals_paid"] = True
        self.denied("UNSUPPORTED_FINANCIAL_AUTHORITY_ASSERTION")

    def test_claim_id_cannot_repeat(self):
        self.data[0]["claims"][1]["claim_id"] = 10
        self.denied("CLAIM_ID_DUPLICATE")

    def test_claim_total_is_bound_to_source_rows(self):
        self.data[0]["mainnet_recorded_amount_wolo"] = 214
        self.denied("CLAIM_SUMMARY_DRIFT")

    def test_claim_payout_hash_absence_is_mandatory(self):
        self.data[0]["claims"][1]["claimed_without_payout_tx_hash"] = False
        self.denied("CLAIM_HAS_PAYOUT_PROOF_OR_INVALID_FLAG")

    def test_source_market_identity_is_bound(self):
        self.data[1]["cases"][0]["market_id"] = 402
        self.denied("OVERLAP_CLAIM_IDENTITY_CONFLICT")

    def test_claim_and_wager_sums_reconcile(self):
        self.data[1]["cases"][0]["same_market_wager_expected_or_original_stake_wolo"] = 201
        self.denied("PAYOUT_WAGER_MARKET_NOT_EXACT")

    def test_extra_void_stake_is_not_silently_reclassified(self):
        self.data[1]["one_market_excess_original_staked_amount_not_matched_by_claim_wolo"] = 0
        self.denied("OVERLAP_AMOUNT_DRIFT")

    def test_independent_finality_claim_is_not_accepted(self):
        self.data[1]["claims_paid_or_unpaid_independently_proven"] = True
        self.denied("UNSUPPORTED_FINANCIAL_AUTHORITY_ASSERTION")

    def test_indexed_winner_requires_successful_local_execution(self):
        self.data[2]["records"][0]["local_comet_tx_code"] = 7
        self.denied("WINNER_INDEXED_STAKE_NOT_EXECUTED")

    def test_false_not_a_successful_comet_code(self):
        self.data[2]["records"][0]["local_comet_tx_code"] = False
        self.denied("WINNER_INDEXED_STAKE_NOT_EXECUTED")

    def test_false_not_a_successful_active_comet_code(self):
        self.data[3]["entries"][0]["local_comet_execution_code"] = False
        self.denied("ACTIVE_STAKE_NOT_LOCALLY_EXECUTED")

    def test_cross_family_wager_collision_is_not_disjoint(self):
        self.data[3]["entries"][0]["wager_id"] = 1
        self.denied("CROSS_FAMILY_WAGER_ID_REUSED")

    def test_cross_family_tx_collision_is_not_disjoint(self):
        self.data[3]["entries"][0]["tx_hash"] = "a" * 64
        self.denied("CROSS_FAMILY_STAKE_TX_HASH_REUSED")

    def test_winner_nonadditive_summary_consistent(self):
        self.data[2]["recorded_expected_payout_wolo"] = 229
        self.denied("WINNER_SUMMARY_DRIFT")

    def test_claim_market_must_match_verified_winner_market(self):
        self.data[2]["records"][0]["market_id"] = 499
        self.denied("PAYOUT_CLAIM_WINNER_MARKET_COVERAGE_DRIFT")

    def test_winner_duplicate_stake_hash_is_refused(self):
        self.data[2]["records"][1]["stake_tx_hash"] = "a" * 64
        self.denied("WINNER_STAKE_HASH_DUPLICATED_OR_INVALID")

    def test_active_claim_replay_stake_hash_is_refused(self):
        self.data[3]["entries"].append(copy.deepcopy(self.data[3]["entries"][0]))
        self.data[3]["entries"][1]["wager_id"] = 6
        self.denied("ACTIVE_STAKE_HASH_DUPLICATED_OR_INVALID")

    def test_active_stake_exact_original_escrow_required(self):
        self.data[3]["entries"][0]["indexed_recipient_matches_original_escrow"] = False
        self.denied("ACTIVE_STAKE_EVIDENCE_INVALID")

    def test_no_float_or_boolean_as_count(self):
        self.data[3]["wager_count"] = True
        self.denied("INVALID_NONNEGATIVE_INTEGER")

    def test_digests_cover_exact_four_packets(self):
        self.data[4]["claims"] = "BAD"
        self.denied("INPUT_HASH_SET_INVALID")

    def test_no_follow_and_digest_pinning(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "a.json"
            data = json.dumps({"schema": "x"}).encode()
            p.write_bytes(data)
            sha = hashlib.sha256(data).hexdigest()
            self.assertEqual(tool.read(p, sha)["schema"], "x")
            with self.assertRaisesRegex(tool.GapError, "^SOURCE_DIGEST_MISMATCH$"):
                tool.read(p, "a" * 64)
            p.unlink()
            p.symlink_to("/etc/hosts")
            with self.assertRaisesRegex(tool.GapError, "^SOURCE_UNAVAILABLE$"):
                tool.read(p, sha)

    def test_duplicate_json_object_keys_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "a.json"
            raw = b'{"schema":"x","schema":"y"}'
            p.write_bytes(raw)
            with self.assertRaisesRegex(tool.GapError, "^DUPLICATE_JSON_KEY$"):
                tool.read(p, hashlib.sha256(raw).hexdigest())


if __name__ == "__main__":
    unittest.main()

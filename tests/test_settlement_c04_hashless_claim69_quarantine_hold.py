"""Adversarial exact C04 69 hashless-claimed population: NEVER paid, unpaid or replay."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "scripts" / "settlement_c04_hashless_claim69_quarantine_hold.py"
spec = importlib.util.spec_from_file_location("c04_hashless69", SOURCE)
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)


def fixture():
    group_rows = []
    claims = []
    current = 2000
    for (era, kind), (n, total) in tool.GROUPS.items():
        group_rows.append({"claim_kind": kind, "era": era,
                           "recorded_amount_wolo": total, "rows": n})
        base, extra = divmod(total, n)
        for i in range(n):
            claim_id = current
            current += 1
            is_founder = kind == "founders_bonus"
            founder_status = ("failed" if i < 11 else "partial") if is_founder else None
            claims.append({
                "claim_id": claim_id,
                "claim_kind": kind,
                "claimed_without_payout_tx_hash": True,
                "created_at": "2026-04-07 01:54:02.803" if era == "legacy_era"
                              else "2026-10-24 01:12:35.000",
                "era": era,
                "founder_bonus_request_id_present": False,
                "founder_bonus_status": founder_status,
                "market_settlement_failure_code": None,
                "market_settlement_status": "pending",
                "market_status": "settled",
                "payout_attempted_at_present": True,
                "payout_proof_url_present": False,
                "recorded_amount_wolo": base + (1 if i < extra else 0),
                "same_market_stake_hash_present_wager_payout_hash_missing_count": 1,
                "source_founder_bonus_id": claim_id if is_founder else None,
                "source_market_id": 946520,
            })
    return {
        "all_payment_fates_independently_proven": False,
        "app_mainnet_era_cutoff_utc": "2026-05-25T00:00:00Z",
        "captured_utc": "2026-11-05T17:30:28.020546+00:00",
        "claims": claims,
        "db_observation": "HD PostgreSQL repeatable-read read-only",
        "financial_release_authorized": False,
        "founder_source_status_summary": {"failed": 11, "partial": 40},
        "groups": group_rows,
        "legacy_recorded_amount_wolo": 600,
        "legacy_rows": 5,
        "local_source_status_equals_onchain_execution": False,
        "mainnet_recorded_amount_wolo": 119843,
        "mainnet_rows": 64,
        "marked_claimed_equals_paid": False,
        "production_mutated": False,
        "recorded_amount_total_wolo": 120443,
        "refund_or_founder_retry_authorized": False,
        "schema": tool.EVIDENCE_SCHEMA,
        "source_snapshot_and_comet_atomic": False,
        "total_claimed_without_hash_rows": 69,
    }


class C04AllClaimedHashlessTests(unittest.TestCase):
    def setUp(self):
        self.d = fixture()

    def refused(self, why):
        with self.assertRaisesRegex(tool.HoldError, "^" + why + "$"):
            tool.classify(self.d)

    def test_69_unique_claims_nominal_amount_are_nonadditive_hold(self):
        a = tool.classify(self.d)
        self.assertEqual(a["status"], "HOLD")
        self.assertEqual(a["claimed_nohash_claims_quarantined_as_UNKNOWN"], 69)
        self.assertEqual(a["nonadditive_recorded_nominal_wolo"], 120443)
        self.assertEqual((a["bet_payout_claims"], a["bet_refund_claims"],
                          a["founder_bonus_claims"]), (15, 3, 51))
        self.assertTrue(a["claim_889_and_9645_not_in_this_census"])
        self.assertTrue(a["total_is_not_additive_with_wagers_or_other_c05_buckets"])
        for k in ("any_claim_paid_proved", "any_claim_unpaid_proved",
                  "retry_authorized", "financial_release_authorized",
                  "production_mutated", "historical_payment_dispositions_independently_proved"):
            self.assertIs(a[k], False)
        self.assertEqual(len(a["claim_identity_amount_commitment_sha256"]), 64)
        self.assertNotIn(str(self.d["claims"][0]["claim_id"]), json.dumps(a))

    def test_db_claimed_status_must_never_mean_cosmos_paid(self):
        self.d["marked_claimed_equals_paid"] = True
        self.refused("C04_DATABASE_STATUS_FABRICATED_AS_PAYMENT")

    def test_no_historical_independent_comet_fiction(self):
        for key in ("all_payment_fates_independently_proven",
                    "source_snapshot_and_comet_atomic",
                    "local_source_status_equals_onchain_execution"):
            self.d = fixture()
            self.d[key] = True
            self.refused("C04_DATABASE_STATUS_FABRICATED_AS_PAYMENT")

    def test_no_authorize_retry_or_funded_release(self):
        for key in ("refund_or_founder_retry_authorized",
                    "financial_release_authorized", "production_mutated"):
            self.d = fixture()
            self.d[key] = True
            self.refused("C04_DATABASE_STATUS_FABRICATED_AS_PAYMENT")

    def test_claim_id_uniqueness_strict_and_pending_not_misclassified(self):
        self.d["claims"][1]["claim_id"] = self.d["claims"][0]["claim_id"]
        self.refused("C04_DUPLICATE_OR_PENDING_CLAIM_MISCLASSIFIED")
        self.d = fixture()
        self.d["claims"][0]["claim_id"] = 889
        self.refused("C04_DUPLICATE_OR_PENDING_CLAIM_MISCLASSIFIED")
        self.d = fixture()
        self.d["claims"][0]["claim_id"] = 9645
        self.refused("C04_DUPLICATE_OR_PENDING_CLAIM_MISCLASSIFIED")

    def test_false_is_not_valid_claim_id(self):
        self.d["claims"][0]["claim_id"] = True
        self.refused("C04_DUPLICATE_OR_PENDING_CLAIM_MISCLASSIFIED")

    def test_missing_hash_flag_or_fake_payout_proof_refused(self):
        self.d["claims"][0]["claimed_without_payout_tx_hash"] = False
        self.refused("C04_UNPROVED_PAYOUT_STATUS_DRIFT")
        self.d = fixture()
        self.d["claims"][0]["payout_proof_url_present"] = True
        self.refused("C04_UNPROVED_PAYOUT_STATUS_DRIFT")

    def test_status_claimed_not_even_settled_market_refused(self):
        self.d["claims"][0]["market_status"] = "unsettled"
        self.refused("C04_UNPROVED_PAYOUT_STATUS_DRIFT")

    def test_recorded_claim_amount_boolean_negative_or_oversize_denied(self):
        for v in (False, -1, 25001, "100"):
            self.d = fixture()
            self.d["claims"][0]["recorded_amount_wolo"] = v
            self.refused("C04_CLAIM_MONEY_OR_DATE_DRIFT")

    def test_global_nominal_and_group_sums_must_match_rows(self):
        self.d["recorded_amount_total_wolo"] = 0
        self.refused("C04_GLOBAL_SCOPE_TOTALS_DRIFT")
        self.d = fixture()
        self.d["groups"][0]["recorded_amount_wolo"] = 599
        self.refused("C04_GROUP_RECORDED_SUMS_DRIFT")
        self.d = fixture()
        self.d["claims"][0]["recorded_amount_wolo"] += 1
        self.refused("C04_CLAIM_ROW_SUMS_DISAGREE_WITH_AGGREGATES")

    def test_missing_or_extra_claim_refused(self):
        self.d["claims"].pop()
        self.refused("C04_HASHLESS_CLAIM_POPULATION_DRIFT")
        self.d = fixture()
        self.d["claims"].append(dict(self.d["claims"][0]))
        self.refused("C04_HASHLESS_CLAIM_POPULATION_DRIFT")

    def test_founding_source_identity_and_status_locked(self):
        founder = next(x for x in self.d["claims"] if x["claim_kind"]=="founders_bonus")
        founder["source_founder_bonus_id"] = None
        self.refused("C04_FOUNDER_SOURCE_MISSING")
        self.d = fixture()
        founder = next(x for x in self.d["claims"] if x["claim_kind"]=="founders_bonus")
        founder["founder_bonus_status"] = "paid"
        self.refused("C04_FOUNDER_SOURCE_MISSING")

    def test_nonfounder_cannot_be_cloned_to_bonus(self):
        self.d["claims"][0]["source_founder_bonus_id"] = 1
        self.refused("C04_NONFOUNDER_DOUBLE_CLAIM_SOURCE")

    def test_illegal_market_status_and_stake_overlap_denied(self):
        self.d["claims"][0]["market_settlement_status"] = "chain-confirmed"
        self.refused("C04_SETTLEMENT_STATUS_NOT_CHAIN_FINALITY")
        self.d = fixture()
        self.d["claims"][0]["same_market_stake_hash_present_wager_payout_hash_missing_count"] = 3
        self.refused("C04_STAKE_OVERLAP_METADATA_DRIFT")

    def test_changed_observation_source_and_extra_fields_denied(self):
        self.d["db_observation"] = "trusted consensus payment"
        self.refused("C04_SOURCE_OR_SCHEMA_DRIFT")
        self.d = fixture()
        self.d["claims"][0]["confirmed_paid"] = True
        self.refused("C04_CLAIM_ROW_FIELDS_DRIFT")

    def test_raw_source_digest_is_fixed_and_cannot_be_caller_supplied(self):
        with tempfile.TemporaryDirectory(prefix="c04-all-") as d:
            p = Path(d) / "claims.json"
            p.write_text(json.dumps(self.d))
            p.chmod(0o600)
            with self.assertRaisesRegex(tool.HoldError, "^PRIVATE_C04_PACKET_SHA256_DRIFT$"):
                tool.read_exact_private(p)

    def test_private_source_symlink_and_wrong_mode_denied(self):
        with tempfile.TemporaryDirectory(prefix="c04-all-") as d:
            p = Path(d) / "claims.json"
            p.write_text(json.dumps(self.d))
            p.chmod(0o644)
            with self.assertRaisesRegex(tool.HoldError, "^PRIVATE_C04_PACKET_OWNER_OR_MODE_DRIFT$"):
                tool.read_exact_private(p)
            p.chmod(0o600)
            link = Path(d) / "symlink.json"
            link.symlink_to(p)
            with self.assertRaisesRegex(tool.HoldError, "^PRIVATE_C04_PACKET_UNAVAILABLE$"):
                tool.read_exact_private(link)

    def test_duplicate_json_keys_or_nan_rejected(self):
        with self.assertRaisesRegex(tool.HoldError, "^DUPLICATE_JSON_KEY$"):
            tool.unique([("status", "claimed"), ("status", "paid")])
        with self.assertRaisesRegex(tool.HoldError, "^NONCANONICAL_JSON_NUMBER$"):
            tool.no_floats_or_infinity("NaN")

    def test_no_execution_flag(self):
        with self.assertRaises(SystemExit) as error:
            tool.main(["--execute"])
        self.assertEqual(error.exception.code, 2)


if __name__ == "__main__":
    unittest.main()

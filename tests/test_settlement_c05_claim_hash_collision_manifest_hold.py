#!/usr/bin/env python3
"""Offline adversarial tests for a permanently noncrediting C05 reconciliation."""
import importlib.util
import pathlib
import unittest

P = pathlib.Path(__file__).resolve().parent.parent / "scripts" / "settlement_c05_claim_hash_collision_manifest_hold.py"
spec = importlib.util.spec_from_file_location("manifest", P)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def claim(i, h, source=5, amount=100, status="claimed"):
    return {"id": i, "status": status, "claim_kind": "founders_bonus",
            "amount_wolo": amount, "claimed_by_user_id": 42,
            "source_market_id": source, "source_game_stats_id": None,
            "source_founder_bonus_id": None,
            "claim_group_key": f"group-{i}", "payout_tx_hash": h}


def tx(i, h, amount=100, denom="uwolo"):
    return {"id": i, "tx_hash": h, "height": 100, "denom": denom,
            "amount_uwolo": amount * 1000000}


def dataset(*rows, transfers):
    return {"claims": list(rows), "transfers": list(transfers)}


class C05HeldManifestTests(unittest.TestCase):
    def test_single_exact_is_not_payment_authority(self):
        h = "a" * 64
        result = m.classify(dataset(claim(1, h), transfers=[tx(1, h)]))
        group = result["groups"][0]
        self.assertEqual(group["classification"], "SINGLE_AMOUNT_MATCH_NOT_PAYMENT_PROOF")
        for key in ("payment_proven", "eligible_to_repay", "solvency_admitted"):
            self.assertFalse(group[key])
        self.assertFalse(result["summary"]["funding_authorized"])
        self.assertEqual(result["summary"]["admitted_reserves_wolo"], 0)

    def test_identical_economic_source_not_an_automatic_waiver(self):
        h = "b" * 64
        result = m.classify(dataset(claim(1, h), claim(2, h), transfers=[tx(1, h)]))
        row = result["groups"][0]
        self.assertEqual(row["classification"], "REUSED_IDENTICAL_ECONOMIC_SOURCE_UNKNOWN")
        self.assertEqual(row["claim_count"], 2)
        self.assertEqual(row["nominal_difference_vs_indexed_wolo"], 100)
        self.assertFalse(row["eligible_to_repay"])

    def test_distinct_source_same_hash_is_protected(self):
        h = "c" * 64
        result = m.classify(dataset(claim(1, h, source=5), claim(2, h, source=6),
                                    transfers=[tx(1, h)]))
        self.assertEqual(result["groups"][0]["classification"],
                         "REUSED_DISTINCT_ECONOMIC_SOURCE_UNKNOWN")
        self.assertEqual(result["groups"][0]["economic_key_count"], 2)
        self.assertEqual(result["groups"][0]["nominal_difference_vs_indexed_wolo"], 100)

    def test_true_batch_looks_plausible_but_remains_unattributed(self):
        h = "d" * 64
        result = m.classify(dataset(claim(1, h), claim(2, h, source=6),
                                    transfers=[tx(1, h, amount=200)]))
        self.assertEqual(result["groups"][0]["classification"],
                         "BATCH_AMOUNT_MATCH_UNATTRIBUTED")
        self.assertFalse(result["groups"][0]["payment_proven"])

    def test_missing_index_does_not_allow_repayment(self):
        h, other = "e" * 64, "f" * 64
        result = m.classify(dataset(claim(1, h), transfers=[tx(1, other)]))
        self.assertEqual(result["groups"][0]["classification"], "INDEX_MISSING_UNKNOWN")
        self.assertFalse(result["groups"][0]["eligible_to_repay"])

    def test_wrong_denom_or_duplicate_index_fails_closed(self):
        a, b = "1" * 64, "2" * 64
        result = m.classify(dataset(claim(1, a), claim(2, b),
                                    transfers=[tx(1, a, denom="btc"),
                                               tx(2, b), tx(3, b)]))
        self.assertEqual({r["classification"] for r in result["groups"]},
                         {"INDEX_WRONG_DENOM_UNKNOWN", "INDEX_DUPLICATE_UNKNOWN"})

    def test_missing_source_never_becomes_identical_obligation(self):
        a = "3" * 64
        first, second = claim(1, a, source=None), claim(2, a, source=None)
        result = m.classify(dataset(first, second, transfers=[tx(1, a)]))
        self.assertEqual(result["groups"][0]["classification"],
                         "INDEX_AMOUNT_MISMATCH_UNKNOWN")

    def test_rescinded_paid_and_pending_are_retained(self):
        a = "4" * 64
        result = m.classify(dataset(claim(1, a, status="rescinded"),
                                    claim(2, None, status="pending"),
                                    claim(3, a),
                                    transfers=[tx(1, a)]))
        self.assertEqual(result["summary"]["claim_rows"], 3)
        self.assertEqual(result["summary"]["rescinded_with_hash_ids"], [1])
        self.assertEqual(result["summary"]["statuses"]["pending"]["missing_hash_rows"], 1)
        self.assertEqual(result["summary"]["classes"]
                         ["SINGLE_AMOUNT_MATCH_NOT_PAYMENT_PROOF"]["claim_rows"], 1)

    def test_id_and_hash_integrity_checks(self):
        a = "5" * 64
        with self.assertRaises(m.Hold):
            m.classify(dataset(claim(1, a), claim(1, a), transfers=[tx(1, a)]))
        with self.assertRaises(m.Hold):
            m.classify(dataset(claim(1, "bad-hash"), transfers=[tx(1, a)]))
        with self.assertRaises(m.Hold):
            m.classify(dataset(claim(1, a, amount=-9), transfers=[tx(1, a)]))

    def test_canonical_digest_is_order_and_identity_bound(self):
        a = {"x": 1, "y": 2}
        b = {"y": 2, "x": 1}
        self.assertEqual(m.digest(m.canonical(a)), m.digest(m.canonical(b)))
        self.assertNotEqual(m.digest(m.canonical(a)),
                            m.digest(m.canonical({"x": 1, "y": 3})))


if __name__ == "__main__":
    unittest.main()


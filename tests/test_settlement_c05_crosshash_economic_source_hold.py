#!/usr/bin/env python3
"""Noncrediting adversarial cross-hash C05 economic-source-collision contracts."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "settlement_c05_crosshash_economic_source_hold.py"
SPEC = importlib.util.spec_from_file_location("crosshash", SCRIPT)
cross = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cross)


def claim(i: int, h: str | None, source: int = 5, status: str = "claimed", kind: str = "founders_bonus"):
    return {"id": i, "status": status, "claim_kind": kind, "amount_wolo": 100,
            "claimed_by_user_id": 42, "source_market_id": source,
            "source_game_stats_id": None, "source_founder_bonus_id": None,
            "claim_group_key": f"group-{i}", "payout_tx_hash": h}


def transfer(i: int, h: str, amt: int = 100):
    return {"id": i, "tx_hash": h, "height": 200, "denom": "uwolo",
            "amount_uwolo": amt * 1000000}


class CrossHashHeldTests(unittest.TestCase):
    def test_two_real_index_amounts_same_economic_key_are_still_held(self):
        a, b = "a" * 64, "b" * 64
        result = cross.inspect({"claims": [claim(1, a), claim(2, b)],
                                "transfers": [transfer(1, a), transfer(2, b)]})
        s = result["summary"]
        self.assertEqual(s["cross_hash_keys"], 1)
        self.assertEqual(s["cross_hash_claim_rows"], 2)
        self.assertEqual(s["cross_hash_all_rows_indexed"], 1)
        self.assertEqual(s["cross_hash_all_amounts_match"], 1)
        self.assertFalse(s["funding_authorized"])
        row = result["cross_hash"][0]
        self.assertFalse(row["payment_proven"])
        self.assertFalse(row["eligible_to_repay"])
        self.assertFalse(row["economic_source_uniqueness_proven"])

    def test_one_missing_index_does_not_count_as_two_payments(self):
        a, b, c = "c" * 64, "d" * 64, "e" * 64
        result = cross.inspect({"claims": [claim(1, a), claim(2, b)],
                                "transfers": [transfer(1, a), transfer(2, c)]})
        s = result["summary"]
        self.assertEqual(s["cross_hash_keys"], 1)
        self.assertEqual(s["cross_hash_all_rows_indexed"], 0)
        self.assertEqual(s["cross_hash_with_unindexed_rows"], 1)

    def test_reused_same_hash_is_v1_category_not_cross_hash(self):
        a = "1" * 64
        result = cross.inspect({"claims": [claim(1, a), claim(2, a)],
                                "transfers": [transfer(1, a)]})
        self.assertEqual(result["summary"]["cross_hash_keys"], 0)
        self.assertEqual(result["summary"]["cross_hash_claim_rows"], 0)

    def test_distinct_sources_are_not_same_economic_group(self):
        a, b = "2" * 64, "3" * 64
        result = cross.inspect({"claims": [claim(1, a, source=11),
                                           claim(2, b, source=12)],
                                "transfers": [transfer(1, a), transfer(2, b)]})
        self.assertEqual(result["summary"]["cross_hash_keys"], 0)

    def test_pending_claimed_and_rescinded_cross_state_flags(self):
        a, b = "4" * 64, "5" * 64
        result = cross.inspect({
            "claims": [claim(1, a), claim(2, None, status="pending"),
                       claim(3, b, source=7), claim(4, None, source=7, status="rescinded")],
            "transfers": [transfer(1, a), transfer(2, b)]})
        self.assertEqual(result["summary"]["pending_claimed_source_key_overlap"], 1)
        self.assertEqual(result["summary"]["rescinded_active_source_key_overlap"], 1)

    def test_claimed_hashed_and_hashless_reports_unknown_not_credit(self):
        a = "6" * 64
        result = cross.inspect({"claims": [claim(1, a), claim(2, None)],
                                "transfers": [transfer(1, a)]})
        self.assertEqual(result["summary"]["claimed_hash_and_hashless_source_key_overlap"], 1)
        self.assertEqual(result["summary"]["cross_hash_keys"], 0)
        self.assertFalse(result["summary"]["repayment_authorized"])

    def test_source_input_integrity_guard_inherited(self):
        a = "7" * 64
        with self.assertRaises(cross.base.Hold):
            cross.inspect({"claims": [claim(1, a), claim(1, a)],
                           "transfers": [transfer(1, a)]})


if __name__ == "__main__":
    unittest.main()


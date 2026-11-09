#!/usr/bin/env python3
"""Offline falsification checks for the C05 one-validator historical witness."""
import importlib.util
from pathlib import Path
import unittest

P=Path(__file__).resolve().parents[1]/"scripts"/"settlement_c05_single_validator_offhost_bank_height_witness.py"
spec=importlib.util.spec_from_file_location("witness",P)
w=importlib.util.module_from_spec(spec);spec.loader.exec_module(w)


def fixture():
    H="A"*64
    APP="B"*64
    VH="C"*64
    addr="D"*40
    header={"height":"2886568","chain_id":"wolo-1","app_hash":APP,
            "validators_hash":VH}
    return {"census_sha256":w.EXPECTED_CENSUS_SHA256,
            "census":{"network":"wolo-1","observed_height":2886568,
                      "registered_wallet_count":24,
                      "local_consensus_block_hash":H,
                      "total_all_24_labels_uwolo":"87639451200705",
                      "eligible_reserves_uwolo":"0",
                      "c05_gate_closed":False,
                      "offhost_consensus_witness_verified":False},
            "block":{"block_id":{"hash":H},"header":header.copy()},
            "commit":{"signed_header":{"header":header.copy(),
                    "commit":{"height":"2886568","block_id":{"hash":H},
                        "signatures":[{"validator_address":addr,
                                       "block_id_flag":2,"signature":"encoded"}]}}},
            "validators":{"block_height":"2886568","count":"1","total":"1",
                          "validators":[{"address":addr,"voting_power":"2000"}]},
            "status":{"node_info":{"network":"wolo-1"},
                      "validator_info":{"address":addr,"voting_power":"2000"},
                      "sync_info":{"latest_block_height":"2898000","catching_up":False}},
            "observed_at_utc":"2026-11-09T21:00:00+00:00"}


class WitnessTests(unittest.TestCase):
    def test_actual_shape_accepted_without_false_consensus_or_reserve(self):
        x=w.classify(fixture())
        self.assertEqual(x["classification"],
                         "PASS_SAME_NODE_HISTORICAL_BLOCK_COMMIT_CONSISTENCY")
        self.assertFalse(x["financial_gate_closed"])
        self.assertFalse(x["funding_authorized"])
        self.assertFalse(x["independent_consensus_verified"])
        self.assertFalse(x["independent_bank_balances_reverified"])

    def test_changed_census_digest_denied(self):
        x=fixture();x["census_sha256"]="9"*64
        with self.assertRaises(w.Hold):w.classify(x)

    def test_wrong_chain_id_denied(self):
        x=fixture();x["status"]["node_info"]["network"]="fork-1"
        with self.assertRaises(w.Hold):w.classify(x)

    def test_bank_hash_drift_denied(self):
        x=fixture();x["census"]["local_consensus_block_hash"]="9"*64
        with self.assertRaises(w.Hold):w.classify(x)

    def test_mixed_height_denied(self):
        x=fixture();x["commit"]["signed_header"]["commit"]["height"]="2886567"
        with self.assertRaises(w.Hold):w.classify(x)

    def test_app_hash_mismatch_denied(self):
        x=fixture();x["commit"]["signed_header"]["header"]["app_hash"]="9"*64
        with self.assertRaises(w.Hold):w.classify(x)

    def test_second_validator_denied(self):
        x=fixture();x["validators"]["total"]="2"
        with self.assertRaises(w.Hold):w.classify(x)

    def test_absent_commit_signature_denied(self):
        x=fixture();x["commit"]["signed_header"]["commit"]["signatures"][0]["signature"]=""
        with self.assertRaises(w.Hold):w.classify(x)

    def test_false_spendable_reserve_denied(self):
        x=fixture();x["census"]["eligible_reserves_uwolo"]="10"
        with self.assertRaises(w.Hold):w.classify(x)

    def test_behind_chain_denied(self):
        x=fixture();x["status"]["sync_info"]["catching_up"]=True
        with self.assertRaises(w.Hold):w.classify(x)

    def test_validator_identity_changed_denied(self):
        x=fixture();x["status"]["validator_info"]["address"]="E"*40
        with self.assertRaises(w.Hold):w.classify(x)


if __name__=="__main__":unittest.main()


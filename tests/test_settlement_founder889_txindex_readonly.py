"""C04: no local tx-index response can become payout retry or trusted finality."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

FILE = Path(__file__).resolve().parents[1] / "scripts/settlement_founder889_txindex_readonly.py"
SPEC = importlib.util.spec_from_file_location("settlement_founder889_txindex_readonly", FILE)
assert SPEC and SPEC.loader
M = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = M
SPEC.loader.exec_module(M)

HASH = "D5B4CFAA5E9063F8342EA9E2B6119FCFF28DEE20B2E1DD6803944933B237D699"
ADDR_A = "wolo1" + "a" * 38
ADDR_B = "wolo1" + "b" * 38
ADDR_C = "wolo1" + "c" * 38


def record(t, amount="300000000", status="failed"):
    root = Path(t.enterContext(tempfile.TemporaryDirectory()))
    rid = "synthetic-request-original"
    data = {"request": {"request_id": rid, "amount_uwolo": amount,
                        "memo": "private memo must not be emitted", "to_address": ADDR_A},
            "response": {"request_id": rid, "status": status, "signer_address": ADDR_B,
                         "retryable": True, "tx_hash": ""}}
    file = root / (rid + ".json")
    file.write_text(json.dumps(data))
    return root, hashlib.sha256(rid.encode()).hexdigest(), file


def mock_tx(hash_value, height, to, amount):
    return {
        "hash": hash_value,
        "height": str(height),
        "tx_result": {
            "code": 0,
            "events": [{"type": "transfer", "attributes": [
                {"key": "sender", "value": ADDR_B},
                {"key": "recipient", "value": to},
                {"key": "amount", "value": amount},
            ]}],
        },
    }


def scenario(*, exact=0, bad_control=False, sender_count=1,
             node_syncing=False, bad_header=False):
    positive = mock_tx(HASH, 1078913, ADDR_C, "100000000uwolo")
    if bad_control:
        positive["hash"] = "0" * 64
    other = mock_tx("A" * 64, 324458, ADDR_C, "300000000uwolo")
    to_first = mock_tx("B" * 64, 334337, ADDR_A, "6000000uwolo")
    to_second = mock_tx("C" * 64, 355431, ADDR_A, "2000000uwolo")

    def find(expr, limit=20):
        if expr.startswith("tx.height = 1078913"):
            return 1, [positive]
        if expr == "transfer.recipient = '" + ADDR_A + "'":
            return 7, []
        if "transfer.recipient" in expr and "transfer.amount" in expr:
            return exact, []
        if "transfer.sender" in expr and "transfer.amount" in expr:
            return sender_count, [other] if sender_count == 1 else []
        if "transfer.sender" in expr and "transfer.recipient" in expr:
            return 2, [to_first, to_second]
        raise AssertionError("unexpected dynamic query")

    def get(path, params):
        if path == "/status":
            return {"node_info": {"network": "wolo-1"},
                    "sync_info": {"catching_up": node_syncing,
                                  "latest_block_height": "2809900"}}
        if path == "/block":
            return {"block": {"header": {"chain_id": "other" if bad_header else "wolo-1",
                                         "height": str(params["height"]),
                                         "time": "2026-06-13T01:17:14Z"}}}
        raise AssertionError("unexpected path")

    primary = {"status": "accepted", "amount": "100000000", "txhash": HASH,
               "to": ADDR_C, "sender": ADDR_B}
    founder = {"status": "failed", "amount": "300000000", "txhash": "",
               "sender": ADDR_B, "to": ADDR_A, "retryable": True,
               "record_sha256": "f" * 64}
    return primary, founder, find, get


class HistoricalNoPayoutAuthority(unittest.TestCase):
    def test_exact_original_is_read_without_signing(self):
        root, fp, _ = record(self)
        j = M.load_original(root, fp, "300000000", "failed")
        self.assertEqual(j["amount"], "300000000")
        self.assertEqual(j["to"], ADDR_A)
        self.assertEqual(j["sender"], ADDR_B)

    def test_altered_amount_or_status_is_refused(self):
        root, fp, _ = record(self)
        with self.assertRaises(M.Hold):
            M.load_original(root, fp, "100000000", "failed")
        with self.assertRaises(M.Hold):
            M.load_original(root, fp, "300000000", "accepted")

    def test_symlink_request_fails_closed(self):
        root, fp, f = record(self)
        outside = Path(self.enterContext(tempfile.TemporaryDirectory())) / "private"
        outside.write_bytes(f.read_bytes())
        f.unlink()
        f.symlink_to(outside)
        with self.assertRaises(M.Hold):
            M.load_original(root, fp, "300000000", "failed")

    def test_unknown_id_and_oversized_input_rejected(self):
        root, fp, f = record(self)
        with self.assertRaises(M.Hold):
            M.load_original(root, "0" * 64, "300000000", "failed")
        f.write_bytes(b"x" * (M.MAX_BYTES + 1))
        with self.assertRaises(M.Hold):
            M.load_original(root, fp, "300000000", "failed")

    def test_positive_control_and_zero_match_remain_hold(self):
        output = M.observe(*scenario()[:2], query=scenario()[2], get=scenario()[3])
        self.assertEqual(output["status"], "HOLD")
        self.assertTrue(output["known_positive_100wolo_control_found"])
        self.assertEqual(output["original_recipient_indexed_exact_300wolo"], 0)
        self.assertEqual(output["original_recipient_indexed_any_amount"], 7)
        self.assertEqual(output["original_sender_to_original_recipient_any_amount"], 2)
        self.assertEqual(output["founder889_payment_fate"], "UNKNOWN")
        self.assertFalse(output["retry_authorized"])
        self.assertFalse(output["chain_index_historical_completeness_proven"])
        self.assertFalse(output["independent_chain_trust_root_verified"])
        self.assertFalse(output["financial_release_authorized"])
        self.assertFalse(output["c04_closed"])
        self.assertFalse(output["funds_moved"])

    def test_nonzero_founder_match_is_not_credited(self):
        primary, founder, find, get = scenario(exact=1)
        output = M.observe(primary, founder, find, get)
        self.assertEqual(output["original_recipient_indexed_exact_300wolo"], 1)
        self.assertEqual(output["founder889_payment_fate"], "UNKNOWN")
        self.assertFalse(output["retry_authorized"])

    def test_unknown_or_bad_positive_control_refused(self):
        primary, founder, find, get = scenario(bad_control=True)
        with self.assertRaises(M.Hold):
            M.observe(primary, founder, find, get)

    def test_candidate_pagination_overflow_refused(self):
        primary, founder, find, get = scenario(sender_count=21)
        with self.assertRaises(M.Hold):
            M.observe(primary, founder, find, get)

    def test_bad_block_header_refused(self):
        primary, founder, find, get = scenario(bad_header=True)
        with self.assertRaises(M.Hold):
            M.observe(primary, founder, find, get)

    def test_node_syncing_refused(self):
        primary, founder, find, get = scenario(node_syncing=True)
        with self.assertRaises(M.Hold):
            M.observe(primary, founder, find, get)

    def test_rpc_refuses_unapproved_path(self):
        with self.assertRaises(M.Hold):
            M.rpc_json("/broadcast_tx_sync", {})


if __name__ == "__main__":
    unittest.main()

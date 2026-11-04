#!/usr/bin/env python3
"""C04 historical founder #889 bounded Comet index correlation, NEVER a payout permit.

Root-only original request read; loopback-only historical index queries. Original
wallets, memos, request IDs, keys, query URLs and unrelated transaction hashes
NEVER emitted. A zero indexed match is not proof of nonpayment or chain finality.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
from urllib.parse import urlencode
from urllib.request import build_opener, HTTPRedirectHandler, Request

PRIMARY = Path("/mnt/HC_Volume_105319120/wolochain-mainnet/settlement-state/requests")
FOUNDER = Path("/mnt/HC_Volume_105319120/wolochain-mainnet/founder-rewards-settlement-state/requests")
FP100 = "2ed7062c8d9c44411401e4705fac55159dc3b2d936ad962459ef2869b126c020"
FP889 = "d3017b812ff439caa9c02578a9d65eb95960366c9d1f15749ed20a0418dcd715"
TX100_HEIGHT = 1078913
LOCAL_RPC = "http://127.0.0.1:27657"
ADDR = re.compile(r"wolo1[0-9a-z]{30,90}\Z")
HASH64 = re.compile(r"[0-9a-fA-F]{64}\Z")
MAX_FILES = 10000
MAX_BYTES = 1048576
MAX_INDEX_ITEMS = 20


class Hold(ValueError):
    pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def load_original(folder: Path, fingerprint: str, amount: str, status: str) -> dict:
    if not HASH64.fullmatch(fingerprint) or not folder.is_dir() or folder.is_symlink():
        raise Hold("INVALID_PROTECTED_ROOT")
    entries = list(folder.iterdir())
    if len(entries) > MAX_FILES:
        raise Hold("UNBOUNDED_REQUEST_INVENTORY")
    found = [p for p in entries if p.name.endswith(".json") and
             hashlib.sha256(p.name[:-5].encode()).hexdigest() == fingerprint]
    if len(found) != 1:
        raise Hold("ORIGINAL_REQUEST_AMBIGUOUS_OR_MISSING")
    p = found[0]
    s = p.lstat()
    if not stat.S_ISREG(s.st_mode) or p.is_symlink() or s.st_size > MAX_BYTES:
        raise Hold("ORIGINAL_REQUEST_UNSAFE")
    fd = os.open(p, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        before = os.fstat(fd)
        data = bytearray()
        while len(data) <= MAX_BYTES:
            chunk = os.read(fd, min(65536, MAX_BYTES + 1 - len(data)))
            if not chunk:
                break
            data.extend(chunk)
        after = os.fstat(fd)
        if len(data) > MAX_BYTES or (
            before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns
        ) != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
            raise Hold("ORIGINAL_REQUEST_CHANGED")
    finally:
        os.close(fd)
    try:
        record = json.loads(data)
        req = record["request"]
        rsp = record["response"]
        original_id = p.name[:-5]
        if req["request_id"] != original_id or rsp["request_id"] != original_id:
            raise Hold("REQUEST_IDENTITY_MISMATCH")
        if req["amount_uwolo"] != amount or rsp["status"] != status:
            raise Hold("HISTORICAL_REQUEST_STATUS_MISMATCH")
        if not ADDR.fullmatch(req["to_address"]) or not isinstance(req["memo"], str):
            raise Hold("HISTORICAL_REQUEST_SHAPE")
        if not 0 < len(req["memo"]) <= 1024:
            raise Hold("HISTORICAL_MEMO_SHAPE")
        return {
            "to": req["to_address"], "sender": rsp.get("signer_address", ""),
            "amount": req["amount_uwolo"], "status": status,
            "txhash": rsp.get("tx_hash") or "",
            "retryable": rsp.get("retryable"),
            "record_sha256": hashlib.sha256(data).hexdigest(),
        }
    except (ValueError, TypeError, KeyError) as exc:
        raise Hold("INVALID_PROTECTED_REQUEST") from exc


def rpc_json(path: str, params: dict[str, str | int]) -> dict:
    if path not in ("/tx_search", "/block", "/status"):
        raise Hold("RPC_PATH_NOT_APPROVED")
    url = LOCAL_RPC + path + ("?" + urlencode(params) if params else "")
    opener = build_opener(NoRedirect())
    response = opener.open(Request(url, method="GET"), timeout=8)
    try:
        if response.geturl() != url:
            raise Hold("RPC_REDIRECT_REFUSED")
        blob = response.read(2 * 1024 * 1024 + 1)
        if len(blob) > 2 * 1024 * 1024:
            raise Hold("RPC_RESPONSE_TOO_LARGE")
        value = json.loads(blob)
        if not isinstance(value, dict) or value.get("error"):
            raise Hold("RPC_RESULT_UNAVAILABLE")
        return value["result"]
    finally:
        response.close()


def find(query: str, limit: int = MAX_INDEX_ITEMS) -> tuple[int, list]:
    if not isinstance(query, str) or not (0 < len(query) <= 500):
        raise Hold("INVALID_QUERY")
    if not isinstance(limit, int) or not 1 <= limit <= MAX_INDEX_ITEMS:
        raise Hold("INVALID_INDEX_LIMIT")
    output = rpc_json("/tx_search", {"query": json.dumps(query), "per_page": limit,
                                      "page": 1, "order_by": json.dumps("asc")})
    if not isinstance(output, dict) or not str(output.get("total_count", "")).isdecimal():
        raise Hold("INDEX_COUNT_UNKNOWN")
    n = int(output["total_count"])
    txs = output.get("txs") or []
    if n < 0 or n >= 100000 or not isinstance(txs, list) or len(txs) != min(n, limit):
        raise Hold("INDEX_RESPONSE_INCONSISTENT")
    return n, txs


def observe(primary: dict, founder: dict, query=find, get=rpc_json) -> dict:
    if primary["status"] != "accepted" or primary["amount"] != "100000000" or (
        not HASH64.fullmatch(primary["txhash"])
    ):
        raise Hold("POSITIVE_CONTROL_INVALID")
    if founder["status"] != "failed" or founder["amount"] != "300000000" or (
        founder["txhash"] or founder["retryable"] is not True
    ):
        raise Hold("FOUNDER_SOURCE_NOT_AMBIGUOUS")
    to, sender = founder["to"], founder["sender"]
    if not ADDR.fullmatch(to) or not ADDR.fullmatch(sender):
        raise Hold("FOUNDER_SENDER_OR_RECIPIENT_UNAVAILABLE")
    control_q = "tx.height = 1078913 AND transfer.recipient = '" + primary["to"] + "'"
    positive, known_txs = query(control_q, 2)
    if positive != 1 or len(known_txs) != 1 or (
        known_txs[0]["hash"].upper() != primary["txhash"].upper() or
        known_txs[0]["tx_result"].get("code", 0) != 0
    ):
        raise Hold("HISTORICAL_TX_INDEX_POSITIVE_CONTROL_FAILED")
    prefix_to = "transfer.recipient = '" + to + "'"
    prefix_from = "transfer.sender = '" + sender + "'"
    any_recipient, recipient_txs = query(prefix_to)
    exact, _ = query(prefix_to + " AND transfer.amount = '300000000uwolo'")
    sender_300, sender_txs = query(prefix_from + " AND transfer.amount = '300000000uwolo'")
    from_to, from_to_txs = query(prefix_from + " AND " + prefix_to)
    if sender_300 > MAX_INDEX_ITEMS or from_to > MAX_INDEX_ITEMS:
        raise Hold("MATCH_CANDIDATE_ENUMERATION_UNBOUNDED")
    observations = []
    for kind, txs in (("sender_amount", sender_txs), ("sender_recipient", from_to_txs)):
        for tx in txs:
            if tx["tx_result"].get("code", 0) != 0 or not HASH64.fullmatch(tx["hash"]):
                raise Hold("FAILED_OR_MALFORMED_INDEXED_TX")
            height = int(tx["height"])
            if height < 1:
                raise Hold("INDEX_HEIGHT_INVALID")
            events = tx["tx_result"].get("events") or []
            recipient_matches = False
            amount_matches = False
            for event in events:
                if event.get("type") != "transfer":
                    continue
                attributes = {a["key"]: a["value"] for a in event.get("attributes", [])}
                if attributes.get("sender") != sender:
                    continue
                recipient_matches |= attributes.get("recipient") == to
                amount_matches |= attributes.get("amount") == "300000000uwolo"
            block = get("/block", {"height": height})
            header = block["block"]["header"]
            if header["chain_id"] != "wolo-1" or int(header["height"]) != height:
                raise Hold("HISTORICAL_HEADER_MISMATCH")
            observations.append({
                "class": kind, "height": height,
                "block_date": str(header["time"])[:10],
                "tx_hash_fingerprint": hashlib.sha256(tx["hash"].encode()).hexdigest(),
                "recipient_matches_original": recipient_matches,
                "amount_300wolo_matches_original": amount_matches,
            })
    status = get("/status", {})
    if status["node_info"]["network"] != "wolo-1" or status["sync_info"]["catching_up"] is not False:
        raise Hold("SOURCE_NODE_NOT_READY")
    return {
        "schema": "wolo.c04.founder889.indexed-transfer-noncrediting.v1",
        "status": "HOLD",
        "source": "single_operator_local_txindex_nonindependent",
        "chain_id": "wolo-1",
        "node_height": int(status["sync_info"]["latest_block_height"]),
        "original_request_sha256": founder["record_sha256"],
        "original_request_id_sha256": FP889,
        "original_signer_sha256": hashlib.sha256(sender.encode()).hexdigest(),
        "original_recipient_sha256": hashlib.sha256(to.encode()).hexdigest(),
        "known_positive_100wolo_control_found": True,
        "original_recipient_indexed_any_amount": any_recipient,
        "original_recipient_indexed_exact_300wolo": exact,
        "original_sender_indexed_exact_300wolo": sender_300,
        "original_sender_to_original_recipient_any_amount": from_to,
        "enumerated_other_candidates": observations,
        "recipient_index_count_fully_enumerated": any_recipient <= MAX_INDEX_ITEMS,
        "chain_index_historical_completeness_proven": False,
        "independent_chain_trust_root_verified": False,
        "no_unindexed_payment_proven": False,
        "founder889_payment_fate": "UNKNOWN",
        "retry_authorized": False,
        "financial_release_authorized": False,
        "c04_closed": False,
        "funds_moved": False,
        "production_mutated": False,
    }


def main(argv: list[str]) -> int:
    if argv not in ([], ["--inspect"]) or os.geteuid() != 0:
        print('{"status":"STOP","reason":"ROOT_ONLY_FIXED_INSPECTION","financial_release_authorized":false}')
        return 2
    try:
        primary = load_original(PRIMARY, FP100, "100000000", "accepted")
        founder = load_original(FOUNDER, FP889, "300000000", "failed")
        report = observe(primary, founder)
        print(json.dumps(report, sort_keys=True))
    except (Hold, OSError, TypeError, KeyError, ValueError, TimeoutError):
        print('{"status":"HOLD","reason":"HISTORICAL_INDEX_CORRELATION_UNAVAILABLE","retry_authorized":false,"c04_closed":false}')
    return 3


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

#!/usr/bin/env python3
"""C04 founder #889: pin local indexed evidence and refuse a false 300 WOLO payout.

No locally indexed transfer is proven to match BOTH original amount and
recipient. This cannot establish absence globally: single operator, incomplete
historical consensus/trust proof, and hashless original attempt. Never settle,
refund, rebroadcast or permit funds from this packet. Exit 3/HOLD, 2/STOP.
Offline, no database, network, signer, filesystem mutation or service startup.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys

SCHEMA = "wolo.c04.founder889-matched-payment-quarantine.v1"
EVIDENCE_SCHEMA = "wolo.c04.founder889.indexed-transfer-noncrediting.v1"
SOURCE_SHA256 = "5ba9e9aa43b14d39918f8fdee1b10efe3079c6969239c6aeba91f935f45412af"
ROOT_KEYS = frozenset({
    "c04_closed", "chain_id", "chain_index_historical_completeness_proven",
    "enumerated_other_candidates", "financial_release_authorized",
    "founder889_payment_fate", "funds_moved",
    "independent_chain_trust_root_verified", "known_positive_100wolo_control_found",
    "no_unindexed_payment_proven", "node_height",
    "original_recipient_indexed_any_amount", "original_recipient_indexed_exact_300wolo",
    "original_recipient_sha256", "original_request_id_sha256",
    "original_request_sha256", "original_sender_indexed_exact_300wolo",
    "original_sender_to_original_recipient_any_amount", "original_signer_sha256",
    "production_mutated", "recipient_index_count_fully_enumerated",
    "retry_authorized", "schema", "source", "status",
})
CANDIDATE_KEYS = frozenset({
    "amount_300wolo_matches_original", "block_date", "class", "height",
    "recipient_matches_original", "tx_hash_fingerprint",
})
SHA64 = re.compile(r"[a-f0-9]{64}\Z")
DAY = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}\Z")
MAX_BYTES = 262144


class HoldError(ValueError):
    pass


def require(test: bool, why: str):
    if not test:
        raise HoldError(why)


def unique(pairs):
    obj = {}
    for k, v in pairs:
        require(k not in obj, "DUPLICATE_JSON_KEY")
        obj[k] = v
    return obj


def no_nan(_):
    raise HoldError("NONFINITE_JSON")


def read_original_private(path: Path) -> dict:
    require(path.is_absolute() and ".." not in path.parts,
            "PRIVATE_EVIDENCE_PATH_UNSAFE")
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
        try:
            before = os.fstat(fd)
            require(stat.S_ISREG(before.st_mode)
                    and 0 < before.st_size <= MAX_BYTES,
                    "PRIVATE_EVIDENCE_SIZE_OR_TYPE")
            require(before.st_uid == os.geteuid()
                    and stat.S_IMODE(before.st_mode) == 0o600,
                    "PRIVATE_EVIDENCE_MODE_OR_OWNER")
            raw = bytearray()
            while len(raw) <= MAX_BYTES:
                part = os.read(fd, min(65536, MAX_BYTES + 1 - len(raw)))
                if not part:
                    break
                raw.extend(part)
            after = os.fstat(fd)
            fields = ("st_dev", "st_ino", "st_uid", "st_mode", "st_size",
                      "st_mtime_ns", "st_ctime_ns")
            require(len(raw) == before.st_size and all(
                getattr(before, key) == getattr(after, key) for key in fields),
                "PRIVATE_EVIDENCE_CHANGED_DURING_READ")
        finally:
            os.close(fd)
    except OSError:
        raise HoldError("PRIVATE_EVIDENCE_UNAVAILABLE") from None
    require(hashlib.sha256(raw).hexdigest() == SOURCE_SHA256,
            "PRIVATE_EVIDENCE_PIN_MISMATCH")
    try:
        result = json.loads(raw.decode("utf-8", "strict"),
                            object_pairs_hook=unique, parse_constant=no_nan)
    except (UnicodeError, ValueError, RecursionError):
        raise HoldError("PRIVATE_EVIDENCE_JSON_INVALID") from None
    require(type(result) is dict, "PRIVATE_EVIDENCE_SHAPE_INVALID")
    return result


def classify(doc: dict) -> dict:
    require(type(doc) is dict and set(doc) == ROOT_KEYS
            and doc["schema"] == EVIDENCE_SCHEMA and doc["chain_id"] == "wolo-1"
            and doc["status"] == "HOLD"
            and doc["source"] == "single_operator_local_txindex_nonindependent",
            "FOUNDER_SOURCE_OR_SCHEMA_DRIFT")
    require(all(doc[k] is False for k in (
                "c04_closed", "chain_index_historical_completeness_proven",
                "financial_release_authorized", "funds_moved",
                "independent_chain_trust_root_verified",
                "no_unindexed_payment_proven", "production_mutated",
                "retry_authorized"))
            and doc["founder889_payment_fate"] == "UNKNOWN"
            and doc["known_positive_100wolo_control_found"] is True
            and doc["recipient_index_count_fully_enumerated"] is True,
            "FOUNDER_UNKNOWN_OR_INDEPENDENT_TRUST_FABRICATED")
    require(all(type(doc[k]) is int and doc[k] == val for k, val in (
        ("node_height", 2825757),
        ("original_recipient_indexed_any_amount", 7),
        ("original_recipient_indexed_exact_300wolo", 0),
        ("original_sender_indexed_exact_300wolo", 1),
        ("original_sender_to_original_recipient_any_amount", 2),
    )), "FOUNDER_LOCAL_INDEX_METRICS_DRIFT")
    require(all(type(doc[k]) is str and SHA64.fullmatch(doc[k]) is not None
                and doc[k] != "0" * 64 for k in (
                    "original_recipient_sha256", "original_request_id_sha256",
                    "original_request_sha256", "original_signer_sha256")),
            "FOUNDER_ORIGINAL_REQUEST_PINS_MISSING")
    rows = doc["enumerated_other_candidates"]
    require(type(rows) is list and len(rows) == 3, "FOUNDER_LOCAL_CANDIDATE_COVERAGE_DRIFT")
    seen_hashes, seen_heights, sender_amount, sender_recipient = set(), set(), 0, 0
    for row in rows:
        require(type(row) is dict and set(row) == CANDIDATE_KEYS,
                "FOUNDER_CANDIDATE_SHAPE_DRIFT")
        name = row["class"]
        require(type(name) is str and name in {"sender_amount", "sender_recipient"},
                "FOUNDER_CANDIDATE_CLASS_DRIFT")
        require(type(row["height"]) is int and 0 < row["height"] <= doc["node_height"]
                and row["height"] not in seen_heights,
                "FOUNDER_CANDIDATE_HEIGHT_DRIFT")
        seen_heights.add(row["height"])
        tx = row["tx_hash_fingerprint"]
        require(type(tx) is str and SHA64.fullmatch(tx) is not None
                and tx not in seen_hashes and tx != "0" * 64,
                "FOUNDER_CANDIDATE_TX_IDENTITY_DRIFT")
        seen_hashes.add(tx)
        require(type(row["block_date"]) is str and DAY.fullmatch(row["block_date"])
                is not None, "FOUNDER_CANDIDATE_DATE_DRIFT")
        require(type(row["recipient_matches_original"]) is bool
                and type(row["amount_300wolo_matches_original"]) is bool
                and not (row["recipient_matches_original"]
                         and row["amount_300wolo_matches_original"]),
                "FOUNDER_UNJUSTIFIED_MATCHED_PAYMENT")
        if name == "sender_amount":
            require(row["recipient_matches_original"] is False
                    and row["amount_300wolo_matches_original"] is True,
                    "FOUNDER_CANDIDATE_ORIGINAL_MATCH_DRIFT")
            sender_amount += 1
        else:
            require(row["recipient_matches_original"] is True
                    and row["amount_300wolo_matches_original"] is False,
                    "FOUNDER_CANDIDATE_ORIGINAL_MATCH_DRIFT")
            sender_recipient += 1
    require(sender_amount == 1 and sender_recipient == 2,
            "FOUNDER_CANDIDATE_DISTRIBUTION_DRIFT")
    return {
        "schema": SCHEMA, "status": "HOLD",
        "claim_id": 889, "original_claim_amount_wolo": 300,
        "source_sha256": SOURCE_SHA256,
        "local_sender_same_amount_other_recipient_count": sender_amount,
        "local_sender_recipient_other_amount_count": sender_recipient,
        "local_exact_sender_recipient_300wolo_count": 0,
        "known_positive_100wolo_control": True,
        "payment_fate": "UNKNOWN",
        "observed_single_operator_index_height": doc["node_height"],
        "single_operator_local_index_only": True,
        "independent_canonical_finality_proved": False,
        "historical_global_payment_absence_proved": False,
        "unpaid_proved": False, "paid_proved": False,
        "retry_authorized": False,
        "financial_release_authorized": False,
        "production_mutated": False,
        "next_evidence": "independently trusted historical complete chain coverage and original sender-recipient-amount transaction identity",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        report = classify(read_original_private(args.evidence))
    except HoldError as exc:
        print(json.dumps({"schema": SCHEMA, "status": "STOP",
                          "reason": str(exc), "financial_release_authorized": False},
                         sort_keys=True))
        return 2
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    return 3


if __name__ == "__main__":
    sys.exit(main())

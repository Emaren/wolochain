#!/usr/bin/env python3
"""C04 claim #9645: deny misattribution of overlapping historical 100-WOLO transfers.

This only validates the exact, private, SHA-pinned November 5 local-index
attribution packet. Its fourteen same-amount transfers belong to already
referenced wager payouts and other claims. NOT a negative chain proof; missing
payout hash is NOT evidence of nonpayment. It cannot issue a refund, retry
an UNKNOWN, classify an actual payment or authorize a canary.

Offline and nonmutating. No network, filesystem writes, database, keyring,
token, signing or financial service activation. Exit 3/HOLD or 2/STOP.
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

SCHEMA = "wolo.c04.claim9645-payout-overlap-quarantine.v1"
INPUT_SCHEMA = "wolo.c04-9645-attribution-observation.v1"
SOURCE_SHA256 = "e260fbc599da012d9ac1480caed97a6f1ecbc369e7924587fb0a3c7682fa17b5"
ROOT_KEYS = {
    "schema", "captured_utc", "claim_created_after_attempt", "claim_id",
    "claim_payout_hash_absent", "claim_pending", "claim_retry_authorized",
    "financial_mutation", "independent_consensus_and_complete_coverage_proven",
    "indexed_candidate_count", "indexed_candidates", "local_index_max_height",
    "local_index_rows", "market_id", "market_voided",
    "refund_9645_paid_or_unpaid_proven", "refund_failed", "trust_limit",
    "wager_amount_wolo", "wager_count",
}
CANDIDATE_KEYS = {
    "amount_uwolo", "hash", "height", "original_market_memo", "other_claim_refs",
    "timestamp", "wager_payout_refs",
}
HASH64 = re.compile(r"[A-F0-9]{64}\Z")
TIME = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}\Z")
MAX_BYTES = 262144


class HoldError(ValueError):
    pass


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise HoldError(reason)


def unique_pairs(pairs):
    obj = {}
    for key, value in pairs:
        require(key not in obj, "DUPLICATE_JSON_KEY")
        obj[key] = value
    return obj


def reject_constant(_):
    raise HoldError("NONFINITE_JSON_NUMBER")


def read_exact_private(path: Path) -> dict:
    require(path.is_absolute() and ".." not in path.parts,
            "PRIVATE_INPUT_PATH_NOT_CANONICAL")
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
        try:
            before = os.fstat(fd)
            require(stat.S_ISREG(before.st_mode)
                    and 0 < before.st_size <= MAX_BYTES,
                    "PRIVATE_INPUT_NOT_BOUNDED_REGULAR")
            require(before.st_uid == os.geteuid()
                    and stat.S_IMODE(before.st_mode) == 0o600,
                    "PRIVATE_INPUT_OWNER_OR_MODE_DRIFT")
            raw = bytearray()
            while len(raw) <= MAX_BYTES:
                piece = os.read(fd, min(65536, MAX_BYTES + 1 - len(raw)))
                if not piece:
                    break
                raw.extend(piece)
            after = os.fstat(fd)
            fields = ("st_dev", "st_ino", "st_uid", "st_mode", "st_size",
                      "st_mtime_ns", "st_ctime_ns")
            require(len(raw) == before.st_size
                    and all(getattr(before, k) == getattr(after, k) for k in fields),
                    "PRIVATE_INPUT_CHANGED_DURING_READ")
        finally:
            os.close(fd)
    except OSError:
        raise HoldError("PRIVATE_INPUT_UNAVAILABLE") from None
    require(hashlib.sha256(raw).hexdigest() == SOURCE_SHA256,
            "PRIVATE_INPUT_SHA256_DRIFT")
    try:
        obj = json.loads(raw.decode("utf-8", "strict"),
                         object_pairs_hook=unique_pairs, parse_constant=reject_constant)
    except (ValueError, UnicodeError, RecursionError):
        raise HoldError("PRIVATE_INPUT_INVALID_JSON") from None
    require(type(obj) is dict, "PRIVATE_INPUT_NOT_OBJECT")
    return obj


def classify(doc: dict) -> dict:
    require(type(doc) is dict and set(doc) == ROOT_KEYS
            and doc["schema"] == INPUT_SCHEMA
            and type(doc["captured_utc"]) is str
            and re.fullmatch(r"2026-11-05T[0-9:.]+[+]00:00", doc["captured_utc"])
            is not None
            and type(doc["trust_limit"]) is str
            and len(doc["trust_limit"]) > 10,
            "ATTRIBUTION_SOURCE_OR_SCHEMA_DRIFT")
    require(type(doc["claim_id"]) is int and doc["claim_id"] == 9645
            and type(doc["market_id"]) is int and doc["market_id"] == 946520
            and type(doc["wager_amount_wolo"]) is int
            and doc["wager_amount_wolo"] == 100
            and type(doc["wager_count"]) is int and doc["wager_count"] == 1,
            "CLAIM_OR_MARKET_IDENTITY_DRIFT")
    require(all(doc[k] is True for k in (
                "claim_created_after_attempt", "claim_payout_hash_absent",
                "claim_pending", "market_voided", "refund_failed"))
            and all(doc[k] is False for k in (
                "claim_retry_authorized", "financial_mutation",
                "independent_consensus_and_complete_coverage_proven",
                "refund_9645_paid_or_unpaid_proven")),
            "HISTORICAL_FINALITY_OR_RETRY_FABRICATED")
    require(type(doc["indexed_candidate_count"]) is int
            and doc["indexed_candidate_count"] == 14
            and type(doc["local_index_max_height"]) is int
            and doc["local_index_max_height"] == 2813553
            and type(doc["local_index_rows"]) is int
            and doc["local_index_rows"] == 4300
            and type(doc["indexed_candidates"]) is list
            and len(doc["indexed_candidates"]) == 14,
            "LOCAL_INDEX_COVERAGE_DRIFT")
    seen_hashes = set()
    seen_heights = set()
    for candidate in doc["indexed_candidates"]:
        require(type(candidate) is dict and set(candidate) == CANDIDATE_KEYS,
                "CANDIDATE_SHAPE_DRIFT")
        require(type(candidate["amount_uwolo"]) is int
                and candidate["amount_uwolo"] == 100000000,
                "CANDIDATE_AMOUNT_DRIFT")
        tx = candidate["hash"]
        height = candidate["height"]
        require(type(tx) is str and HASH64.fullmatch(tx) is not None
                and tx != "0" * 64 and tx not in seen_hashes,
                "CANDIDATE_TX_IDENTITY_DUPLICATE_OR_INVALID")
        seen_hashes.add(tx)
        require(type(height) is int and 0 < height <= doc["local_index_max_height"]
                and height not in seen_heights,
                "CANDIDATE_HEIGHT_DUPLICATE_OR_INVALID")
        seen_heights.add(height)
        require(type(candidate["timestamp"]) is str
                and TIME.fullmatch(candidate["timestamp"]) is not None,
                "CANDIDATE_TIMESTAMP_DRIFT")
        # The source's 'original_market_memo' is a boolean, not memo text;
        # do not infer a real memo or a unique recipient from it.
        require(candidate["original_market_memo"] is False
                and type(candidate["wager_payout_refs"]) is int
                and candidate["wager_payout_refs"] == 1
                and type(candidate["other_claim_refs"]) is int
                and candidate["other_claim_refs"] == 1,
                "CANDIDATE_ALREADY_ATTRIBUTED_OR_MEMO_DRIFT")
    return {
        "schema": SCHEMA, "status": "HOLD",
        "claim_id": 9645, "market_id": 946520,
        "original_claim_amount_wolo": 100,
        "indexed_other_100wolo_candidates": len(seen_hashes),
        "indexed_candidate_amount_uwolo": 100000000,
        "every_indexed_candidate_already_referenced": True,
        "observed_single_operator_index_rows": 4300,
        "observed_single_operator_index_max_height": 2813553,
        "source_sha256": SOURCE_SHA256,
        "same_operator_local_index_only": True,
        "locally_indexed_candidates_not_unique_refund_proof": True,
        "claimed_refund_payment_fate": "UNKNOWN",
        "independent_finality_or_complete_coverage_proved": False,
        "refund_paid_proved": False,
        "refund_unpaid_proved": False,
        "refund_due_proved": False,
        "retry_authorized": False,
        "financial_release_authorized": False,
        "production_mutated": False,
        "next_evidence": "authenticated original request, independently trusted full historical transfer/recipient coverage and linked refund settlement disposition",
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        doc = read_exact_private(args.evidence)
        result = classify(doc)
    except HoldError as exc:
        print(json.dumps({"schema": SCHEMA, "status": "STOP",
                          "reason": str(exc), "financial_release_authorized": False},
                         sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 3


if __name__ == "__main__":
    sys.exit(main())

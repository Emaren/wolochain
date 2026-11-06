#!/usr/bin/env python3
"""Fixed C04 market #261848 original-stake observation. NONCREDITING and NO RETRY.

This validates ONE private local Comet observation with a caller-provided
SHA-256. Local success + hashless payout is not independent canonical finality,
proof of unpaid refund, or approval to rebroadcast.
No network, PostgreSQL, wallet, signer or state mutation.
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

SCHEMA = "wolo.c04.market261848-original-stakes-quarantine.v1"
EVIDENCE_SCHEMA = "aoe2war.c04.market-261848-local-stake-evidence.v1"
EXPECTED_WAGERS = {394: (5000, 719485), 396: (800, 719690)}
ROOT_KEYS = {
    "schema", "source", "observed_utc", "market_id", "wagers", "amount_total_wolo",
    "local_stake_execution_proved", "independent_checkpoint_proved",
    "independent_recipient_amount_refund_disposition_proved", "refund_due_proved",
    "retry_authorized", "financial_release_authorized", "production_mutated",
}
WAGER_KEYS = {"id", "amount_wolo", "stake_hash", "payout_hash_absent", "local_comet"}
COMET_KEYS = {"execution_code", "height", "inclusion_proof_present", "rpc_hash", "stake_hash"}
HEX64 = re.compile(r"[0-9A-F]{64}\Z")
LOWER_SHA = re.compile(r"[a-f0-9]{64}\Z")
MAX_BYTES = 262144


class HoldError(ValueError):
    pass


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise HoldError(reason)


def unique(pairs):
    result = {}
    for k, v in pairs:
        require(k not in result, "DUPLICATE_JSON_KEY")
        result[k] = v
    return result


def read_exact_private(path: Path, expected_sha: str) -> tuple[dict, str]:
    require(type(expected_sha) is str and LOWER_SHA.fullmatch(expected_sha) is not None,
            "EXPECTED_EVIDENCE_DIGEST_INVALID")
    require(path.is_absolute() and ".." not in path.parts, "EVIDENCE_PATH_NOT_CANONICAL")
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
        try:
            before = os.fstat(fd)
            require(stat.S_ISREG(before.st_mode) and 0 < before.st_size <= MAX_BYTES,
                    "EVIDENCE_NOT_BOUNDED_FILE")
            require(before.st_uid == os.geteuid() and stat.S_IMODE(before.st_mode) == 0o600,
                    "EVIDENCE_OWNER_OR_MODE_DRIFT")
            raw = bytearray()
            while len(raw) <= MAX_BYTES:
                piece = os.read(fd, min(65536, MAX_BYTES + 1 - len(raw)))
                if not piece:
                    break
                raw.extend(piece)
            after = os.fstat(fd)
            fields = ("st_dev", "st_ino", "st_uid", "st_mode", "st_size", "st_mtime_ns", "st_ctime_ns")
            require(all(getattr(before, x) == getattr(after, x) for x in fields)
                    and len(raw) == before.st_size, "EVIDENCE_CHANGED_DURING_READ")
        finally:
            os.close(fd)
    except (OSError, ValueError) as exc:
        if type(exc) is HoldError:
            raise
        raise HoldError("EVIDENCE_UNAVAILABLE") from None
    actual = hashlib.sha256(raw).hexdigest()
    require(actual == expected_sha, "EVIDENCE_DIGEST_DRIFT")
    try:
        doc = json.loads(raw.decode("utf-8", "strict"),
                         object_pairs_hook=unique,
                         parse_constant=lambda _: require(False, "NONFINITE_JSON"))
    except (UnicodeError, ValueError, RecursionError) as exc:
        if type(exc) is HoldError:
            raise
        raise HoldError("EVIDENCE_JSON_INVALID") from None
    require(type(doc) is dict, "EVIDENCE_NOT_JSON_OBJECT")
    return doc, actual


def classify(doc: dict, evidence_sha256: str) -> dict:
    require(type(doc) is dict and set(doc) == ROOT_KEYS
            and doc["schema"] == EVIDENCE_SCHEMA and type(doc["source"]) is str
            and 0 < len(doc["source"]) <= 256
            and type(doc["observed_utc"]) is str and 10 <= len(doc["observed_utc"]) <= 64,
            "MARKET_EVIDENCE_SHAPE_DRIFT")
    require(type(doc["market_id"]) is int and doc["market_id"] == 261848
            and type(doc["amount_total_wolo"]) is int and doc["amount_total_wolo"] == 5800,
            "MARKET_ID_OR_AMOUNT_DRIFT")
    require(doc["local_stake_execution_proved"] is True
            and all(doc[k] is False for k in (
                "independent_checkpoint_proved",
                "independent_recipient_amount_refund_disposition_proved",
                "refund_due_proved", "retry_authorized", "financial_release_authorized",
                "production_mutated")), "UNSUPPORTED_PAYMENT_FINALITY_OR_AUTHORITY")
    require(type(doc["wagers"]) is list and len(doc["wagers"]) == len(EXPECTED_WAGERS),
            "MARKET_WAGER_COVERAGE_DRIFT")
    ids, hashes, amount_total, rows = set(), set(), 0, []
    for row in doc["wagers"]:
        require(type(row) is dict and set(row) == WAGER_KEYS
                and type(row["id"]) is int and row["id"] in EXPECTED_WAGERS,
                "WAGER_IDENTITY_DRIFT")
        wager_id = row["id"]
        require(wager_id not in ids, "WAGER_REUSED")
        ids.add(wager_id)
        amount, height = EXPECTED_WAGERS[wager_id]
        require(type(row["amount_wolo"]) is int and row["amount_wolo"] == amount
                and row["payout_hash_absent"] is True, "WAGER_AMOUNT_OR_PAYOUT_STATE_DRIFT")
        comet = row["local_comet"]
        require(type(comet) is dict and set(comet) == COMET_KEYS,
                "LOCAL_COMET_EVIDENCE_SHAPE_DRIFT")
        require(type(comet["execution_code"]) is int and comet["execution_code"] == 0
                and type(comet["height"]) is str and comet["height"] == str(height)
                and comet["inclusion_proof_present"] is True,
                "LOCAL_COMET_EXECUTION_OR_HEIGHT_DRIFT")
        tx = row["stake_hash"]
        require(type(tx) is str and HEX64.fullmatch(tx) is not None
                and tx == comet["stake_hash"] == comet["rpc_hash"] and tx not in hashes,
                "ORIGINAL_STAKE_IDENTITY_DRIFT")
        hashes.add(tx)
        amount_total += amount
        rows.append({"wager_id": wager_id, "stake_wolo": amount,
                     "local_execution_code_zero": True, "payout_hash_absent": True})
    require(ids == set(EXPECTED_WAGERS) and amount_total == doc["amount_total_wolo"],
            "MARKET_WAGER_SUM_DRIFT")
    require(type(evidence_sha256) is str and LOWER_SHA.fullmatch(evidence_sha256) is not None,
            "EVIDENCE_DIGEST_INVALID")
    return {
        "schema": SCHEMA, "status": "HOLD",
        "market_id": 261848, "original_stake_local_observation_wolo": amount_total,
        "wagers": sorted(rows, key=lambda x: x["wager_id"]),
        "input_sha256": evidence_sha256,
        "same_operator_local_comet_only": True,
        "independent_canonical_finality_proved": False,
        "payout_or_refund_unpaid_proved": False,
        "refund_due_proved": False,
        "retry_authorized": False,
        "financial_release_authorized": False,
        "production_mutated": False,
        "next_evidence": "independent canonical chain checkpoint and complete original-recipient amount refund disposition; no double-count or automatic retry",
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--sha256", required=True)
    args = parser.parse_args(argv)
    try:
        doc, digest = read_exact_private(args.evidence, args.sha256)
        report = classify(doc, digest)
    except HoldError as exc:
        print(json.dumps({"schema": SCHEMA, "status": "STOP", "reason": str(exc),
                          "financial_release_authorized": False}, sort_keys=True))
        return 2
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    return 3


if __name__ == "__main__":
    sys.exit(main())

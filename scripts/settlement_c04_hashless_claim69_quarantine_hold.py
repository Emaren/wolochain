#!/usr/bin/env python3
"""C04 all 69 'claimed' but hashless legacy/mainnet records: quarantine only.

The database word 'claimed' is NOT a Cosmos execution receipt. This utility
classifies an exact protected historical packet without asserting any of its
69 transfer fates, crediting balances, retrying requests, or double-counting
its nominal 120,443 WOLO with wager principal, founders or C05 liabilities.

Source is a local READ ONLY / REPEATABLE READ PostgreSQL snapshot, NOT an
atomic authenticated Comet history or an independently trusted bank proof.
No network/database queries, no disk writes, no wallet, signer or state change.
Exit 3/HOLD or 2/STOP. Never a C04 physical acceptance certificate.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys

SCHEMA = "wolo.c04.hashless69-claimed-unknown-quarantine.v1"
EVIDENCE_SCHEMA = "wolo.c04.mainnet-hashless-claimed-reconciliation-scope.v1"
PACKET_SHA256 = "87662f2185281af4876d6ebcfe677d12d2df89593fe2f494b320d3e941bdb95e"
GROUPS = {
    ("legacy_era", "bet_payout"): (5, 600),
    ("mainnet_era", "bet_payout"): (10, 108904),
    ("mainnet_era", "bet_refund"): (3, 6801),
    ("mainnet_era", "founders_bonus"): (51, 4138),
}
ROOT_KEYS = frozenset({
    "all_payment_fates_independently_proven", "app_mainnet_era_cutoff_utc",
    "captured_utc", "claims", "db_observation", "financial_release_authorized",
    "founder_source_status_summary", "groups", "legacy_recorded_amount_wolo",
    "legacy_rows", "local_source_status_equals_onchain_execution",
    "mainnet_recorded_amount_wolo", "mainnet_rows",
    "marked_claimed_equals_paid", "production_mutated",
    "recorded_amount_total_wolo", "refund_or_founder_retry_authorized",
    "schema", "source_snapshot_and_comet_atomic",
    "total_claimed_without_hash_rows",
})
ROW_KEYS = frozenset({
    "claim_id", "claim_kind", "claimed_without_payout_tx_hash",
    "created_at", "era", "founder_bonus_request_id_present",
    "founder_bonus_status", "market_settlement_failure_code",
    "market_settlement_status", "market_status", "payout_attempted_at_present",
    "payout_proof_url_present", "recorded_amount_wolo",
    "same_market_stake_hash_present_wager_payout_hash_missing_count",
    "source_founder_bonus_id", "source_market_id",
})
ROW_DATE = re.compile(r"20[0-9]{2}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}(?:[.][0-9]{1,6})?\Z")
MAX_BYTES = 262144


class HoldError(ValueError):
    pass


def require(ok: bool, label: str):
    if not ok:
        raise HoldError(label)


def unique(pairs):
    obj = {}
    for k, v in pairs:
        require(k not in obj, "DUPLICATE_JSON_KEY")
        obj[k] = v
    return obj


def no_floats_or_infinity(value):
    raise HoldError("NONCANONICAL_JSON_NUMBER")


def read_exact_private(path: Path) -> dict:
    require(path.is_absolute() and ".." not in path.parts,
            "PRIVATE_C04_PACKET_PATH_INVALID")
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
        try:
            start = os.fstat(fd)
            require(stat.S_ISREG(start.st_mode)
                    and 0 < start.st_size <= MAX_BYTES,
                    "PRIVATE_C04_PACKET_NOT_BOUNDED")
            require(start.st_uid == os.geteuid()
                    and stat.S_IMODE(start.st_mode) == 0o600,
                    "PRIVATE_C04_PACKET_OWNER_OR_MODE_DRIFT")
            body = bytearray()
            while len(body) <= MAX_BYTES:
                part = os.read(fd, min(65536, MAX_BYTES + 1 - len(body)))
                if not part:
                    break
                body.extend(part)
            end = os.fstat(fd)
            keys = ("st_dev", "st_ino", "st_uid", "st_mode", "st_size",
                    "st_ctime_ns", "st_mtime_ns")
            require(len(body) == start.st_size and all(
                getattr(start, k) == getattr(end, k) for k in keys),
                "PRIVATE_C04_PACKET_CHANGED_DURING_READ")
        finally:
            os.close(fd)
    except OSError:
        raise HoldError("PRIVATE_C04_PACKET_UNAVAILABLE") from None
    require(hashlib.sha256(body).hexdigest() == PACKET_SHA256,
            "PRIVATE_C04_PACKET_SHA256_DRIFT")
    try:
        doc = json.loads(body.decode("utf-8", "strict"),
                         object_pairs_hook=unique, parse_constant=no_floats_or_infinity,
                         parse_float=no_floats_or_infinity)
    except (ValueError, UnicodeError, RecursionError):
        raise HoldError("PRIVATE_C04_PACKET_INVALID_JSON") from None
    require(type(doc) is dict, "PRIVATE_C04_PACKET_NOT_OBJECT")
    return doc


def classify(doc: dict) -> dict:
    require(type(doc) is dict and set(doc) == ROOT_KEYS
            and doc["schema"] == EVIDENCE_SCHEMA
            and doc["db_observation"] == "HD PostgreSQL repeatable-read read-only"
            and doc["app_mainnet_era_cutoff_utc"] == "2026-05-25T00:00:00Z"
            and type(doc["captured_utc"]) is str
            and doc["captured_utc"].startswith("2026-11-05T"),
            "C04_SOURCE_OR_SCHEMA_DRIFT")
    require(all(doc[k] is False for k in (
                "all_payment_fates_independently_proven",
                "financial_release_authorized", "local_source_status_equals_onchain_execution",
                "marked_claimed_equals_paid", "production_mutated",
                "refund_or_founder_retry_authorized",
                "source_snapshot_and_comet_atomic")),
            "C04_DATABASE_STATUS_FABRICATED_AS_PAYMENT")
    require(all(type(doc[k]) is int and doc[k] == v for k, v in (
        ("total_claimed_without_hash_rows", 69),
        ("recorded_amount_total_wolo", 120443),
        ("legacy_rows", 5), ("legacy_recorded_amount_wolo", 600),
        ("mainnet_rows", 64), ("mainnet_recorded_amount_wolo", 119843),
    )), "C04_GLOBAL_SCOPE_TOTALS_DRIFT")
    require(type(doc["founder_source_status_summary"]) is dict
            and doc["founder_source_status_summary"] == {"failed": 11, "partial": 40},
            "C04_FOUNDER_STATUS_CENSUS_DRIFT")
    groups = doc["groups"]
    require(type(groups) is list and len(groups) == len(GROUPS),
            "C04_AGGREGATE_GROUP_SHAPE_DRIFT")
    reported = {}
    for item in groups:
        require(type(item) is dict and set(item) ==
                {"claim_kind", "era", "recorded_amount_wolo", "rows"},
                "C04_GROUP_FIELDS_DRIFT")
        k = (item["era"], item["claim_kind"])
        require(k in GROUPS and k not in reported
                and type(item["rows"]) is int
                and type(item["recorded_amount_wolo"]) is int,
                "C04_GROUP_IDENTITY_DRIFT")
        reported[k] = (item["rows"], item["recorded_amount_wolo"])
    require(reported == GROUPS, "C04_GROUP_RECORDED_SUMS_DRIFT")
    rows = doc["claims"]
    require(type(rows) is list and len(rows) == 69,
            "C04_HASHLESS_CLAIM_POPULATION_DRIFT")
    sums = defaultdict(lambda: [0, 0])
    founders_status = defaultdict(int)
    ids, commitments = set(), []
    for row in rows:
        require(type(row) is dict and set(row) == ROW_KEYS,
                "C04_CLAIM_ROW_FIELDS_DRIFT")
        claim = row["claim_id"]
        require(type(claim) is int and claim > 0 and claim not in ids
                and claim not in (889, 9645),
                "C04_DUPLICATE_OR_PENDING_CLAIM_MISCLASSIFIED")
        ids.add(claim)
        group = (row["era"], row["claim_kind"])
        require(group in GROUPS
                and row["claimed_without_payout_tx_hash"] is True
                and row["market_status"] == "settled"
                and row["payout_proof_url_present"] is False
                and type(row["payout_attempted_at_present"]) is bool
                and type(row["founder_bonus_request_id_present"]) is bool,
                "C04_UNPROVED_PAYOUT_STATUS_DRIFT")
        amount = row["recorded_amount_wolo"]
        require(type(amount) is int and 0 < amount <= 25000
                and type(row["source_market_id"]) is int
                and row["source_market_id"] > 0
                and type(row["created_at"]) is str
                and ROW_DATE.fullmatch(row["created_at"]) is not None,
                "C04_CLAIM_MONEY_OR_DATE_DRIFT")
        require(type(row["same_market_stake_hash_present_wager_payout_hash_missing_count"])
                is int
                and 0 <= row["same_market_stake_hash_present_wager_payout_hash_missing_count"] <= 2,
                "C04_STAKE_OVERLAP_METADATA_DRIFT")
        require(row["market_settlement_status"] in
                (None, "pending", "executed", "failed", "dry_run")
                and row["market_settlement_failure_code"] in
                (None, "PAYOUT_RESERVE_FLOOR_HIT", "PAYOUT_BALANCE_TOO_LOW",
                 "ADMIN_RETRY_FAILED"),
                "C04_SETTLEMENT_STATUS_NOT_CHAIN_FINALITY")
        if row["claim_kind"] == "founders_bonus":
            require(type(row["source_founder_bonus_id"]) is int
                    and row["source_founder_bonus_id"] > 0
                    and row["founder_bonus_status"] in ("failed", "partial"),
                    "C04_FOUNDER_SOURCE_MISSING")
            founders_status[row["founder_bonus_status"]] += 1
        else:
            require(row["source_founder_bonus_id"] is None
                    and row["founder_bonus_status"] is None,
                    "C04_NONFOUNDER_DOUBLE_CLAIM_SOURCE")
        sums[group][0] += 1
        sums[group][1] += amount
        commitments.append((claim, row["era"], row["claim_kind"], amount))
    require({k:tuple(v) for k,v in sums.items()} == GROUPS,
            "C04_CLAIM_ROW_SUMS_DISAGREE_WITH_AGGREGATES")
    require(dict(founders_status) == {"failed": 11, "partial": 40},
            "C04_FOUNDER_SOURCE_STATUS_DRIFT")
    identity_root = hashlib.sha256(json.dumps(
        sorted(commitments), separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()
    return {
        "schema": SCHEMA, "status": "HOLD",
        "input_sha256": PACKET_SHA256,
        "claim_identity_amount_commitment_sha256": identity_root,
        "claimed_nohash_claims_quarantined_as_UNKNOWN": len(ids),
        "nonadditive_recorded_nominal_wolo": sum(amount for *_, amount in commitments),
        "legacy_recorded_nominal_wolo": 600,
        "mainnet_recorded_nominal_wolo": 119843,
        "founder_bonus_claims": 51,
        "bet_payout_claims": 15,
        "bet_refund_claims": 3,
        "recorded_claimed_status_is_not_chain_payment_proof": True,
        "claim_889_and_9645_not_in_this_census": True,
        "historical_payment_dispositions_independently_proved": False,
        "total_is_not_additive_with_wagers_or_other_c05_buckets": True,
        "any_claim_paid_proved": False, "any_claim_unpaid_proved": False,
        "retry_authorized": False, "financial_release_authorized": False,
        "production_mutated": False,
        "next_evidence": "same-epoch independent canonical transfer proofs and complete per-claim original recipient/amount disposition; full HD/DE nonoverlap reserve census",
    }


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--evidence", type=Path, required=True)
    args = p.parse_args(argv)
    try:
        result = classify(read_exact_private(args.evidence))
    except HoldError as exc:
        print(json.dumps({"schema": SCHEMA, "status": "STOP",
                          "reason": str(exc), "financial_release_authorized": False},
                         sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 3


if __name__ == "__main__":
    sys.exit(main())

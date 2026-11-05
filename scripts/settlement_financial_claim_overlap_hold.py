#!/usr/bin/env python3
"""C04/C05 source-bound, non-additive liability identity check (NEVER release).

Reads four locally produced, owner-private observations, with no network/DB,
signing, payouts, writes, external tools, or payout recipient display.
A valid report exits 3 (financial HOLD); malformed/drifted evidence exits 2.
Individual observation timestamps do not form an atomic financial checkpoint.
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

VERSION = "wolo.c05.disjoint-legacy-liability-hold.v1"
MAX_BYTES = 2 * 1024 * 1024
DIGEST = re.compile(r"[a-f0-9]{64}\Z")


class GapError(ValueError):
    pass


def fail(code: str):
    raise GapError(code)


def pairs_unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            fail("DUPLICATE_JSON_KEY")
        result[key] = value
    return result


def read(path: Path, sha: str) -> dict:
    if not isinstance(sha, str) or not DIGEST.fullmatch(sha):
        fail("EXPECTED_DIGEST_INVALID")
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            before = os.fstat(fd)
            if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= MAX_BYTES:
                fail("SOURCE_NOT_BOUNDED_REGULAR_FILE")
            body = bytearray()
            while len(body) <= MAX_BYTES:
                chunk = os.read(fd, min(65536, MAX_BYTES + 1 - len(body)))
                if not chunk:
                    break
                body.extend(chunk)
            after = os.fstat(fd)
            keys = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
            if len(body) != before.st_size or any(getattr(before, k) != getattr(after, k) for k in keys):
                fail("SOURCE_CHANGED_DURING_READ")
        finally:
            os.close(fd)
        if hashlib.sha256(body).hexdigest() != sha:
            fail("SOURCE_DIGEST_MISMATCH")
        packet = json.loads(body.decode("utf-8"), object_pairs_hook=pairs_unique,
                            parse_constant=lambda _: fail("NONFINITE_JSON"))
        if type(packet) is not dict:
            fail("SOURCE_ROOT_INVALID")
        return packet
    except GapError:
        raise
    except (OSError, ValueError, UnicodeError, RecursionError):
        fail("SOURCE_UNAVAILABLE")


def nonnegative(value):
    if type(value) is not int or value < 0 or value > 10**15:
        fail("INVALID_NONNEGATIVE_INTEGER")
    return value


def strictly_false(doc: dict, *keys):
    if any(doc.get(k) is not False for k in keys):
        fail("UNSUPPORTED_FINANCIAL_AUTHORITY_ASSERTION")


def classify_claims(doc):
    if doc.get("schema") != "wolo.c04.mainnet-hashless-claimed-reconciliation-scope.v1":
        fail("CLAIM_SCHEMA_DRIFT")
    strictly_false(doc, "all_payment_fates_independently_proven",
                   "marked_claimed_equals_paid", "financial_release_authorized",
                   "refund_or_founder_retry_authorized", "production_mutated")
    entries = doc.get("claims")
    if type(entries) is not list or not 0 < len(entries) <= 50000:
        fail("CLAIM_ROWS_INVALID")
    seen = set()
    main = []
    grouped = {}
    for row in entries:
        if type(row) is not dict:
            fail("CLAIM_ROW_INVALID")
        cid = nonnegative(row.get("claim_id"))
        if cid in seen:
            fail("CLAIM_ID_DUPLICATE")
        seen.add(cid)
        amount = nonnegative(row.get("recorded_amount_wolo"))
        era = row.get("era")
        kind = row.get("claim_kind")
        if era not in ("mainnet_era", "legacy_era") or kind not in (
            "bet_payout", "bet_refund", "founders_bonus", "founders_win", "winner_bounty"
        ):
            fail("CLAIM_KIND_OR_ERA_INVALID")
        if row.get("claimed_without_payout_tx_hash") is not True:
            fail("CLAIM_HAS_PAYOUT_PROOF_OR_INVALID_FLAG")
        grouped[(era, kind)] = grouped.get((era, kind), 0) + amount
        if era == "mainnet_era":
            main.append(row)
    if (len(entries) != nonnegative(doc.get("total_claimed_without_hash_rows"))
        or len(main) != nonnegative(doc.get("mainnet_rows"))
        or sum(nonnegative(x["recorded_amount_wolo"]) for x in entries)
          != nonnegative(doc.get("recorded_amount_total_wolo"))
        or sum(x["recorded_amount_wolo"] for x in main)
          != nonnegative(doc.get("mainnet_recorded_amount_wolo"))):
        fail("CLAIM_SUMMARY_DRIFT")
    return main, grouped


def classify_overlap(doc, main):
    if doc.get("schema") != "wolo.c05.claim-wager-overlap-readonly.v1":
        fail("OVERLAP_SCHEMA_DRIFT")
    strictly_false(doc, "claims_paid_or_unpaid_independently_proven",
                   "financial_release_authorized", "retry_authorized",
                   "production_mutated")
    cases = doc.get("cases")
    if type(cases) is not list or not 0 < len(cases) <= 10000:
        fail("OVERLAP_ROWS_INVALID")
    by_id = {x["claim_id"]: x for x in main}
    seen = set()
    payout_markets = {}
    tally = {"bet_payout": [0, 0, 0], "bet_refund": [0, 0, 0]}
    for row in cases:
        if type(row) is not dict:
            fail("OVERLAP_ROW_INVALID")
        cid = nonnegative(row.get("claim_id"))
        if cid in seen or cid not in by_id:
            fail("OVERLAP_ID_MISSING_OR_DUPLICATE")
        seen.add(cid)
        parent = by_id[cid]
        kind = row.get("claim_kind")
        if kind not in tally or kind != parent["claim_kind"] or row.get("market_id") != parent.get("source_market_id"):
            fail("OVERLAP_CLAIM_IDENTITY_CONFLICT")
        original = nonnegative(row.get("claim_amount_wolo"))
        wager_value = nonnegative(row.get("same_market_wager_expected_or_original_stake_wolo"))
        matched = nonnegative(row.get("same_market_staked_no_payout_wager_count"))
        if original != parent["recorded_amount_wolo"] or matched == 0:
            fail("OVERLAP_CLAIM_AMOUNT_OR_WAGER_ABSENT")
        if kind == "bet_payout":
            if wager_value != original:
                fail("PAYOUT_WAGER_MARKET_NOT_EXACT")
            market = nonnegative(row["market_id"])
            if market in payout_markets:
                fail("PAYOUT_MARKET_CLAIM_DUPLICATED")
            payout_markets[market] = (original, matched)
        tally[kind][0] += 1
        tally[kind][1] += original
        tally[kind][2] += wager_value
    for kind, label in (("bet_payout", "bet_payout_claims_without_hash"),
                        ("bet_refund", "bet_refund_claims_without_hash")):
        if tally[kind][0] != nonnegative(doc.get(label)):
            fail("OVERLAP_COUNT_DRIFT")
    if (tally["bet_payout"][1] != nonnegative(doc.get("bet_payout_claimed_wolo"))
        or tally["bet_payout"][2] != nonnegative(doc.get("matched_winner_expected_payout_wolo"))
        or tally["bet_refund"][1] != nonnegative(doc.get("bet_refund_claimed_wolo"))
        or tally["bet_refund"][2] != nonnegative(doc.get("same_market_original_voided_stakes_wolo"))
        or tally["bet_refund"][2] - tally["bet_refund"][1]
           != nonnegative(doc.get("one_market_excess_original_staked_amount_not_matched_by_claim_wolo"))):
        fail("OVERLAP_AMOUNT_DRIFT")
    return tally, payout_markets


def classify_winners(doc, overlap, payout_markets):
    if doc.get("schema") != "wolo.c05.legacy-winner-stake-verifiability.v1":
        fail("WINNER_SCHEMA_DRIFT")
    strictly_false(doc, "current_payout_due_and_unpaid_proven",
                   "disjoint_global_liability_bound_proven",
                   "financial_release_authorized", "production_mutated")
    rows = doc.get("records")
    if type(rows) is not list or not 0 < len(rows) <= 10000:
        fail("WINNER_ROWS_INVALID")
    seen = set()
    seen_stake_hashes = set()
    verified_market_payouts = {}
    verified_market_wagers = {}
    index_payout = no_index_payout = 0
    index_count = no_index_count = 0
    for row in rows:
        if type(row) is not dict:
            fail("WINNER_ROW_INVALID")
        wid = nonnegative(row.get("wager_id"))
        if wid in seen:
            fail("WINNER_WAGER_DUPLICATE")
        seen.add(wid)
        stake_hash = row.get("stake_tx_hash")
        if type(stake_hash) is not str or not DIGEST.fullmatch(stake_hash) or stake_hash in seen_stake_hashes:
            fail("WINNER_STAKE_HASH_DUPLICATED_OR_INVALID")
        seen_stake_hashes.add(stake_hash)
        market = nonnegative(row.get("market_id"))
        value = nonnegative(row.get("expected_payout_wolo"))
        index = nonnegative(row.get("local_index_matches"))
        if index not in (0, 1):
            fail("WINNER_INDEX_NOT_UNIQUE")
        if index == 1:
            if row.get("local_comet_receipt_state") != "LOCAL_EXECUTION_CODE_ZERO" or row.get("local_comet_tx_code") != 0:
                fail("WINNER_INDEXED_STAKE_NOT_EXECUTED")
            index_count += 1
            index_payout += value
            verified_market_payouts[market] = verified_market_payouts.get(market, 0) + value
            verified_market_wagers[market] = verified_market_wagers.get(market, 0) + 1
        else:
            no_index_count += 1
            no_index_payout += value
    if (len(rows) != nonnegative(doc.get("wagers"))
        or index_count != nonnegative(doc.get("indexed_stakes"))
        or no_index_count != nonnegative(doc.get("unindexed_stakes"))
        or index_payout != nonnegative(doc.get("indexed_original_payout_wolo"))
        or no_index_payout != nonnegative(doc.get("unindexed_original_payout_wolo"))
        or index_payout + no_index_payout != nonnegative(doc.get("recorded_expected_payout_wolo"))):
        fail("WINNER_SUMMARY_DRIFT")
    if overlap["bet_payout"][1] > index_payout:
        fail("PAYOUT_CLAIM_EXCEEDS_INDEXED_WINNER_EXPOSURE")
    for market, (amount, n) in payout_markets.items():
        if verified_market_payouts.get(market) != amount or verified_market_wagers.get(market) != n:
            fail("PAYOUT_CLAIM_WINNER_MARKET_COVERAGE_DRIFT")
    return index_count, no_index_count, index_payout, no_index_payout


def classify_active(doc):
    if doc.get("schema") != "wolo.c05.active-stake-escrow-match.v1":
        fail("ACTIVE_SCHEMA_DRIFT")
    strictly_false(doc, "global_solvency_certified", "financial_release_authorized", "production_mutated")
    entries = doc.get("entries")
    if type(entries) is not list or not 0 < len(entries) <= 10000:
        fail("ACTIVE_ROWS_INVALID")
    seen = set()
    seen_tx_hashes = set()
    principal = 0
    for row in entries:
        if type(row) is not dict:
            fail("ACTIVE_ROW_INVALID")
        wid = nonnegative(row.get("wager_id"))
        if wid in seen:
            fail("ACTIVE_WAGER_ID_DUPLICATE")
        seen.add(wid)
        tx_hash = row.get("tx_hash")
        if type(tx_hash) is not str or not DIGEST.fullmatch(tx_hash) or tx_hash in seen_tx_hashes:
            fail("ACTIVE_STAKE_HASH_DUPLICATED_OR_INVALID")
        seen_tx_hashes.add(tx_hash)
        value = row.get("principal_uwolo")
        if type(value) is not str or not re.fullmatch(r"(?:0|[1-9][0-9]{0,26})\Z", value):
            fail("ACTIVE_NONCANONICAL_UWOLO")
        principal += int(value)
        for key in ("indexed_sender_matches_wager_wallet", "indexed_recipient_matches_original_escrow",
                    "indexed_amount_matches_original_stake", "local_comet_proof_present"):
            if row.get(key) is not True:
                fail("ACTIVE_STAKE_EVIDENCE_INVALID")
        if row.get("local_comet_execution_code") != 0:
            fail("ACTIVE_STAKE_NOT_LOCALLY_EXECUTED")
    if len(entries) != nonnegative(doc.get("wager_count")) or str(principal) != doc.get("original_principal_uwolo"):
        fail("ACTIVE_PRINCIPAL_OR_COUNT_DRIFT")
    return len(entries), principal


def verify(claims, overlap, winners, active, hashes):
    main, grouped = classify_claims(claims)
    claim_tally, payout_markets = classify_overlap(overlap, main)
    win_index, win_unindexed, indexed_payout, unindexed_payout = classify_winners(
        winners, claim_tally, payout_markets)
    active_count, principal = classify_active(active)
    if set(hashes) != {"claims", "overlap", "winners", "active"} or any(
        type(v) is not str or not DIGEST.fullmatch(v) for v in hashes.values()
    ):
        fail("INPUT_HASH_SET_INVALID")
    return {
        "schema": VERSION, "status": "HOLD",
        "financial_release_authorized": False, "retry_authorized": False,
        "full_global_solvency_certified": False, "bank_consensus_authenticated": False,
        "observations_atomic_together": False, "production_mutated": False,
        "input_sha256": hashes,
        "NON_ADDITIVE": {
            "hashless_mainnet_claims": len(main),
            "hashless_mainnet_recorded_claim_wolo": sum(x["recorded_amount_wolo"] for x in main),
            "hashless_mainnet_founder_bonus_recorded_wolo": grouped.get(("mainnet_era", "founders_bonus"), 0),
            "hashless_bet_payout_claims_overlap_winning_wager_amount_wolo": claim_tally["bet_payout"][1],
            "same_market_void_refund_claimed_wolo": claim_tally["bet_refund"][1],
            "same_market_voided_original_stake_wolo": claim_tally["bet_refund"][2],
            "unadjudicated_voided_stake_difference_wolo": claim_tally["bet_refund"][2] - claim_tally["bet_refund"][1],
            "legacy_winner_locally_indexed_stake_count": win_index,
            "legacy_winner_unindexed_stake_count": win_unindexed,
            "legacy_winner_locally_indexed_recorded_payout_wolo": indexed_payout,
            "legacy_winner_unindexed_recorded_payout_wolo": unindexed_payout,
            "under_review_locally_staked_wager_count": active_count,
            "under_review_locally_staked_original_principal_uwolo": str(principal),
        },
        "next_required_evidence": (
            "atomically quiesced HD+DE+Wolo accounting; exact chain-anchored "
            "recipient/amount/event mapping for all claimed-without-hash records; "
            "independently reviewed legacy eligibility and disjoint signer obligations"
        ),
    }


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("claims", "overlap", "winners", "active"):
        p.add_argument("--" + name, required=True, type=Path)
        p.add_argument("--sha256-" + name, required=True)
    args = p.parse_args(argv)
    try:
        hashes = {name: getattr(args, "sha256_" + name) for name in (
            "claims", "overlap", "winners", "active")}
        docs = {name: read(getattr(args, name), hashes[name]) for name in hashes}
        result = verify(docs["claims"], docs["overlap"],
                        docs["winners"], docs["active"], hashes)
    except GapError as exc:
        print(json.dumps({"schema": VERSION, "status": "STOP",
                          "reason": str(exc), "financial_release_authorized": False},
                         sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True, indent=2))
    return 3


if __name__ == "__main__":
    sys.exit(main())

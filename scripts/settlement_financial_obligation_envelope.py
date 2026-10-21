#!/usr/bin/env python3
"""Strict offline cross-evidence envelope for HD pending claims and Wolo settlement observations.

This deliberately cannot prove bank solvency or close Wolo financial release #5.
It reports *non-additive* observation families: HD pending claims, 8092/8093
request/run obligations, and uniquely fingerprinted same-node bank balances.
No path, address, memo, signing key, raw transaction or financial permit is printed.
This tool never performs network I/O, signing, writes, or production inspection.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys

VERSION = "wolo.financial.observed-obligation-envelope.v1"
MAX_BYTES = 2 * 1024 * 1024
MAX_ACCOUNTS = 32
MAX_GROUPS = 64
LIMIT = (1 << 128) - 1
DECIMAL = re.compile(r"(?:0|[1-9][0-9]{0,38})\\Z")
DIGEST = re.compile(r"[0-9a-f]{64}\\Z")
EXPECTED_CHAIN = "wolo-1"
JOURNAL_STATUSES = frozenset({"accepted", "confirmed", "failed", "aggregate_only"})
ROLES = frozenset({"payout", "escrow"})

class EvidenceFailure(ValueError):
    pass

def stop(code: str) -> None:
    raise EvidenceFailure(code)

def unique(pairs):
    result = {}
    for k, v in pairs:
        if k in result:
            stop("DUPLICATE_JSON_KEY")
        result[k] = v
    return result

def read_packet(path: Path) -> tuple[dict, str]:
    """One bounded no-follow open. Reject mutations during an individual read."""
    fd = None
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or not (0 < before.st_size <= MAX_BYTES):
            stop("EVIDENCE_FILE_INVALID")
        raw = bytearray()
        while len(raw) <= MAX_BYTES:
            chunk = os.read(fd, min(65536, MAX_BYTES + 1 - len(raw)))
            if not chunk:
                break
            raw.extend(chunk)
        after = os.fstat(fd)
        stamps = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
        if len(raw) != before.st_size or any(
            getattr(before, k) != getattr(after, k) for k in stamps
        ):
            stop("EVIDENCE_CHANGED_DURING_READ")
        doc = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=unique,
            parse_constant=lambda _: stop("INVALID_JSON_NUMBER"),
        )
        if type(doc) is not dict:
            stop("EVIDENCE_ROOT_INVALID")
        return doc, hashlib.sha256(raw).hexdigest()
    except EvidenceFailure:
        raise
    except (OSError, UnicodeError, ValueError, RecursionError):
        stop("EVIDENCE_FILE_INVALID")
    finally:
        if fd is not None:
            os.close(fd)

def amount(value, *, positive=False) -> int:
    if type(value) is not str or not DECIMAL.fullmatch(value):
        stop("INVALID_CANONICAL_UWOLO")
    n = int(value)
    if n > LIMIT or (positive and n == 0):
        stop("UWOLO_BOUND_VIOLATION")
    return n

def count(value, *, positive=False) -> int:
    if type(value) is not int or value < int(positive) or value > 1000000:
        stop("INVALID_COUNT")
    return value

def is_false(obj: dict, *keys: str) -> None:
    if any(obj.get(k) is not False for k in keys):
        stop("UNSUPPORTED_AUTHORITY_ASSERTION")

def held_bank(doc: dict) -> dict:
    if (doc.get("schema") != "aoe2war.wolo.financial-observation.v1"
        or doc.get("chain_id") != EXPECTED_CHAIN
        or doc.get("global_liability_upper_bound_uwolo", "missing") is not None):
        stop("BANK_OBSERVATION_SCOPE_INVALID")
    is_false(doc, "all_signer_roles_discovered", "complete_liabilities_known",
             "consensus_authenticated", "reserve_solvency_certified",
             "financial_drain_certified", "retry_authorized", "production_mutated")
    lanes = doc.get("bank_role_observations")
    if type(lanes) is not list or not (1 <= len(lanes) <= 8):
        stop("BANK_LANE_COVERAGE_INVALID")
    accounts = {}
    lane_ids = set()
    for lane in lanes:
        if type(lane) is not dict or lane.get("lane") not in {"primary", "founder"}:
            stop("BANK_LANE_INVALID")
        if lane["lane"] in lane_ids or lane.get("healthy") is not True or lane.get("chain_id") != EXPECTED_CHAIN:
            stop("BANK_LANE_DUPLICATED_OR_UNHEALTHY")
        lane_ids.add(lane["lane"])
        roles = lane.get("roles")
        if type(roles) is not list or not roles:
            stop("BANK_ROLES_MISSING")
        local_roles = set()
        for role in roles:
            if type(role) is not dict or role.get("role") not in ROLES:
                stop("BANK_ROLE_INVALID")
            if role["role"] in local_roles:
                stop("BANK_ROLE_DUPLICATED")
            local_roles.add(role["role"])
            key = role.get("account_fingerprint_sha256")
            if type(key) is not str or not DIGEST.fullmatch(key):
                stop("BANK_IDENTITY_INVALID")
            if role.get("sources_agree") is not True:
                stop("BANK_TRUST_DOMAIN_INCONSISTENT")
            balance = amount(role.get("configured_node_bank_uwolo"))
            if amount(role.get("health_reported_uwolo")) != balance:
                stop("BANK_SAME_NODE_BALANCE_CONFLICT")
            earlier = accounts.get(key)
            if earlier is not None and earlier != (role["role"], balance):
                stop("BANK_SHARED_IDENTITY_CONFLICT")
            accounts[key] = (role["role"], balance)
            if len(accounts) > MAX_ACCOUNTS:
                stop("BANK_ACCOUNT_LIMIT")
    if lane_ids != {"primary", "founder"}:
        stop("BANK_LANE_COVERAGE_INVALID")
    totals = {role: sum(balance for k, (r, balance) in accounts.items() if r == role)
              for role in sorted(ROLES)}
    return {
        "unique_same_node_bank_accounts": len(accounts),
        "configured_node_payout_balance_uwolo": str(totals["payout"]),
        "configured_node_escrow_balance_uwolo": str(totals["escrow"]),
        "shared_bank_fingerprints_deduplicated": sum(
            1 for lane in lanes for r in lane["roles"]
        ) - len(accounts),
    }

def held_hd(doc: dict) -> dict:
    if (doc.get("schema") != "aoe2war.wolo.app-liability-observation.v1"
        or doc.get("global_liability_upper_bound_uwolo", "missing") is not None):
        stop("HD_OBSERVATION_SCOPE_INVALID")
    is_false(doc, "complete_liabilities_known", "financial_drain_certified", "production_mutated")
    claim = doc.get("claim_889")
    if (type(claim) is not dict or claim.get("present") is not True
        or claim.get("expected_identity") is not True or claim.get("status") != "pending"
        or amount(claim.get("recorded_principal_uwolo"), positive=True) != 300000000
        or claim.get("has_payout_hash") is not False
        or claim.get("paid_or_unpaid_proven") is not False
        or claim.get("retry_authorized") is not False
        or claim.get("liability_hold_preserved") is not True):
        stop("FOUNDER_889_HOLD_INVALID")
    groups = doc.get("recorded_hd_claim_groups")
    if type(groups) is not list or not (1 <= len(groups) <= MAX_GROUPS):
        stop("HD_CLAIM_GROUPS_INVALID")
    kinds = set()
    total = count_total = attempted = invalid = 0
    for row in groups:
        if type(row) is not dict or row.get("status") != "pending":
            stop("HD_CLAIM_GROUP_INVALID")
        kind = row.get("claim_kind")
        if type(kind) is not str or not re.fullmatch(r"[a-z_]{3,50}", kind) or kind in kinds:
            stop("HD_CLAIM_KIND_DUPLICATED_OR_INVALID")
        kinds.add(kind)
        n = amount(row.get("recorded_requested_uwolo"))
        cnt = int(amount(row.get("record_count")))
        tried = int(amount(row.get("attempted_count")))
        hashed = int(amount(row.get("hash_bearing_count")))
        bad = int(amount(row.get("invalid_amount_count")))
        if cnt == 0 or tried > cnt or hashed > cnt:
            stop("HD_CLAIM_COUNT_INCONSISTENT")
        total += n
        count_total += cnt
        attempted += tried
        invalid += bad
    if invalid or count_total > 1000000 or total > LIMIT or (
        "founders_win" not in kinds or attempted < 1
    ):
        stop("HD_CLAIM_COVERAGE_INCOMPLETE")
    return {
        "recorded_hd_pending_claim_count": count_total,
        "recorded_hd_pending_requested_uwolo": str(total),
        "founder_889_pending_requested_uwolo": "300000000",
        "founder_889_included_in_hd_total_not_additive": True,
        "recorded_hd_attempted_claim_count": attempted,
    }

def held_journal(doc: dict) -> dict:
    if (doc.get("version") != "wolo.settlement.state-evidence.v1"
        or doc.get("status") != "HELD" or doc.get("roots_observed") != 2
        or doc.get("observation_complete") is not True
        or doc.get("observation_atomic") is not False):
        stop("JOURNAL_OBSERVATION_INVALID")
    is_false(doc, "chain_proof_verified", "financial_drained", "release_authorized",
             "retry_authorized", "filesystem_writes", "all_historical_paths_covered")
    info = doc.get("accounting")
    counts = doc.get("counts")
    if type(info) is not dict or type(counts) is not dict:
        stop("JOURNAL_ACCOUNTING_MISSING")
    if (info.get("global_liability_upper_bound_uwolo", "missing") is not None
        or info.get("global_liability_bound") != "UNBOUNDED_NOT_PROVEN"
        or info.get("recorded_status_is_chain_proof") is not False
        or info.get("complete_for_observed_requests_and_runs") is not False):
        stop("JOURNAL_PREMATURE_AUTHORITY")
    groups = info.get("amount_groups")
    if type(groups) is not list or not (1 <= len(groups) <= MAX_GROUPS):
        stop("JOURNAL_AMOUNT_GROUPS_INVALID")
    all_sum = leaves = agg_count = row_count = accepted = 0
    seen = set()
    for row in groups:
        if (type(row) is not dict or type(row.get("lane_index")) is not int
            or row["lane_index"] not in (0, 1)
            or row.get("signer_role") not in ROLES
            or row.get("recorded_status") not in JOURNAL_STATUSES):
            stop("JOURNAL_GROUP_INVALID")
        key = (row["lane_index"], row["signer_role"], row["recorded_status"])
        if key in seen:
            stop("JOURNAL_GROUP_DUPLICATED")
        seen.add(key)
        n = amount(row.get("recorded_requested_principal_uwolo"))
        records = count(row.get("request_count"), positive=True)
        if n == 0:
            stop("JOURNAL_GROUP_ZERO_PRINCIPAL")
        all_sum += n
        if row["recorded_status"] == "aggregate_only":
            agg_count += records
        else:
            leaves += n
            row_count += records
        if row["recorded_status"] == "accepted":
            accepted += records
    if (all_sum > LIMIT
        or str(all_sum) != info.get("deduplicated_observed_requested_principal_uwolo")
        or str(leaves) != info.get("leaf_record_requested_principal_uwolo")
        or row_count != count(counts.get("requests"))
        or accepted != count(counts.get("recorded_status_accepted"))
        or agg_count != count(info.get("aggregate_only_obligation_count"))):
        stop("JOURNAL_AMOUNT_OR_COUNT_MISMATCH")
    return {
        "journal_deduplicated_recorded_requested_uwolo": str(all_sum),
        "journal_leaf_recorded_requested_uwolo": str(leaves),
        "journal_aggregate_only_requested_uwolo": str(all_sum - leaves),
        "journal_recorded_accepted_count": accepted,
        "journal_aggregate_only_count": agg_count,
    }

def envelope(bank, hd, journal, sha_bank, sha_hd, sha_journal) -> dict:
    summary = {}
    summary.update(held_bank(bank))
    summary.update(held_hd(hd))
    summary.update(held_journal(journal))
    for k, v in (("bank", sha_bank), ("hd", sha_hd), ("journal", sha_journal)):
        if type(v) is not str or not DIGEST.fullmatch(v):
            stop("MISSING_EVIDENCE_DIGEST")
    return {
        "schema": VERSION,
        "status": "HOLD",
        "financial_release_authorized": False,
        "bank_consensus_authenticated": False,
        "fresh_same_height_evidence": False,
        "input_observations_atomic_together": False,
        "complete_external_signer_and_product_coverage": False,
        "recorded_claim_journal_overlap_reconciled": False,
        "recorded_journal_statuses_authentic_chain_effects": False,
        "global_liability_upper_bound_uwolo": None,
        "global_bank_solvency_certified": False,
        "accepted_transactions_and_claim_889_retry_authorized": False,
        "production_mutated": False,
        "input_sha256": {"bank": sha_bank, "hd": sha_hd, "journal": sha_journal},
        "NON_ADDITIVE_observations": summary,
        "next_required_evidence": (
            "independent anchored same-height chain bank proof; canonical "
            "claim-to-journal obligation identity; complete live/external liability "
            "and owner coverage; fresh quiesced snapshot and finance approval"
        ),
    }

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bank", required=True, type=Path)
    parser.add_argument("--hd", required=True, type=Path)
    parser.add_argument("--journal", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        bank, b = read_packet(args.bank)
        hd, h = read_packet(args.hd)
        journal, j = read_packet(args.journal)
        result = envelope(bank, hd, journal, b, h, j)
    except EvidenceFailure as exc:
        print(json.dumps({"schema": VERSION, "status": "STOP",
                          "reason": str(exc), "financial_release_authorized": False},
                         sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True, indent=2))
    return 3  # Valid observations are NEVER a deployment permit.

if __name__ == "__main__":
    sys.exit(main())

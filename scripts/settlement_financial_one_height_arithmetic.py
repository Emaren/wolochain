#!/usr/bin/env python3
"""Offline same-height financial arithmetic. NEVER a solvency or release certificate.

Accepts a *candidate* one-height inventory created by a separately controlled
operator. Deduplicates literal economic/account fingerprints, bounds uncertain
side effects conservatively, and refuses missing scope. No key, address,
network, ledger, Wolo node, or production service is accessed. Even a complete
numerical inventory is NOT authenticated custody, consensus, owner coverage or
financial authority: this tool always exits HOLD (3).
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

SCHEMA = "wolo.financial.offline-one-height-arithmetic.v1"
HEX40 = re.compile(r"[0-9a-f]{40}\Z")
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
AMOUNT = re.compile(r"(?:0|[1-9][0-9]{0,38})\Z")
LIMIT = (1 << 128) - 1
MAX_BYTES = 524288
MAX_ROWS = 2000
COVERAGE = frozenset({
    "hd_claims", "de_claims", "primary_settlement_journals",
    "founder_settlement_journals", "war_satchel", "mecha_auto_bets",
    "founder_rewards", "staking", "refunds", "offhost_signers",
})
SOURCES = frozenset({
    "hd", "de", "primary_journal", "founder_journal", "war_satchel",
    "mecha", "founder", "staking", "refund", "external",
})
ACCOUNT_ROLES = frozenset({"payout", "escrow", "treasury"})
TOP = frozenset({
    "schema", "chain_id", "source_commit", "height", "block_sha256",
    "accounts", "obligations", "uncertain_effects", "scope_coverage",
})
ACCOUNT = frozenset({
    "identity_sha256", "role", "balance_uwolo", "source_sha256",
    "height", "block_sha256",
})
OBLIGATION = frozenset({
    "economic_id_sha256", "source", "requested_unpaid_uwolo",
    "source_sha256", "height", "block_sha256",
})
UNCERTAIN = frozenset({
    "physical_effect_id_sha256", "source", "upper_exposure_uwolo",
    "source_sha256", "height", "block_sha256",
})
COVERAGE_ITEM = frozenset({"complete", "source_sha256"})


class InvalidEvidence(ValueError):
    pass


def require(ok: bool, reason: str) -> None:
    if not ok:
        raise InvalidEvidence(reason)


def exact(value, fields, reason):
    require(type(value) is dict and set(value) == fields, reason)
    return value


def digest(value) -> bool:
    return type(value) is str and HEX64.fullmatch(value) is not None and value != "0" * 64


def number(value) -> int:
    require(type(value) is str and AMOUNT.fullmatch(value) is not None,
            "NONCANONICAL_UWOLO")
    n = int(value)
    require(n <= LIMIT, "UWOLO_OVERFLOW")
    return n


def sum_safe(values) -> int:
    n = sum(values)
    require(n <= LIMIT, "UWOLO_OVERFLOW")
    return n


def pairs_no_duplicates(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "DUPLICATE_JSON_KEY")
        result[key] = value
    return result


def read_input(filename: Path):
    fd = None
    try:
        require(filename.is_absolute(), "ABSOLUTE_INPUT_REQUIRED")
        fd = os.open(filename, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        before = os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1
                and 1 <= before.st_size <= MAX_BYTES, "UNSAFE_EVIDENCE_FILE")
        raw = bytearray()
        while len(raw) <= MAX_BYTES:
            piece = os.read(fd, min(65536, MAX_BYTES + 1 - len(raw)))
            if not piece:
                break
            raw.extend(piece)
        after = os.fstat(fd)
        require(len(raw) == before.st_size and all(
            getattr(before, key) == getattr(after, key)
            for key in ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
        ), "EVIDENCE_CHANGED_DURING_READ")
        packet = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs_no_duplicates,
                            parse_constant=lambda _: require(False, "INVALID_NUMBER"))
        return packet, hashlib.sha256(raw).hexdigest()
    except InvalidEvidence:
        raise
    except (OSError, ValueError, UnicodeError, RecursionError) as exc:
        raise InvalidEvidence("EVIDENCE_FILE_INVALID") from exc
    finally:
        if fd is not None:
            os.close(fd)


def arithmetic(packet, input_sha256):
    p = exact(packet, TOP, "INPUT_SCHEMA_INVALID")
    require(p["schema"] == SCHEMA and p["chain_id"] == "wolo-1"
            and type(p["source_commit"]) is str
            and HEX40.fullmatch(p["source_commit"]) is not None,
            "UNBOUND_SOURCE_OR_CHAIN")
    height = p["height"]
    block = p["block_sha256"]
    require(type(height) is int and height > 0 and height < (1 << 63)
            and digest(block) and digest(input_sha256), "INVALID_HEIGHT_OR_BLOCK")
    def same_height(row):
        require(type(row["height"]) is int and row["height"] == height
                and row["block_sha256"] == block and digest(row["source_sha256"]),
                "STALE_OR_MIXED_HEIGHT_EVIDENCE")

    accounts = p["accounts"]
    obligations = p["obligations"]
    effects = p["uncertain_effects"]
    coverage = p["scope_coverage"]
    require(type(accounts) is list and 0 < len(accounts) <= MAX_ROWS
            and type(obligations) is list and len(obligations) <= MAX_ROWS
            and type(effects) is list and len(effects) <= MAX_ROWS,
            "INVENTORY_SIZE_INVALID")
    require(type(coverage) is dict and set(coverage) == COVERAGE,
            "UNSCOPED_FINANCIAL_OWNERS")
    gaps = []
    for name in sorted(COVERAGE):
        row = exact(coverage[name], COVERAGE_ITEM, "COVERAGE_ITEM_INVALID")
        require(type(row["complete"]) is bool
                and (row["source_sha256"] is None or digest(row["source_sha256"])),
                "COVERAGE_PROOF_INVALID")
        if not row["complete"] or not digest(row["source_sha256"]):
            gaps.append(name)

    bank = {}
    for row in accounts:
        r = exact(row, ACCOUNT, "ACCOUNT_SCHEMA_INVALID")
        same_height(r)
        require(digest(r["identity_sha256"]) and r["role"] in ACCOUNT_ROLES,
                "ACCOUNT_IDENTITY_INVALID")
        record = (r["role"], number(r["balance_uwolo"]))
        earlier = bank.setdefault(r["identity_sha256"], record)
        require(earlier == record, "SHARED_ACCOUNT_CONFLICT")
    assets = sum_safe(balance for _, balance in bank.values())

    unique_debt = {}
    origin_by_id = {}
    for row in obligations:
        r = exact(row, OBLIGATION, "OBLIGATION_SCHEMA_INVALID")
        same_height(r)
        require(digest(r["economic_id_sha256"]) and r["source"] in SOURCES,
                "OBLIGATION_IDENTITY_INVALID")
        n = number(r["requested_unpaid_uwolo"])
        require(n > 0, "ZERO_OBLIGATION_INVALID")
        key = r["economic_id_sha256"]
        require(key not in unique_debt or unique_debt[key] == n,
                "SAME_OBLIGATION_CONFLICT")
        unique_debt[key] = n
        origin_by_id.setdefault(key, set()).add(r["source"])
    debt = sum_safe(unique_debt.values())

    unique_effect = {}
    unknown_effects = set()
    for row in effects:
        r = exact(row, UNCERTAIN, "UNCERTAIN_EFFECT_SCHEMA_INVALID")
        same_height(r)
        require(digest(r["physical_effect_id_sha256"]) and r["source"] in SOURCES,
                "UNCERTAIN_EFFECT_ID_INVALID")
        value = r["upper_exposure_uwolo"]
        n = None if value is None else number(value)
        require(n is None or n > 0, "ZERO_UNCERTAIN_EFFECT_INVALID")
        key = r["physical_effect_id_sha256"]
        require(key not in unique_effect or unique_effect[key] == n,
                "SAME_EFFECT_BOUND_CONFLICT")
        unique_effect[key] = n
        if n is None:
            unknown_effects.add(key)
    known_exposure = sum_safe(v for v in unique_effect.values() if v is not None)
    arithmetic_complete = not gaps and not unknown_effects and len(obligations) > 0
    # Effects are conservatively ADDITIVE to obligations even when hashes appear
    # related. An independently verified effect-to-obligation mapping is required
    # before offsetting any payout against an unpaid claim.
    recorded_reserve = (sum_safe((debt, known_exposure)) if arithmetic_complete
                        else None)
    conditional_margin = (assets - recorded_reserve
                          if recorded_reserve is not None else None)
    return {
        "schema": "wolo.financial.offline-one-height-report.v1",
        "status": "HOLD",
        "financial_release_authorized": False,
        "production_mutated": False,
        "chain_id": "wolo-1",
        "source_commit": p["source_commit"],
        "height": height,
        "block_sha256": block,
        "input_sha256": input_sha256,
        "bank_accounts_unique": len(bank),
        "bank_assets_claimed_uwolo": str(assets),
        "obligations_unique": len(unique_debt),
        "obligations_observed_rows": len(obligations),
        "cross_source_obligation_identifiers": sum(
            len(sources) > 1 for sources in origin_by_id.values()),
        "recorded_unpaid_requested_uwolo": str(debt),
        "unresolved_effects_unique": len(unique_effect),
        "unbounded_effects": len(unknown_effects),
        "bounded_effect_additional_reserve_uwolo": str(known_exposure),
        "coverage_gaps": gaps,
        "arithmetic_complete_for_claimed_scope": arithmetic_complete,
        "conditional_recorded_reserve_uwolo": (
            str(recorded_reserve) if recorded_reserve is not None else None),
        "conditional_margin_uwolo": (
            str(conditional_margin) if conditional_margin is not None else None),
        "bank_assets_authenticated_uwolo": None,
        "global_liability_upper_bound_uwolo": None,
        "solvency_verdict": "UNKNOWN_INDEPENDENT_EVIDENCE_REQUIRED",
        "chain_finality_authenticated": False,
        "custody_authorized": False,
        "writer_fence_certified": False,
        "accounting_note": (
            "Claimed fingerprints/digests and completeness flags are not chain,"
            " signer or custodian attestations; ambiguous physical effects"
            " remain additive. Never promote this report to release authority."),
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input", type=Path, required=True)
    args = ap.parse_args(argv)
    try:
        doc, sha = read_input(args.input)
        output = arithmetic(doc, sha)
    except InvalidEvidence as exc:
        print(json.dumps({"status": "STOP", "reason": str(exc),
                          "financial_release_authorized": False}, sort_keys=True))
        return 2
    print(json.dumps(output, sort_keys=True, indent=2))
    return 3


if __name__ == "__main__":
    sys.exit(main())

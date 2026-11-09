#!/usr/bin/env python3
"""C05 independent cross-hash source-collision census; permanently noncrediting.

Complements the original per-hash manifest. A shared economic-source tuple
is NOT a unique authorized operation ID; all overlaps remain under review.
"""
from __future__ import annotations
import argparse
from collections import defaultdict
import datetime as dt
import importlib.util
import hashlib
import json
import os
from pathlib import Path
import stat
import sys

SRC = Path(__file__).with_name("settlement_c05_claim_hash_collision_manifest_hold.py")
SOURCE_SHA = "42c7af6f65e628566ad5031f3c45d3ff0f9000f13d16bb38b7853b3bae7fa9a1"
if hashlib.sha256(SRC.read_bytes()).hexdigest() != SOURCE_SHA:
    raise RuntimeError("HOLD_C05_SOURCE_BINDING_DRIFT")
SPEC = importlib.util.spec_from_file_location("c05_original_private_classifier", SRC)
base = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(base)

SCHEMA = "wolo.c05.cross-hash-economic-source-conflicts.v1"
BASE = Path("/root/aoe2war-c05-crosshash-source-manifest-20261109")


def inspect(payload: dict) -> dict:
    # Perform all original source, ID, denomination and hash validations first.
    original = base.classify(payload)
    by_key = defaultdict(list)
    indexed = defaultdict(list)
    for t in payload["transfers"]:
        indexed[base.normalize_hash(t["tx_hash"])].append(t)
    for c in payload["claims"]:
        by_key[base.economic_key(c)].append(c)

    cross_hash, pending_claimed, rescinded_active, hashless_claimed = [], [], [], []
    for key, cs in by_key.items():
        if len(cs) < 2:
            continue
        hashes = sorted({base.normalize_hash(c["payout_tx_hash"]) for c in cs
                         if base.normalize_hash(c["payout_tx_hash"])})
        statuses = {c["status"] for c in cs}
        ids = sorted(c["id"] for c in cs)
        result = {"claim_ids": ids,
                  "claim_count": len(cs), "economic_source_key": list(key),
                  "hashes": hashes, "claim_groups": sorted(str(c["claim_group_key"]) for c in cs),
                  "claimed_count": sum(c["status"] == "claimed" for c in cs),
                  "pending_count": sum(c["status"] == "pending" for c in cs),
                  "rescinded_count": sum(c["status"] == "rescinded" for c in cs),
                  "economic_source_uniqueness_proven": False,
                  "payment_proven": False,
                  "eligible_to_repay": False,
                  "financial_release_authorized": False}
        if len(hashes) >= 2:
            rows = [c for c in cs if base.normalize_hash(c["payout_tx_hash"])]
            matched = [indexed.get(base.normalize_hash(c["payout_tx_hash"]), [])
                       for c in rows]
            result.update({
                "distinct_hashes": len(hashes),
                "hash_rows": len(rows),
                "indexed_hash_rows": sum(len(x) == 1 for x in matched),
                "exact_amount_indexed_rows": sum(
                    len(m) == 1 and m[0]["denom"] == "uwolo" and
                    m[0]["amount_uwolo"] == c["amount_wolo"] * 1000000
                    for c, m in zip(rows, matched)),
                "indexed_transfers": [
                    {"claim_id": c["id"], "tx_hash": base.normalize_hash(c["payout_tx_hash"]),
                     "index_row_ids": [t["id"] for t in matches],
                     "heights": [t["height"] for t in matches],
                     "amount_uwolo": [t["amount_uwolo"] for t in matches]}
                    for c, matches in zip(rows, matched)],
                "source_contains_distinct_claim_group_keys":
                    len({c["claim_group_key"] for c in cs}) > 1,
                "nominal_wolo": sum(c["amount_wolo"] for c in cs)})
            cross_hash.append(result)
        if "pending" in statuses and "claimed" in statuses:
            pending_claimed.append(result)
        if "rescinded" in statuses and ("claimed" in statuses or "pending" in statuses):
            rescinded_active.append(result)
        if any(c["status"] == "claimed" and
               not base.normalize_hash(c["payout_tx_hash"]) for c in cs) and \
           any(c["status"] == "claimed" and
               base.normalize_hash(c["payout_tx_hash"]) for c in cs):
            hashless_claimed.append(result)

    cross_hash.sort(key=lambda r: r["claim_ids"])
    pending_claimed.sort(key=lambda r: r["claim_ids"])
    rescinded_active.sort(key=lambda r: r["claim_ids"])
    hashless_claimed.sort(key=lambda r: r["claim_ids"])
    count_full_index = sum(r["indexed_hash_rows"] == r["hash_rows"]
                           for r in cross_hash)
    count_full_exact = sum(r["exact_amount_indexed_rows"] == r["hash_rows"]
                           for r in cross_hash)
    summary = {
        "schema": SCHEMA,
        "status": "HOLD_C05_CROSS_HASH_ECONOMIC_SOURCE_ATTRIBUTION",
        "funding_authorized": False, "repayment_authorized": False,
        "admitted_reserves_wolo": 0,
        "source_snapshot_sha256": original["summary"]["source_snapshot_sha256"],
        "all_claim_rows": original["summary"]["claim_rows"],
        "all_indexed_transfer_rows": original["summary"]["indexed_transfer_rows"],
        "distinct_source_economic_keys": len(by_key),
        "cross_hash_keys": len(cross_hash),
        "cross_hash_claim_rows": sum(r["claim_count"] for r in cross_hash),
        "cross_hash_nominal_wolo": sum(r["nominal_wolo"] for r in cross_hash),
        "cross_hash_all_rows_indexed": count_full_index,
        "cross_hash_all_amounts_match": count_full_exact,
        "cross_hash_with_unindexed_rows": len(cross_hash) - count_full_index,
        "cross_hash_claimed_only": sum(r["claimed_count"] == r["claim_count"]
                                      for r in cross_hash),
        "cross_hash_with_multiple_group_keys":
            sum(r["source_contains_distinct_claim_group_keys"] for r in cross_hash),
        "pending_claimed_source_key_overlap": len(pending_claimed),
        "rescinded_active_source_key_overlap": len(rescinded_active),
        "claimed_hash_and_hashless_source_key_overlap": len(hashless_claimed),
        "warnings": [
            "CROSS_HASH_SOURCE_KEY_NOT_UNIQUE_ECONOMIC_OPERATION",
            "INDEXED_MATCH_NOT_AUTHENTICATED_BANK_FINALITY",
            "CROSS_STATUS_KEY_REUSE_NEEDS_MANUAL_REVIEW",
            "NO_DUPLICATE_PAYMENT_INFERENCE_OR_WAIVER",
            "NO_PAYOUT_NO_RESERVE_ADMISSION",
        ],
    }
    return {"summary": summary, "cross_hash": cross_hash,
            "pending_claimed": pending_claimed,
            "rescinded_active": rescinded_active,
            "claimed_hash_and_hashless": hashless_claimed}


def seal(report: dict) -> tuple[str, str]:
    base.require(os.geteuid() == 0, "ROOT_REQUIRED")
    base.require(not BASE.exists() and not BASE.is_symlink(), "OUTPUT_EXISTS")
    BASE.mkdir(mode=0o700)
    st = BASE.lstat()
    base.require(st.st_uid == 0 and stat.S_IMODE(st.st_mode) == 0o700,
                 "OUTPUT_NOT_PRIVATE")
    report["summary"]["observed_at_utc"] = dt.datetime.now(dt.timezone.utc).isoformat()
    raw = base.canonical(report)
    public_summary = dict(report["summary"])
    public_summary["private_manifest_sha256"] = base.digest(raw)
    sraw = base.canonical(public_summary)
    for p, body in [(BASE / "private-economic-crosshash-manifest.json", raw),
                    (BASE / "aggregate-noncrediting-hold.json", sraw)]:
        fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(body)
            f.flush()
            os.fsync(f.fileno())
    return base.digest(raw), base.digest(sraw)


def main() -> int:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--live-readonly", action="store_true")
    g.add_argument("--fixture-json", type=Path)
    args = ap.parse_args()
    payload = base.read_live() if args.live_readonly else json.loads(args.fixture_json.read_text())
    report = inspect(payload)
    if args.live_readonly:
        private_sha, aggregate_sha = seal(report)
        print(json.dumps({"status": report["summary"]["status"],
                          "source_snapshot_sha256": report["summary"]["source_snapshot_sha256"],
                          "private_manifest_sha256": private_sha,
                          "aggregate_sha256": aggregate_sha,
                          "private_evidence_directory": str(BASE),
                          "summary": {k: v for k, v in report["summary"].items()
                                      if k not in ("warnings", "observed_at_utc")},
                          "funding_authorized": False}, sort_keys=True))
    else:
        print(json.dumps(report["summary"], sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (base.Hold, ValueError, OSError, json.JSONDecodeError) as e:
        print("HOLD_C05_CROSSHASH_" + type(e).__name__, file=sys.stderr)
        sys.exit(3)


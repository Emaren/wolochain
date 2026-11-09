#!/usr/bin/env python3
"""C05: classify ALL historic claim↔indexed-transfer collisions without credit authority.

Only a repeatable-read READ ONLY PG snapshot is used. The private report is
root-owned mode 0600 and includes identifiers for individual adjudication.
No payment, reserve admission, role grant, migration, key or network action.
Every output is a financial HOLD, even when amounts match.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys

SCHEMA = "wolo.c05.claim-to-indexed-transfer-ambiguity.v1"
HASH = re.compile(r"^[0-9a-fA-F]{64}$")
BASE = Path("/root/aoe2war-c05-claim-hash-manifest-20261109")
SQL = """
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;
SELECT json_build_object(
  'claims',(SELECT coalesce(json_agg(c ORDER BY c.id),'[]'::json) FROM
    (SELECT id,status,claim_kind,amount_wolo,claimed_by_user_id,
            source_market_id,source_game_stats_id,source_founder_bonus_id,
            claim_group_key,payout_tx_hash
       FROM public.pending_wolo_claims) c),
  'transfers',(SELECT coalesce(json_agg(t ORDER BY t.id),'[]'::json) FROM
    (SELECT id,tx_hash,height,denom,amount_uwolo
       FROM public.wolo_indexed_transfers) t)
)::text;
ROLLBACK;
"""


class Hold(ValueError):
    pass


def require(test: bool, reason: str) -> None:
    if not test:
        raise Hold("HOLD_C05_" + reason)


def canonical(obj: object) -> bytes:
    return (json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n").encode()


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def integer(value: object, positive: bool = False) -> bool:
    return type(value) is int and (value > 0 if positive else value >= 0)


def normalize_hash(value: object) -> str:
    if value is None or value == "":
        return ""
    require(isinstance(value, str) and bool(HASH.fullmatch(value.strip())),
            "MALFORMED_TX_HASH")
    return value.strip().lower()


def check_source_fields(rows: list[dict], fields: set[str], category: str) -> None:
    require(isinstance(rows, list) and len(rows) <= 100_000, category + "_ROW_BOUND")
    for row in rows:
        require(type(row) is dict and set(row) == fields,
                category + "_SCHEMA_DRIFT")


def economic_key(c: dict) -> tuple:
    return tuple(c[k] for k in ("claim_kind", "claimed_by_user_id",
                                "source_market_id", "source_game_stats_id",
                                "source_founder_bonus_id", "amount_wolo"))


def economic_source_present(c: dict) -> bool:
    return any(c[k] is not None for k in ("source_market_id",
                                         "source_game_stats_id",
                                         "source_founder_bonus_id"))


def classify(payload: dict) -> dict:
    require(type(payload) is dict and set(payload) == {"claims", "transfers"},
            "INPUT_SCHEMA_DRIFT")
    claims, transfers = payload["claims"], payload["transfers"]
    check_source_fields(claims,
                        {"id", "status", "claim_kind", "amount_wolo",
                         "claimed_by_user_id", "source_market_id",
                         "source_game_stats_id", "source_founder_bonus_id",
                         "claim_group_key", "payout_tx_hash"}, "CLAIM")
    check_source_fields(transfers,
                        {"id", "tx_hash", "height", "denom", "amount_uwolo"},
                        "TRANSFER")
    require(len(claims) > 0 and len(transfers) > 0, "EMPTY_SOURCE_NOT_ACCEPTED")
    ids, transfer_ids = set(), set()
    by_hash: dict[str, list[dict]] = defaultdict(list)
    index: dict[str, list[dict]] = defaultdict(list)
    statuses: dict[str, dict] = defaultdict(lambda: {"rows": 0, "nominal_wolo": 0,
                                                       "missing_hash_rows": 0})
    missing_source = 0
    rescinded_with_hash = []

    for c in claims:
        require(integer(c["id"], True) and c["id"] not in ids,
                "CLAIM_ID_DUPLICATE_OR_INVALID")
        ids.add(c["id"])
        require(c["status"] in ("claimed", "pending", "rescinded"),
                "UNKNOWN_CLAIM_STATUS")
        require(integer(c["amount_wolo"], True), "INVALID_CLAIM_AMOUNT")
        require(type(c["claim_kind"]) is str and 0 < len(c["claim_kind"]) < 100,
                "INVALID_CLAIM_KIND")
        require(integer(c["claimed_by_user_id"], True) or
                c["claimed_by_user_id"] is None, "INVALID_CLAIM_OWNER")
        for f in ("source_market_id", "source_game_stats_id",
                  "source_founder_bonus_id"):
            require(c[f] is None or integer(c[f], True),
                    "INVALID_CLAIM_PROVENANCE")
        require(c["claim_group_key"] is None or
                (type(c["claim_group_key"]) is str and
                 len(c["claim_group_key"]) <= 512),
                "INVALID_CLAIM_GROUP")
        h = normalize_hash(c["payout_tx_hash"])
        if not economic_source_present(c):
            missing_source += 1
        s = statuses[c["status"]]
        s["rows"] += 1
        s["nominal_wolo"] += c["amount_wolo"]
        if not h:
            s["missing_hash_rows"] += 1
        if c["status"] == "claimed" and h:
            by_hash[h].append(c)
        if c["status"] == "rescinded" and h:
            rescinded_with_hash.append(c["id"])

    for t in transfers:
        require(integer(t["id"], True) and t["id"] not in transfer_ids,
                "TRANSFER_ID_DUPLICATE_OR_INVALID")
        transfer_ids.add(t["id"])
        h = normalize_hash(t["tx_hash"])
        require(bool(h) and integer(t["height"], True),
                "INVALID_INDEXED_TX")
        require(type(t["denom"]) is str and 0 < len(t["denom"]) <= 64,
                "INVALID_TRANSFER_DENOM")
        require(integer(t["amount_uwolo"], True), "INVALID_TRANSFER_AMOUNT")
        index[h].append(t)

    groups = []
    summary = defaultdict(lambda: {"hash_groups": 0, "claim_rows": 0,
                                   "nominal_wolo": 0,
                                   "difference_vs_indexed_wolo": 0,
                                   "distinct_economic_group_count": 0})
    for h, cs in sorted(by_hash.items()):
        matches = index.get(h, [])
        nominal = sum(c["amount_wolo"] for c in cs)
        sources = {economic_key(c) for c in cs}
        distinct = len(sources)
        all_source_present = all(economic_source_present(c) for c in cs)
        amount_equal = len({c["amount_wolo"] for c in cs}) == 1
        duplicate_groups = len({c["claim_group_key"] for c in cs}) != len(cs)
        transfer = matches[0] if len(matches) == 1 else None
        if not matches:
            kind = "INDEX_MISSING_UNKNOWN"
        elif len(matches) != 1:
            kind = "INDEX_DUPLICATE_UNKNOWN"
        elif transfer["denom"] != "uwolo":
            kind = "INDEX_WRONG_DENOM_UNKNOWN"
        elif len(cs) == 1 and transfer["amount_uwolo"] == nominal * 1000000:
            kind = "SINGLE_AMOUNT_MATCH_NOT_PAYMENT_PROOF"
        elif (len(cs) > 1 and amount_equal and
              transfer["amount_uwolo"] == cs[0]["amount_wolo"] * 1000000 and
              distinct == 1 and all_source_present):
            kind = "REUSED_IDENTICAL_ECONOMIC_SOURCE_UNKNOWN"
        elif (len(cs) > 1 and amount_equal and
              transfer["amount_uwolo"] == cs[0]["amount_wolo"] * 1000000 and
              distinct > 1):
            kind = "REUSED_DISTINCT_ECONOMIC_SOURCE_UNKNOWN"
        elif len(cs) > 1 and transfer["amount_uwolo"] == nominal * 1000000:
            kind = "BATCH_AMOUNT_MATCH_UNATTRIBUTED"
        else:
            kind = "INDEX_AMOUNT_MISMATCH_UNKNOWN"
        difference = (max(0, nominal - transfer["amount_uwolo"] // 1000000)
                      if transfer is not None and transfer["denom"] == "uwolo"
                      else 0)
        row = {"tx_hash": h, "classification": kind,
               "claim_ids": sorted(c["id"] for c in cs),
               "claim_count": len(cs), "nominal_wolo": nominal,
               "economic_key_count": distinct,
               "source_complete": all_source_present,
               "repeated_claim_group_key": duplicate_groups,
               "claim_groups": sorted(str(c["claim_group_key"]) for c in cs),
               "economic_sources": [
                   {"id": c["id"], "kind": c["claim_kind"],
                    "owner_id": c["claimed_by_user_id"],
                    "source_market_id": c["source_market_id"],
                    "source_game_stats_id": c["source_game_stats_id"],
                    "source_founder_bonus_id": c["source_founder_bonus_id"],
                    "amount_wolo": c["amount_wolo"]}
                   for c in sorted(cs, key=lambda r: r["id"])],
               "indexed_transfer_count": len(matches),
               "indexed_id": transfer["id"] if transfer else None,
               "indexed_height": transfer["height"] if transfer else None,
               "indexed_denom": transfer["denom"] if transfer else None,
               "indexed_amount_uwolo": transfer["amount_uwolo"] if transfer else None,
               "nominal_difference_vs_indexed_wolo": difference,
               "payment_proven": False,
               "eligible_to_repay": False,
               "solvency_admitted": False}
        groups.append(row)
        out = summary[kind]
        out["hash_groups"] += 1
        out["claim_rows"] += len(cs)
        out["nominal_wolo"] += nominal
        out["difference_vs_indexed_wolo"] += difference
        out["distinct_economic_group_count"] += int(distinct > 1)

    tally = {"schema": SCHEMA, "status": "HOLD_C05_HISTORIC_PAYMENT_ATTRIBUTION",
             "funding_authorized": False, "repayment_authorized": False,
             "admitted_reserves_wolo": 0,
             "claim_rows": len(claims), "indexed_transfer_rows": len(transfers),
             "indexed_unique_hashes": len(index), "claimed_hash_groups": len(groups),
             "statuses": dict(sorted(statuses.items())),
             "claims_without_economic_source": missing_source,
             "rescinded_with_hash_ids": sorted(rescinded_with_hash),
             "classes": dict(sorted(summary.items())),
             "source_snapshot_sha256": digest(canonical(payload)),
             "warnings": [
                 "INDEX_MATCH_NOT_SIGNED_CHAIN_PAYMENT_PROOF",
                 "INDEX_MISSING_NOT_PROOF_OF_NONPAYMENT",
                 "SAME_ECONOMIC_SOURCE_NOT_AUTOMATIC_DUPLICATE_WRITE",
                 "DISTINCT_SOURCE_HASH_REUSE_REQUIRES_CLAIM_BY_CLAIM_ADJUDICATION",
                 "REPAYMENT_AND_RESERVE_ADMISSION_ALWAYS_HELD",
             ]}
    return {"summary": tally, "groups": groups}


def read_live() -> dict:
    require(os.geteuid() == 0, "ROOT_REQUIRED")
    env = dict(os.environ)
    env["PGOPTIONS"] = "-c default_transaction_read_only=on -c statement_timeout=30000 -c lock_timeout=1500"
    p = subprocess.run(
        ["sudo", "-u", "postgres", "psql", "-X", "-q", "-A", "-t",
         "-v", "ON_ERROR_STOP=1", "-d", "aoe2hd_db"],
        input=SQL, text=True, capture_output=True, timeout=45, env=env)
    require(p.returncode == 0, "SQL_READ_FAILED")
    require(len(p.stdout) < 24_000_000, "SQL_TOO_LARGE")
    data = json.loads(p.stdout)
    return data


def seal(result: dict) -> tuple[str, str]:
    require(os.geteuid() == 0, "ROOT_SEAL_REQUIRED")
    require(not BASE.exists() and not BASE.is_symlink(), "OUTPUT_EXISTS")
    BASE.mkdir(mode=0o700)
    st = BASE.lstat()
    require(st.st_uid == 0 and stat.S_IMODE(st.st_mode) == 0o700,
            "OUTPUT_DIR_NOT_PRIVATE")
    manifest = BASE / "private-claim-attribution-manifest.json"
    summary = BASE / "aggregate-noncrediting-hold.json"
    result["summary"]["observed_at_utc"] = dt.datetime.now(dt.timezone.utc).isoformat()
    raw = canonical(result)
    minimal = dict(result["summary"])
    minimal["private_manifest_sha256"] = digest(raw)
    for path, body in ((manifest, raw), (summary, canonical(minimal))):
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(body)
            f.flush()
            os.fsync(f.fileno())
    return digest(raw), digest(canonical(minimal))


def main() -> int:
    ap = argparse.ArgumentParser()
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--live-readonly", action="store_true")
    mode.add_argument("--fixture-json", type=Path)
    args = ap.parse_args()
    payload = read_live() if args.live_readonly else json.loads(args.fixture_json.read_text())
    result = classify(payload)
    if args.live_readonly:
        private_sha, summary_sha = seal(result)
        print(json.dumps({
            "status": result["summary"]["status"], "source_snapshot_sha256": result["summary"]["source_snapshot_sha256"],
            "private_manifest_sha256": private_sha,
            "aggregate_sha256": summary_sha,
            "private_evidence_directory": str(BASE),
            "classes": result["summary"]["classes"],
            "claim_rows": result["summary"]["claim_rows"],
            "funding_authorized": False}, sort_keys=True))
    else:
        print(json.dumps(result["summary"], sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (Hold, ValueError, OSError, json.JSONDecodeError,
            subprocess.TimeoutExpired) as e:
        print("HOLD_C05_PRIVATE_MANIFEST_" + type(e).__name__, file=sys.stderr)
        sys.exit(3)


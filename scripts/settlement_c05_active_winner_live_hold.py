#!/usr/bin/env python3
"""C05 HOLD: compare historically pinned 41 active stakes vs fresh HD and 25 winners.

No network client, database driver, signer, key access, payments or database writes.
--emit-hd-sql prints fixed READ ONLY PostgreSQL SQL. Operator separately captures
one 0600 private JSON row and SHA-pins it; --classify ONLY reads private files.
A fully matching source ends 3/HOLD. Any unsupported claim or drift ends 2/STOP.
This is not chain finality, independently authenticated bank state or solvency.
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

VERSION = "wolo.c05.active-winner-live-source-hold.v1"
ACTIVE_SCHEMA = "wolo.c05.active-stake-escrow-match.v1"
WINNERS_SCHEMA = "wolo.c05.legacy-winner-stake-verifiability.v1"
LIVE_SCHEMA = "wolo.c05.live-hd-active-wager-census.v1"
EXPECTED_ACTIVE_SHA256 = "64e8dcf3420e12f5321a4f9f9d16f6403c42575237aa04fd1cf733f75dcb5533"
EXPECTED_WINNERS_SHA256 = "e497627cb285653c0aae2ee572ac8cfe200ca0dcab7a75e14db5de79fc6aa0ad"
EXPECTED_ACTIVE_TUPLE_SHA256 = "fb1a6afb429f0d501377f07fe2f70434196d23668292e53de47300cd98e9dbbc"
ACTIVE_COUNT = 41
WINNER_COUNT = 25
ACTIVE_ORIGINAL_WOLO = 53728
UWOLO_PER_WOLO = 1_000_000
MAX_BYTES = 131072
SHA = re.compile(r"[a-f0-9]{64}\Z")

class Hold(ValueError):
    pass

def require(ok, reason):
    if not ok:
        raise Hold(reason)

def distinct_pairs(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "C05_DUPLICATE_JSON_KEY")
        result[key] = value
    return result

def source_digest(rows):
    return hashlib.sha256(json.dumps(
        rows, separators=(",", ":"), ensure_ascii=True
    ).encode()).hexdigest()

def read_private(path: Path, expected_sha: str):
    require(type(expected_sha) is str and SHA.fullmatch(expected_sha) is not None,
            "C05_INVALID_SOURCE_DIGEST")
    require(path.is_absolute() and ".." not in path.parts and not path.is_symlink(),
            "C05_UNSAFE_SOURCE_PATH")
    try:
        parent = path.parent.stat()
        require(stat.S_ISDIR(parent.st_mode) and not path.parent.is_symlink()
                and parent.st_uid == os.geteuid()
                and stat.S_IMODE(parent.st_mode) == 0o700,
                "C05_UNSAFE_SOURCE_DIRECTORY")
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            before = os.fstat(fd)
            require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1
                    and before.st_uid == os.geteuid()
                    and stat.S_IMODE(before.st_mode) == 0o600
                    and 0 < before.st_size <= MAX_BYTES,
                    "C05_UNSAFE_SOURCE_FILE")
            blob = os.read(fd, MAX_BYTES + 1)
            after = os.fstat(fd)
            require(len(blob) == before.st_size
                    and all(getattr(before, attr) == getattr(after, attr)
                            for attr in ("st_dev", "st_ino", "st_mode", "st_uid",
                                         "st_mtime_ns", "st_ctime_ns", "st_size")),
                    "C05_SOURCE_CHANGED_DURING_READ")
        finally:
            os.close(fd)
    except OSError:
        raise Hold("C05_SOURCE_UNAVAILABLE") from None
    require(hashlib.sha256(blob).hexdigest() == expected_sha,
            "C05_SOURCE_SHA_DRIFT")
    try:
        result = json.loads(blob.decode("utf-8"), object_pairs_hook=distinct_pairs,
            parse_constant=lambda _: require(False, "C05_NONFINITE_JSON"),
            parse_float=lambda _: require(False, "C05_FLOAT_NOT_ALLOWED"))
    except Hold:
        raise
    except (UnicodeError, ValueError, RecursionError):
        raise Hold("C05_SOURCE_JSON_MALFORMED") from None
    require(type(result) is dict, "C05_SOURCE_OBJECT_REQUIRED")
    return result

def fixed_hd_sql():
    return """BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;
SET LOCAL statement_timeout='8s';
SELECT pg_catalog.json_build_object(
 'schema','wolo.c05.live-hd-active-wager-census.v1',
 'database',current_database(),
 'snapshot_utc',to_char(transaction_timestamp() AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS"Z"'),
 'total',(SELECT count(*) FROM public.bet_wagers WHERE status='active'),
 'rows',coalesce((SELECT pg_catalog.json_agg(pg_catalog.json_build_object(
  'id',id,'market_id',market_id,'wolo',amount_wolo,'stake_hash',stake_tx_hash
 ) ORDER BY id) FROM public.bet_wagers WHERE status='active'),'[]'::json),
 'independent_chain_finality',false,
 'financial_release_authorized',false
)::text WHERE current_database()='aoe2hd_db';
COMMIT;
"""

def strict_positive(n):
    require(type(n) is int and n > 0 and n < 10**15,
            "C05_POSITIVE_INTEGER_REQUIRED")
    return n

def historical_active(active):
    require(active.get("schema") == ACTIVE_SCHEMA and
            active.get("global_solvency_certified") is False and
            active.get("financial_release_authorized") is False and
            active.get("independent_canonical_consensus_trust_anchor_proven") is False and
            active.get("wager_count") == ACTIVE_COUNT,
            "C05_HISTORICAL_ACTIVE_AUTHORITY_OR_SCOPE_DRIFT")
    entries = active.get("entries")
    require(type(entries) is list and len(entries) == ACTIVE_COUNT,
            "C05_HISTORICAL_ACTIVE_COUNT_DRIFT")
    result = []
    ids, hashes = set(), set()
    for item in entries:
        require(type(item) is dict, "C05_HISTORICAL_ACTIVE_SHAPE")
        wid = strict_positive(item.get("wager_id"))
        market = strict_positive(item.get("market_id"))
        tx = item.get("tx_hash")
        amount = item.get("principal_uwolo")
        require(type(tx) is str and SHA.fullmatch(tx.lower()) is not None
                and type(amount) is str and re.fullmatch(r"[1-9][0-9]*", amount),
                "C05_HISTORICAL_STAKE_IDENTITY_INVALID")
        require(wid not in ids and tx.lower() not in hashes,
                "C05_HISTORICAL_ACTIVE_DUPLICATE")
        ids.add(wid); hashes.add(tx.lower())
        result.append([wid, market, int(amount), tx.lower()])
    result.sort()
    require(sum(row[2] for row in result) ==
            int(active.get("original_principal_uwolo", "0")),
            "C05_HISTORICAL_ORIGINAL_PRINCIPAL_DRIFT")
    require(source_digest(result) == EXPECTED_ACTIVE_TUPLE_SHA256,
            "C05_HISTORICAL_ACTIVE_SOURCE_IDENTITY_DRIFT")
    return result, ids, hashes

def historical_winners(winners):
    require(winners.get("schema") == WINNERS_SCHEMA
            and winners.get("financial_release_authorized") is False
            and winners.get("disjoint_global_liability_bound_proven") is False,
            "C05_HISTORICAL_WINNER_AUTHORITY_DRIFT")
    rows = winners.get("records")
    require(type(rows) is list and len(rows) == WINNER_COUNT,
            "C05_HISTORICAL_WINNER_COUNT_DRIFT")
    ids, txs = set(), set()
    for row in rows:
        require(type(row) is dict, "C05_HISTORICAL_WINNER_SHAPE")
        wid = strict_positive(row.get("wager_id"))
        tx = row.get("stake_tx_hash")
        require(type(tx) is str and SHA.fullmatch(tx.lower()) is not None,
                "C05_HISTORICAL_WINNER_TX_INVALID")
        require(wid not in ids and tx.lower() not in txs,
                "C05_HISTORICAL_WINNER_DUPLICATE")
        ids.add(wid); txs.add(tx.lower())
    return ids, txs

def live_active(live, now=None):
    require(type(live) is dict and set(live) == {
        "schema", "database", "snapshot_utc", "total", "rows",
        "independent_chain_finality", "financial_release_authorized"
    }, "C05_LIVE_SOURCE_SHAPE")
    require(live["schema"] == LIVE_SCHEMA and live["database"] == "aoe2hd_db"
            and live["independent_chain_finality"] is False
            and live["financial_release_authorized"] is False,
            "C05_LIVE_UNSUPPORTED_AUTHORITY")
    require(type(live["snapshot_utc"]) is str
            and re.fullmatch(r"20[0-9]{2}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z",
                             live["snapshot_utc"]) is not None,
            "C05_LIVE_TIMESTAMP_FORMAT")
    try:
        stamp = datetime.strptime(live["snapshot_utc"], "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc)
    except ValueError:
        raise Hold("C05_LIVE_INVALID_TIMESTAMP") from None
    delta = ((now or datetime.now(timezone.utc)) - stamp).total_seconds()
    require(-30 <= delta <= 900, "C05_LIVE_OBSERVATION_EXPIRED_OR_FUTURE")
    rows = live["rows"]
    require(type(live["total"]) is int and live["total"] == ACTIVE_COUNT
            and type(rows) is list and len(rows) == ACTIVE_COUNT,
            "C05_LIVE_ACTIVE_COUNT_DRIFT")
    result, ids, hashes = [], set(), set()
    last = 0
    for row in rows:
        require(type(row) is dict and set(row) == {
            "id", "market_id", "wolo", "stake_hash"
        }, "C05_LIVE_ROW_SHAPE")
        wid = strict_positive(row["id"])
        market = strict_positive(row["market_id"])
        wolo = strict_positive(row["wolo"])
        tx = row["stake_hash"]
        require(type(tx) is str and SHA.fullmatch(tx.lower()) is not None,
                "C05_LIVE_STAKE_HASH_INVALID")
        require(wid > last and wid not in ids and tx.lower() not in hashes,
                "C05_LIVE_DUPLICATE_OR_UNORDERED")
        last = wid
        ids.add(wid);hashes.add(tx.lower())
        result.append([wid,market,wolo*UWOLO_PER_WOLO,tx.lower()])
    require(sum(x[2] for x in result) == ACTIVE_ORIGINAL_WOLO*UWOLO_PER_WOLO,
            "C05_LIVE_PRINCIPAL_DRIFT")
    return result, ids, hashes, stamp

def classify(active, winners, live, now=None):
    baseline, old_ids, old_hashes = historical_active(active)
    winner_ids, winner_hashes = historical_winners(winners)
    fresh, fresh_ids, fresh_hashes, stamp = live_active(live, now=now)
    require(old_ids == fresh_ids and old_hashes == fresh_hashes
            and baseline == fresh,
            "C05_ACTIVE_INDIVIDUAL_SOURCE_DRIFT")
    require(not (fresh_ids & winner_ids) and not (fresh_hashes & winner_hashes),
            "C05_ACTIVE_VS_WINNER_SOURCE_COLLISION")
    return {
        "schema":VERSION,
        "status":"HOLD_C05_ACTIVE_SOURCE_IDENTITIES_MATCH_NO_SOLVENCY",
        "live_snapshot_utc":stamp.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "active_wagers":ACTIVE_COUNT,
        "original_nominal_stake_wolo":ACTIVE_ORIGINAL_WOLO,
        "historical_winner_rows":WINNER_COUNT,
        "active_vs_winner_wager_id_collisions":0,
        "active_vs_winner_stake_hash_collisions":0,
        "historical_and_live_active_identity_sha256":source_digest(fresh),
        "all_financial_obligations_complete":False,
        "snapshots_atomic_hd_de_chain":False,
        "independent_bank_proof_authenticated":False,
        "claim_payment_finality_authenticated":False,
        "full_solvency_certified":False,
        "payout_retry_authorized":False,
        "financial_release_authorized":False,
        "production_mutated":False,
    }

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    mode=p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--emit-hd-sql",action="store_true")
    mode.add_argument("--classify",action="store_true")
    p.add_argument("--active",type=Path)
    p.add_argument("--winners",type=Path)
    p.add_argument("--live",type=Path)
    p.add_argument("--live-sha256")
    a=p.parse_args(argv)
    if a.emit_hd_sql:
        print(fixed_hd_sql(),end="")
        return 3
    try:
        require(all((a.active,a.winners,a.live,a.live_sha256)),
                "C05_HISTORICAL_AND_LIVE_FILES_REQUIRED")
        result=classify(
            read_private(a.active,EXPECTED_ACTIVE_SHA256),
            read_private(a.winners,EXPECTED_WINNERS_SHA256),
            read_private(a.live,a.live_sha256))
    except Hold as exc:
        print(json.dumps({"schema":VERSION,"status":"STOP",
                          "reason":str(exc),"financial_release_authorized":False},
                         sort_keys=True))
        return 2
    print(json.dumps(result,sort_keys=True))
    return 3

if __name__=="__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""C04 HOLD-only same-window HD+DE live claim drift observer.

Emits strictly SELECT-only PostgreSQL transactions (no DB credentials or
connections from this program). Consumes two independently supplied, private
0600 JSON observations from HD and DE. Detects real source changes and
quarantines all 69 claimed-but-hashless cases without inferring paid/unpaid.

The two PostgreSQL snapshots cannot be made atomic by this tool; it is NOT a
Comet consensus receipt, complete C05 solvency proof or C06/C07 recovery.
Even a matching report returns 3/HOLD. Errors and drift return 2/STOP.
"""
from __future__ import annotations

import argparse
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys

SCHEMA="wolo.c04.dual-db-claim-census-observation.v1"
REPORT="wolo.c04.dual-db-finance-drift-hold.v1"
MAX_BYTES=32768
DIGEST=re.compile(r"[a-f0-9]{64}\Z")
HD="aoe2hd_db"
DE="aoe2de_db"
CRITICAL_CLAIMS={
  889:("pending","founders_win",300,False,True),
  8217:("claimed","bet_refund",800,False,True),
  8218:("pending","founders_bonus",4000,False,False),
  8219:("pending","founders_bonus",4000,False,False),
  8226:("pending","founders_bonus",8,False,False),
  8227:("pending","founders_bonus",8,False,False),
  9645:("pending","bet_refund",100,False,True),
}
CRITICAL_WAGERS={
  394:("void",5000,True,False),
  396:("void",800,True,False),
}
HD_COUNTS={
 "claimed_hashless":69,"claimed_hashless_wolo":120443,
 "pending":948,"pending_wolo":993289,
 "claimed_with_hash":1243,
}
HD_GROUPS={
 "bet_payout":(15,109504),
 "bet_refund":(3,6801),
 "founders_bonus":(51,4138),
}
DE_COUNTS={"claimed_hashless":0,"claimed_hashless_wolo":0,
           "pending":0,"pending_wolo":0,"claimed_with_hash":0}

class Hold(ValueError):
    pass

def require(condition,reason):
    if not condition:raise Hold(reason)

def unique(pairs):
    result={}
    for k,v in pairs:
        require(k not in result,"C04_DUPLICATE_JSON_KEY")
        result[k]=v
    return result

def parse_time(text):
    require(type(text) is str and
            re.fullmatch(r"20[0-9]{2}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z",text),
            "C04_CAPTURE_TIMESTAMP_INVALID")
    try:return datetime.strptime(text,"%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:raise Hold("C04_CAPTURE_TIMESTAMP_INVALID") from None

def observe_sql(db):
    require(db in (HD,DE),"C04_UNKNOWN_DB_SCOPE")
    # Built exclusively from controlled literals; never interpolates an
    # arbitrary table identifier or receives SQL via input arguments.
    return """
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;
SET LOCAL statement_timeout='8s';
SELECT pg_catalog.json_build_object(
'schema','wolo.c04.dual-db-claim-census-observation.v1',
'database',current_database(),
'captured_utc',to_char(transaction_timestamp() AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS"Z"'),
'counts',(SELECT pg_catalog.json_build_object(
  'claimed_hashless',count(*) FILTER (WHERE status='claimed'
    AND NULLIF(BTRIM(COALESCE(payout_tx_hash,'')),'') IS NULL),
  'claimed_hashless_wolo',coalesce(sum(amount_wolo) FILTER (WHERE status='claimed'
    AND NULLIF(BTRIM(COALESCE(payout_tx_hash,'')),'') IS NULL),0),
  'pending',count(*) FILTER (WHERE status='pending'),
  'pending_wolo',coalesce(sum(amount_wolo) FILTER (WHERE status='pending'),0),
  'claimed_with_hash',count(*) FILTER (WHERE status='claimed'
    AND NULLIF(BTRIM(COALESCE(payout_tx_hash,'')),'') IS NOT NULL))
 FROM public.pending_wolo_claims),
'groups',coalesce((SELECT pg_catalog.json_agg(pg_catalog.json_build_object(
 'kind',claim_kind,'count',row_count,'wolo',total_wolo) ORDER BY claim_kind)
 FROM (SELECT claim_kind,count(*) row_count,coalesce(sum(amount_wolo),0) total_wolo
 FROM public.pending_wolo_claims WHERE status='claimed'
 AND NULLIF(BTRIM(COALESCE(payout_tx_hash,'')),'') IS NULL
 GROUP BY claim_kind) z),'[]'::json),
'critical_claims',coalesce((SELECT pg_catalog.json_agg(pg_catalog.json_build_object(
 'id',id,'status',status,'kind',claim_kind,'wolo',amount_wolo,
 'hash_present',NULLIF(BTRIM(COALESCE(payout_tx_hash,'')),'') IS NOT NULL,
 'attempted',payout_attempted_at IS NOT NULL) ORDER BY id)
 FROM public.pending_wolo_claims
 WHERE id IN (889,8217,8218,8219,8226,8227,9645)),'[]'::json),
'critical_wagers',coalesce((SELECT pg_catalog.json_agg(pg_catalog.json_build_object(
 'id',id,'status',status,'wolo',amount_wolo,
 'stake_hash_present',NULLIF(BTRIM(COALESCE(stake_tx_hash,'')),'') IS NOT NULL,
 'payout_hash_present',NULLIF(BTRIM(COALESCE(payout_tx_hash,'')),'') IS NOT NULL)
 ORDER BY id) FROM public.bet_wagers WHERE id IN (394,396)),'[]'::json),
'indexed',(SELECT pg_catalog.json_build_object(
 'count',count(*),'height_max',coalesce(max(height),0))
 FROM public.wolo_indexed_transfers),
'financial_authorized',false,'chain_finality_proven',false,
'cross_db_snapshot_atomic',false)
WHERE current_database() = '""" + db + """';
COMMIT;
""".strip()+"\n"

def read_private(path,expected):
    require(type(expected) is str and DIGEST.fullmatch(expected),
            "C04_EXPECTED_DIGEST_INVALID")
    require(path.is_absolute() and ".." not in path.parts and
            not path.is_symlink(),"C04_PRIVATE_PATH_INVALID")
    require(path.parent.is_dir() and not path.parent.is_symlink()
            and path.parent.stat().st_uid==os.geteuid()
            and stat.S_IMODE(path.parent.stat().st_mode)==0o700,
            "C04_PRIVATE_PARENT_UNSAFE")
    try:
        fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|os.O_CLOEXEC)
        try:
            before=os.fstat(fd)
            require(stat.S_ISREG(before.st_mode) and before.st_nlink==1
                    and before.st_uid==os.geteuid()
                    and stat.S_IMODE(before.st_mode)==0o600
                    and 0<before.st_size<=MAX_BYTES,
                    "C04_PRIVATE_EVIDENCE_UNSAFE")
            body=os.read(fd,MAX_BYTES+1)
            after=os.fstat(fd)
            require(len(body)==before.st_size
                    and all(getattr(before,k)==getattr(after,k)
                        for k in ("st_dev","st_ino","st_uid","st_mode",
                                  "st_size","st_ctime_ns","st_mtime_ns")),
                    "C04_EVIDENCE_CHANGED_DURING_READ")
        finally:os.close(fd)
    except OSError:raise Hold("C04_PRIVATE_EVIDENCE_UNAVAILABLE") from None
    require(hashlib.sha256(body).hexdigest()==expected,
            "C04_EVIDENCE_SHA_DRIFT")
    try:
        data=json.loads(body.decode("utf-8"),
                        object_pairs_hook=unique,
                        parse_constant=lambda _:require(False,"C04_NONFINITE_JSON"),
                        parse_float=lambda _:require(False,"C04_NONCANONICAL_FLOAT"))
    except Hold:
        raise
    except (ValueError,UnicodeError,RecursionError):
        raise Hold("C04_JSON_MALFORMED") from None
    return data

def validate(packet,db):
    require(type(packet) is dict and set(packet)=={
            "schema","database","captured_utc","counts","groups",
            "critical_claims","critical_wagers","indexed",
            "financial_authorized","chain_finality_proven","cross_db_snapshot_atomic"},
            "C04_SCHEMA_DRIFT")
    require(packet["schema"]==SCHEMA and packet["database"]==db
            and packet["financial_authorized"] is False
            and packet["chain_finality_proven"] is False
            and packet["cross_db_snapshot_atomic"] is False,
            "C04_UNEARNED_FINANCIAL_AUTHORITY")
    moment=parse_time(packet["captured_utc"])
    counts=packet["counts"]
    require(type(counts) is dict and set(counts)==set(HD_COUNTS)
            and all(type(v) is int and v>=0 for v in counts.values()),
            "C04_COUNTS_SHAPE_DRIFT")
    require(counts==(HD_COUNTS if db==HD else DE_COUNTS),
            "C04_LIVE_CLAIM_CENSUS_CHANGED")
    groups=packet["groups"]
    require(type(groups) is list and len(groups)==(3 if db==HD else 0),
            "C04_CLAIM_GROUP_COUNT_DRIFT")
    actual={}
    for group in groups:
        require(type(group) is dict and set(group)=={"kind","count","wolo"}
                and type(group["kind"]) is str and group["kind"] not in actual
                and type(group["count"]) is int and type(group["wolo"]) is int,
                "C04_GROUP_IDENTITY_INVALID")
        actual[group["kind"]]=(group["count"],group["wolo"])
    require(actual==(HD_GROUPS if db==HD else {}),"C04_GROUP_AMOUNT_DRIFT")
    claims=packet["critical_claims"]
    wagers=packet["critical_wagers"]
    require(type(claims) is list and type(wagers) is list,
            "C04_CRITICAL_EVIDENCE_MISSING")
    actual_claims={}
    for row in claims:
        require(type(row) is dict and set(row)=={
                "id","status","kind","wolo","hash_present","attempted"}
                and type(row["id"]) is int and row["id"] not in actual_claims
                and type(row["hash_present"]) is bool
                and type(row["attempted"]) is bool,
                "C04_CLAIM_CASE_SHAPE_INVALID")
        actual_claims[row["id"]]=(row["status"],row["kind"],row["wolo"],
                                  row["hash_present"],row["attempted"])
    actual_wagers={}
    for row in wagers:
        require(type(row) is dict and set(row)=={
                "id","status","wolo","stake_hash_present","payout_hash_present"}
                and type(row["id"]) is int and row["id"] not in actual_wagers
                and type(row["stake_hash_present"]) is bool
                and type(row["payout_hash_present"]) is bool,
                "C04_WAGER_CASE_SHAPE_INVALID")
        actual_wagers[row["id"]]=(row["status"],row["wolo"],
                                  row["stake_hash_present"],row["payout_hash_present"])
    require(actual_claims==(CRITICAL_CLAIMS if db==HD else {})
            and actual_wagers==(CRITICAL_WAGERS if db==HD else {}),
            "C04_HISTORICAL_UNKNOWN_CASE_DRIFT")
    idx=packet["indexed"]
    require(type(idx) is dict and set(idx)=={"count","height_max"}
            and all(type(idx[x]) is int and idx[x]>=0
                    for x in ("count","height_max")),
            "C04_LOCAL_INDEX_SHAPE_INVALID")
    if db==HD:
        require(idx["count"]>=4300 and idx["height_max"]>=2813553,
                "C04_LOCAL_INDEX_OBSERVED_REGRESSION")
    else:
        require(idx=={"count":0,"height_max":0},
                "C04_DE_INDEX_SCOPE_CHANGED")
    return moment

def compare(hd,de,now=None):
    t1=validate(hd,HD);t2=validate(de,DE)
    now=now or datetime.now(timezone.utc)
    require(-30<=(now-t1).total_seconds()<=900 and
            -30<=(now-t2).total_seconds()<=900,
            "C04_SOURCE_CAPTURE_EXPIRED_OR_FUTURE")
    require(abs((t1-t2).total_seconds())<=120,
            "C04_CROSS_DB_CAPTURE_WINDOW_SPLIT")
    return {
        "schema":REPORT,
        "status":"HOLD_C04_UNRESOLVED_PAYMENT_FINALITY",
        "hd_claimed_hashless":69,
        "hd_claimed_hashless_nominal_wolo":120443,
        "de_claimed_hashless":0,
        "hd_pending_claims":948,
        "hd_pending_nominal_wolo":993289,
        "historical_cases_preserved":True,
        "cross_db_atomic":False,
        "independent_comet_finality":False,
        "independent_reserve_coverage":False,
        "hashless_nominal_additive_to_pending_liability":False,
        "retry_authorized":False,"financial_release_authorized":False,
        "production_mutated":False,
    }

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    m=p.add_mutually_exclusive_group(required=True)
    m.add_argument("--emit-hd-sql",action="store_true")
    m.add_argument("--emit-de-sql",action="store_true")
    m.add_argument("--classify",action="store_true")
    p.add_argument("--hd",type=Path)
    p.add_argument("--de",type=Path)
    p.add_argument("--hd-sha256")
    p.add_argument("--de-sha256")
    a=p.parse_args(argv)
    if a.emit_hd_sql:
        print(observe_sql(HD),end="")
        return 3
    if a.emit_de_sql:
        print(observe_sql(DE),end="")
        return 3
    try:
        require(all((a.hd,a.de,a.hd_sha256,a.de_sha256)),
                "C04_DUAL_DB_FILES_AND_PINNED_SHA_REQUIRED")
        report=compare(read_private(a.hd,a.hd_sha256),
                       read_private(a.de,a.de_sha256))
    except (Hold,OSError,ValueError,TypeError) as exc:
        print(json.dumps({"schema":REPORT,"status":"STOP",
                          "reason":str(exc) if type(exc) is Hold else type(exc).__name__,
                          "financial_release_authorized":False},sort_keys=True))
        return 2
    print(json.dumps(report,sort_keys=True))
    return 3

if __name__=="__main__":
    sys.exit(main())

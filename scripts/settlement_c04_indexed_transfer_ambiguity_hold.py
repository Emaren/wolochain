#!/usr/bin/env python3
"""Read-only C04 candidate matches. NEVER declares a customer payment final.

Matches are local indexed-transfer candidates by exact recipient and uwolo
amount. Neither a local SQL index nor a unique match authenticates consensus,
payer identity, transfer purpose or claim discharge. Only HOLD or STOP.
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

SCHEMA = "wolo.c04.indexed-transfer-candidate-ambiguity-hold.v1"
SOURCE_SCHEMA = "wolo.c04.indexed-transfer-candidate-readonly-census.v1"
SHA = re.compile(r"[0-9a-f]{64}\Z")
MAX = 100_000
KIND = {
    "founders_bonus": (51, 4138),
    "bet_payout": (15, 109504),
    "bet_refund": (3, 6801),
}
SQL = """BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;
SET LOCAL statement_timeout='10000ms';
WITH claims AS (
 SELECT c.id,c.claim_kind,c.amount_wolo::bigint AS nominal,
        c.payout_attempted_at,lower(btrim(u.wallet_address)) AS wallet
 FROM public.pending_wolo_claims c
 LEFT JOIN public.users u ON u.id=c.claimed_by_user_id
 WHERE c.status='claimed'
   AND NULLIF(btrim(coalesce(c.payout_tx_hash,'')),'') IS NULL
), match_rows AS (
 SELECT c.id,c.claim_kind,c.nominal,c.wallet,c.payout_attempted_at,
        count(t.id)::int AS any_hits,
        count(t.id) FILTER (WHERE c.payout_attempted_at IS NOT NULL
            AND t.timestamp BETWEEN c.payout_attempted_at-interval '1 day'
                              AND c.payout_attempted_at+interval '7 days')::int AS near_hits,
        count(t.id) FILTER (WHERE c.payout_attempted_at IS NOT NULL
            AND t.timestamp BETWEEN c.payout_attempted_at-interval '1 day'
                              AND c.payout_attempted_at+interval '30 days')::int AS thirty_day_hits
 FROM claims c LEFT JOIN public.wolo_indexed_transfers t
      ON c.wallet IS NOT NULL AND c.wallet <> ''
     AND lower(btrim(t.recipient_address))=c.wallet
     AND t.amount_uwolo=c.nominal*1000000
     AND t.chain_id='wolo-1' AND t.denom='uwolo'
 GROUP BY c.id,c.claim_kind,c.nominal,c.wallet,c.payout_attempted_at
), groups AS (
 SELECT claim_kind,count(*)::int AS claims,
        coalesce(sum(nominal),0)::text AS nominal_wolo,
        count(*) FILTER(WHERE wallet IS NOT NULL AND wallet <> '')::int AS wallet_count,
        count(*) FILTER(WHERE payout_attempted_at IS NOT NULL)::int AS attempted,
        count(*) FILTER(WHERE any_hits > 0)::int AS any_candidate_claims,
        count(*) FILTER(WHERE any_hits = 1)::int AS exactly_one_candidate_claims,
        count(*) FILTER(WHERE any_hits > 1)::int AS multiple_candidate_claims,
        count(*) FILTER(WHERE near_hits > 0)::int AS near_attempt_claims,
        count(*) FILTER(WHERE thirty_day_hits > 0)::int AS thirty_day_claims,
        coalesce(sum(any_hits),0)::int AS all_candidate_rows
 FROM match_rows GROUP BY claim_kind
), indexed AS (
 SELECT count(*)::int AS rows,
        max(height)::text AS max_height,
        max(timestamp)::date::text AS max_timestamp_utc_day,
        count(*) FILTER(WHERE chain_id='wolo-1' AND denom='uwolo')::int AS wolo_uwolo_rows
 FROM public.wolo_indexed_transfers
)
SELECT jsonb_build_object(
 'schema','wolo.c04.indexed-transfer-candidate-readonly-census.v1',
 'database','aoe2hd_db','financial_release_authorized',false,
 'index_not_independent_consensus_finality',true,
 'window_before_attempt_days',1,'near_after_attempt_days',7,
 'far_after_attempt_days',30,
 'index_rows',indexed.rows,
 'index_wolo_uwolo_rows',indexed.wolo_uwolo_rows,
 'index_max_height',indexed.max_height,
 'index_latest_utc_day',indexed.max_timestamp_utc_day,
 'groups',(SELECT coalesce(jsonb_agg(jsonb_build_object(
    'kind',claim_kind,'claims',claims,'nominal_wolo',nominal_wolo,
    'wallet_count',wallet_count,'attempted',attempted,
    'any_candidate_claims',any_candidate_claims,
    'exactly_one_candidate_claims',exactly_one_candidate_claims,
    'multiple_candidate_claims',multiple_candidate_claims,
    'near_attempt_claims',near_attempt_claims,
    'thirty_day_claims',thirty_day_claims,
    'all_candidate_rows',all_candidate_rows) ORDER BY claim_kind),'[]'::jsonb) FROM groups)
)::text FROM indexed;
ROLLBACK;
"""

class Hold(ValueError):
    pass

def need(ok,reason):
    if not ok:
        raise Hold(reason)

def count(value,top):
    need(type(value) is int and 0<=value<=top,"NONCANONICAL_COUNT")
    return value

def validate(data):
    need(type(data) is dict and set(data)=={
        "schema","database","financial_release_authorized",
        "index_not_independent_consensus_finality",
        "window_before_attempt_days","near_after_attempt_days",
        "far_after_attempt_days","index_rows","index_wolo_uwolo_rows",
        "index_max_height","index_latest_utc_day","groups"
    },"OBSERVATION_SCHEMA_DRIFT")
    need(data["schema"]==SOURCE_SCHEMA and data["database"]=="aoe2hd_db"
         and data["financial_release_authorized"] is False
         and data["index_not_independent_consensus_finality"] is True,
         "UNAUTHENTICATED_RELEASE_ASSERTION")
    need((data["window_before_attempt_days"],data["near_after_attempt_days"],
          data["far_after_attempt_days"])==(1,7,30),"TIME_WINDOW_DRIFT")
    indexed=count(data["index_rows"],10_000_000)
    same_chain=count(data["index_wolo_uwolo_rows"],indexed)
    need(indexed>0 and same_chain>0,"INDEX_EMPTY_OR_UNTRUSTED")
    need(type(data["index_max_height"]) is str and
         re.fullmatch(r"[1-9][0-9]{0,12}",data["index_max_height"]) and
         type(data["index_latest_utc_day"]) is str and
         re.fullmatch(r"20[0-9]{2}-[0-9]{2}-[0-9]{2}",
                      data["index_latest_utc_day"]), "INDEX_FRONTIER_UNKNOWN")
    groups=data["groups"]
    need(type(groups) is list and len(groups)==len(KIND),"CLAIM_KIND_DRIFT")
    names=set()
    safe={}
    for item in groups:
        need(type(item) is dict and set(item)=={
            "kind","claims","nominal_wolo","wallet_count","attempted",
            "any_candidate_claims","exactly_one_candidate_claims",
            "multiple_candidate_claims","near_attempt_claims",
            "thirty_day_claims","all_candidate_rows"
        }, "CLAIM_GROUP_SCHEMA_DRIFT")
        kind=item["kind"]
        need(type(kind) is str and kind in KIND and kind not in names,
             "UNKNOWN_OR_DUPLICATED_CLAIM_KIND")
        names.add(kind)
        expected_count,expected_nominal=KIND[kind]
        n=count(item["claims"],69)
        need(n==expected_count and type(item["nominal_wolo"]) is str and
             item["nominal_wolo"]==str(expected_nominal),"PINNED_C04_POPULATION_DRIFT")
        attempted=count(item["attempted"],n)
        wallet=count(item["wallet_count"],n)
        any_hits=count(item["any_candidate_claims"],n)
        unique=count(item["exactly_one_candidate_claims"],n)
        multi=count(item["multiple_candidate_claims"],n)
        near=count(item["near_attempt_claims"],n)
        far=count(item["thirty_day_claims"],n)
        total=count(item["all_candidate_rows"],n*indexed)
        need(wallet==n and unique+multi==any_hits and near<=far<=any_hits
             and near<=attempted and total>=unique+2*multi,
             "IMPOSSIBLE_TRANSFER_MATCH_COUNTS")
        safe[kind]={"claims":n,"nominal_wolo":str(expected_nominal),
            "wallet_identified":wallet,"recorded_attempts":attempted,
            "claim_with_any_candidates":any_hits,
            "claim_with_exactly_one_candidate":unique,
            "claim_with_many_candidates":multi,
            "claim_with_near_attempt_candidate":near,
            "claim_with_thirty_day_candidate":far,
            "candidate_index_rows":total}
    need(names==set(KIND),"MISSING_CLAIM_KIND")
    return {"schema":SCHEMA,"status":"HOLD_C04_INDEX_MATCHES_NOT_INDEPENDENT_PAYMENT_FINALITY",
        "observed_utc":datetime.now(timezone.utc).isoformat(),
        "claimset_identity_sha256_independently_verified_by_this_observer":False,
        "pin_69_claims_population":True,
        "index_rows":indexed,"index_wolo_uwolo_rows":same_chain,
        "index_max_height":data["index_max_height"],
        "index_latest_utc_day":data["index_latest_utc_day"],
        "groups":safe,
        "original_69_claim_payout_hashes_present":False,
        "candidate_transfer_is_payment_proof":False,
        "any_transfer_is_unique_economic_effect_proven":False,
        "independent_comet_bank_and_inclusion_proven":False,
        "claim_discharge_authorized":False,
        "retry_authorized":False,
        "funded_release_authorized":False,
        "production_mutated":False}

def private_read(path):
    path=Path(path)
    need(path.is_absolute() and not path.is_symlink(),"ABSOLUTE_PRIVATE_PATH_REQUIRED")
    s=path.lstat()
    need(stat.S_ISREG(s.st_mode) and s.st_nlink==1 and
         stat.S_IMODE(s.st_mode)==0o600 and s.st_uid==os.geteuid(),
         "PRIVATE_FILE_0600_OWNER_REQUIRED")
    need(0<s.st_size<=MAX,"PRIVATE_OBSERVATION_SIZE")
    return path.read_bytes()

def main(argv=None):
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--emit-hd-sql",action="store_true")
    ap.add_argument("--classify",action="store_true")
    ap.add_argument("--input",type=Path)
    ap.add_argument("--input-sha256")
    args=ap.parse_args(argv)
    try:
        need(args.emit_hd_sql!=args.classify,"EXACT_ONE_MODE_REQUIRED")
        if args.emit_hd_sql:
            need(args.input is None and args.input_sha256 is None,
                 "SQL_MODE_NO_EXTERNAL_EVIDENCE")
            print(SQL)
            return 3
        need(args.input is not None and type(args.input_sha256) is str
             and SHA.fullmatch(args.input_sha256),"SHA_BOUND_INPUT_REQUIRED")
        raw=private_read(args.input)
        need(hashlib.sha256(raw).hexdigest()==args.input_sha256,
             "SOURCE_SNAPSHOT_CHANGED")
        data=json.loads(raw)
        print(json.dumps(validate(data),sort_keys=True))
        return 3
    except (Hold,ValueError,OSError,UnicodeError,json.JSONDecodeError) as e:
        reason=str(e) if isinstance(e,Hold) else "SOURCE_EVIDENCE_UNAVAILABLE"
        print(json.dumps({"schema":SCHEMA,"status":"STOP","reason":reason,
            "financial_release_authorized":False,"production_mutated":False},sort_keys=True))
        return 2

if __name__=="__main__":
    sys.exit(main())

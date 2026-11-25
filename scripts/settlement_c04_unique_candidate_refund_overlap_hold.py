#!/usr/bin/env python3
"""C04 READ ONLY: detect unique indexed transfer already allocated to refund.

An unhash-linked historical bet_payout has one wallet+amount local indexed
transfer. That same hash is also stored in a different market's claimed
bet_refund and void bet_wager payout. Such a candidate cannot be used
as independent evidence to discharge the other obligation.
Only STOP/HOLD; no financial source update, retry, credit or release.
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

SCHEMA="wolo.c04.unique-indexed-tx-prior-refund-overlap-hold.v1"
INPUT_SCHEMA="wolo.c04.unique-indexed-tx-refund-overlap-readonly-census.v1"
MAX_FILE=100_000
HEX64=re.compile(r"[0-9a-f]{64}\Z")
SQL="""BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;
SET LOCAL statement_timeout='10000ms';
WITH unresolved AS (
 SELECT c.id,c.claim_kind,c.amount_wolo,c.claimed_by_user_id,
        c.source_market_id,lower(btrim(u.wallet_address)) AS wallet
 FROM public.pending_wolo_claims c
 LEFT JOIN public.users u ON u.id=c.claimed_by_user_id
 WHERE c.status='claimed'
 AND NULLIF(btrim(coalesce(c.payout_tx_hash,'')),'') IS NULL
), matches AS (
 SELECT c.id,c.claim_kind,c.amount_wolo,c.claimed_by_user_id,
        c.source_market_id,
        count(t.id)::int AS candidate_count,max(t.tx_hash) AS tx_hash
 FROM unresolved c LEFT JOIN public.wolo_indexed_transfers t
 ON c.wallet=lower(btrim(t.recipient_address))
 AND t.chain_id='wolo-1' AND t.denom='uwolo'
 AND t.amount_uwolo=c.amount_wolo::bigint*1000000
 GROUP BY c.id,c.claim_kind,c.amount_wolo,c.claimed_by_user_id,c.source_market_id
), unique_c AS (
 SELECT *,regexp_replace(upper(btrim(tx_hash)),'^0X','') AS normalized_hash
 FROM matches WHERE candidate_count=1
), attribution AS (
 SELECT u.id,u.claim_kind,u.source_market_id,
  (SELECT count(*)::int FROM public.pending_wolo_claims prior
    WHERE prior.status='claimed' AND
     regexp_replace(upper(btrim(coalesce(prior.payout_tx_hash,''))),'^0X','')
      =u.normalized_hash) AS claimed_hash_references,
  (SELECT count(*)::int FROM public.bet_wagers wager
    WHERE regexp_replace(upper(btrim(coalesce(wager.payout_tx_hash,''))),'^0X','')
      =u.normalized_hash) AS wager_hash_references,
  (SELECT count(*)::int FROM public.pending_wolo_claims prior
    JOIN public.bet_wagers wager ON
      regexp_replace(upper(btrim(coalesce(wager.payout_tx_hash,''))),'^0X','')
       =regexp_replace(upper(btrim(coalesce(prior.payout_tx_hash,''))),'^0X','')
    WHERE prior.status='claimed' AND prior.claim_kind='bet_refund'
      AND wager.status='void'
      AND prior.source_market_id=wager.market_id
      AND prior.source_market_id IS DISTINCT FROM u.source_market_id
      AND prior.claimed_by_user_id=u.claimed_by_user_id
      AND wager.user_id=u.claimed_by_user_id
      AND prior.amount_wolo=u.amount_wolo AND wager.payout_wolo=u.amount_wolo
      AND regexp_replace(upper(btrim(coalesce(prior.payout_tx_hash,''))),'^0X','')
        =u.normalized_hash) AS exact_other_market_void_refund_links
 FROM unique_c u
)
SELECT jsonb_build_object(
 'schema','wolo.c04.unique-indexed-tx-refund-overlap-readonly-census.v1',
 'database','aoe2hd_db','financial_release_authorized',false,
 'claim_count',(SELECT count(*)::int FROM unresolved),
 'nominal_ambiguous_wolo',(SELECT coalesce(sum(amount_wolo),0)::text FROM unresolved),
 'unique_wallet_amount_candidate_claims',(SELECT count(*)::int FROM attribution),
 'unique_bet_payout_candidate_claims',(SELECT count(*)::int FROM attribution
     WHERE claim_kind='bet_payout'),
 'unique_candidate_hash_already_claimed_count',(SELECT count(*)::int FROM attribution
     WHERE claimed_hash_references>0),
 'unique_candidate_hash_on_wager_count',(SELECT count(*)::int FROM attribution
     WHERE wager_hash_references>0),
 'unique_bet_payout_candidate_prior_other_market_void_refund_count',
     (SELECT count(*)::int FROM attribution
      WHERE claim_kind='bet_payout' AND exact_other_market_void_refund_links>0),
 'local_index_is_independent_bank_proof',false,
 'candidate_can_discharge_original_claim',false
)::text;
ROLLBACK;
"""

class Hold(ValueError):
    pass

def need(ok,why):
    if not ok:raise Hold(why)

def require_integer(x,upper):
    need(type(x) is int and 0<=x<=upper,"NONCANONICAL_C04_COUNT")
    return x

def classify(d):
    need(type(d) is dict and set(d)=={
        "schema","database","financial_release_authorized",
        "claim_count","nominal_ambiguous_wolo",
        "unique_wallet_amount_candidate_claims",
        "unique_bet_payout_candidate_claims",
        "unique_candidate_hash_already_claimed_count",
        "unique_candidate_hash_on_wager_count",
        "unique_bet_payout_candidate_prior_other_market_void_refund_count",
        "local_index_is_independent_bank_proof",
        "candidate_can_discharge_original_claim"},
        "C04_ECONOMIC_OVERLAP_SCHEMA_DRIFT")
    need(d["schema"]==INPUT_SCHEMA and d["database"]=="aoe2hd_db"
         and d["financial_release_authorized"] is False
         and d["local_index_is_independent_bank_proof"] is False
         and d["candidate_can_discharge_original_claim"] is False,
         "C04_FORGED_PAYMENT_FINALITY")
    count=require_integer(d["claim_count"],100000)
    need(count==69 and d["nominal_ambiguous_wolo"]=="120443",
         "C04_CLAIMSET_COUNT_OR_NOMINAL_DRIFT")
    unique=require_integer(d["unique_wallet_amount_candidate_claims"],count)
    bet=require_integer(d["unique_bet_payout_candidate_claims"],unique)
    prior=require_integer(d["unique_candidate_hash_already_claimed_count"],unique)
    wager=require_integer(d["unique_candidate_hash_on_wager_count"],unique)
    conflict=require_integer(
        d["unique_bet_payout_candidate_prior_other_market_void_refund_count"],bet)
    need(conflict<=prior and conflict<=wager,
         "C04_IMPOSSIBLE_CROSS_SURFACE_REFUND_OVERLAP_COUNTS")
    return {
        "schema":SCHEMA,
        "status":("HOLD_C04_UNIQUE_TRANSFER_ALREADY_ATTRIBUTED_TO_OTHER_MARKET_REFUND"
                  if conflict else "HOLD_C04_UNIQUE_TRANSFER_NOT_PAYMENT_FINALITY"),
        "claim_count":count,
        "nominal_ambiguous_wolo":"120443",
        "unique_candidate_claims":unique,
        "unique_bet_payout_claims":bet,
        "unique_indexed_tx_already_in_claim_record_count":prior,
        "unique_indexed_tx_already_in_wager_record_count":wager,
        "unique_bet_payout_candidate_attributed_to_different_market_void_refund_count":conflict,
        "other_market_economic_overlap_resolved":False,
        "same_operator_local_chain_only":True,
        "independent_canonical_chain_finality_proven":False,
        "claim_discharge_authorized":False,
        "retry_authorized":False,
        "financial_release_authorized":False,
        "production_mutated":False
    }

def private_read(path:Path,sha:str):
    need(path.is_absolute() and not path.is_symlink() and
         type(sha) is str and HEX64.fullmatch(sha),"C04_PRIVATE_INPUT_FORMAT")
    st=path.lstat()
    need(st.st_uid==os.geteuid() and st.st_nlink==1 and
         stat.S_ISREG(st.st_mode) and stat.S_IMODE(st.st_mode)==0o600 and
         0<st.st_size<=MAX_FILE,"C04_PRIVATE_EVIDENCE_MODE")
    raw=path.read_bytes()
    need(len(raw)==st.st_size and hashlib.sha256(raw).hexdigest()==sha,
         "C04_EVIDENCE_DRIFT")
    return json.loads(raw)

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--emit-hd-sql",action="store_true")
    p.add_argument("--classify",action="store_true")
    p.add_argument("--input",type=Path)
    p.add_argument("--input-sha256")
    a=p.parse_args(argv)
    try:
        need(a.emit_hd_sql != a.classify,"EXACT_ONE_READONLY_MODE")
        if a.emit_hd_sql:
            need(a.input is None and a.input_sha256 is None,
                 "C04_NO_RAW_INPUT_IN_SQL_MODE")
            print(SQL);return 3
        need(a.input is not None and a.input_sha256 is not None,
             "C04_SOURCE_HASH_REQUIRED")
        print(json.dumps(classify(private_read(a.input,a.input_sha256)),sort_keys=True))
        return 3
    except (Hold,OSError,ValueError,TypeError,UnicodeError) as e:
        why=str(e) if isinstance(e,Hold) else "C04_PRIVATE_EVIDENCE_UNAVAILABLE"
        print(json.dumps({"schema":SCHEMA,"status":"STOP","reason":why,
                          "financial_release_authorized":False,
                          "production_mutated":False},sort_keys=True))
        return 2

if __name__=="__main__":
    sys.exit(main())

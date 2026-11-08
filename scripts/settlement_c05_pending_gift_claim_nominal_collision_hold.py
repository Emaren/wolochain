#!/usr/bin/env python3
"""C05 bounded READ ONLY pending-gift claim-nominal collision observer.

Equal recipient and nominal amount is not evidence that a gift was
funded or that a historical wager payout discharged a different gift.
Only aggregate output; HOLD or STOP, never customer mutation/approval.
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

INPUT_SCHEMA = "wolo.c05.pending-gifts-same-user-claim-nominal-census.v1"
SCHEMA = "wolo.c05.pending-gifts-same-user-claim-nominal-hold.v1"
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
MAX_INPUT = 32768
SQL = """BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;
SET LOCAL statement_timeout='9000ms';
SET LOCAL lock_timeout='1000ms';
WITH gifts AS (
 SELECT id,user_id,amount,created_at
 FROM public.user_gifts
 WHERE kind='WOLO' AND status='pending'
), per_gift AS (
 SELECT g.amount,
 (SELECT count(*)::int FROM public.pending_wolo_claims p
  WHERE p.claimed_by_user_id=g.user_id AND p.amount_wolo=g.amount) AS claims,
 (SELECT count(*)::int FROM public.pending_wolo_claims p
  WHERE p.claimed_by_user_id=g.user_id AND p.amount_wolo=g.amount
  AND p.status='claimed') AS claimed,
 (SELECT count(*)::int FROM public.pending_wolo_claims p
  WHERE p.claimed_by_user_id=g.user_id AND p.amount_wolo=g.amount
  AND nullif(btrim(coalesce(p.payout_tx_hash,'')),'') IS NOT NULL) AS hash_bearing,
 (SELECT count(*)::int FROM public.pending_wolo_claims p
  WHERE p.claimed_by_user_id=g.user_id AND p.amount_wolo=g.amount
  AND p.claim_kind='bet_refund') AS refund_claims,
 (SELECT count(*)::int FROM public.pending_wolo_claims p
  WHERE p.claimed_by_user_id=g.user_id AND p.amount_wolo=g.amount
  AND p.claim_kind='bet_payout') AS payout_claims,
 (SELECT count(*)::int FROM public.pending_wolo_claims p
  WHERE p.claimed_by_user_id=g.user_id AND p.amount_wolo=g.amount
  AND abs(extract(epoch from (p.created_at-g.created_at)))<=86400) AS within_day,
 (SELECT count(*)::int FROM public.pending_wolo_claims p
  WHERE p.claimed_by_user_id=g.user_id AND p.amount_wolo=g.amount
  AND abs(extract(epoch from (p.created_at-g.created_at)))<=2592000) AS within_30_days
 FROM gifts g
), buckets AS (
 SELECT amount::text AS amount_wolo, count(*)::int AS gifts,
 sum(claims)::int AS claims,sum(claimed)::int AS claimed,
 sum(hash_bearing)::int AS hash_bearing,
 sum(refund_claims)::int AS refund_claims,
 sum(payout_claims)::int AS payout_claims,
 sum(within_day)::int AS within_day,
 sum(within_30_days)::int AS within_30_days
 FROM per_gift GROUP BY amount
)
SELECT jsonb_build_object(
 'schema','wolo.c05.pending-gifts-same-user-claim-nominal-census.v1',
 'database',current_database(),
 'pending_gifts',(SELECT count(*)::int FROM gifts),
 'amount_buckets',coalesce((SELECT jsonb_agg(
  jsonb_build_object('amount_wolo',amount_wolo,'gifts',gifts,
   'claims',claims,'claimed',claimed,'hash_bearing',hash_bearing,
   'refund_claims',refund_claims,'payout_claims',payout_claims,
   'within_day',within_day,'within_30_days',within_30_days)
 ORDER BY amount_wolo) FROM buckets),'[]'::jsonb),
 'economic_identity_proven',false,
 'chain_payment_finality_proven',false,
 'gift_discharge_authorized',false,
 'financial_release_authorized',false
)::text WHERE current_database()='aoe2hd_db';
ROLLBACK;
"""

class Hold(ValueError):
    pass

def require(ok: bool, reason: str) -> None:
    if not ok:
        raise Hold(reason)

def integer(x):
    require(type(x) is int and 0 <= x <= 1000000, "NONCANONICAL_COUNT")
    return x

def classify(x):
    fields = {"schema","database","pending_gifts","amount_buckets",
              "economic_identity_proven","chain_payment_finality_proven",
              "gift_discharge_authorized","financial_release_authorized"}
    require(type(x) is dict and set(x)==fields, "C05_CENSUS_SCHEMA_DRIFT")
    require(x["schema"]==INPUT_SCHEMA and x["database"]=="aoe2hd_db" and
            all(x[k] is False for k in (
              "economic_identity_proven","chain_payment_finality_proven",
              "gift_discharge_authorized","financial_release_authorized")),
            "C05_FORGED_ECONOMIC_AUTHORITY")
    require(integer(x["pending_gifts"])==2,"C05_PENDING_GIFT_POPULATION_CHANGED")
    buckets=x["amount_buckets"]
    require(type(buckets) is list and len(buckets)==2,"C05_GIFT_BUCKET_DRIFT")
    expected={"100000":{"gifts":1,"claims":0,"claimed":0,
             "hash_bearing":0,"refund_claims":0,"payout_claims":0,
             "within_day":0,"within_30_days":0},
              "100":{"gifts":1,"claims":24,"claimed":24,
             "hash_bearing":24,"refund_claims":20,"payout_claims":4,
             "within_day":0,"within_30_days":13}}
    seen=set()
    required={"amount_wolo","gifts","claims","claimed","hash_bearing",
              "refund_claims","payout_claims","within_day","within_30_days"}
    for row in buckets:
        require(type(row) is dict and set(row)==required,"C05_BUCKET_FIELDS_DRIFT")
        amount=row["amount_wolo"]
        require(type(amount) is str and amount in expected and amount not in seen,
                "C05_AMOUNT_BUCKET_DRIFT")
        seen.add(amount)
        counts={k:integer(v) for k,v in row.items() if k!="amount_wolo"}
        require(counts["hash_bearing"]<=counts["claims"] and
                counts["claimed"]<=counts["claims"] and
                counts["refund_claims"]+counts["payout_claims"]<=counts["claims"]
                and counts["within_day"]<=counts["within_30_days"]<=counts["claims"],
                "C05_SOURCE_COUNTER_INCONSISTENCY")
        require(counts==expected[amount],"C05_CLAIM_NOMINAL_OVERLAP_CHANGED")
    require(seen==set(expected),"C05_PENDING_GIFT_AMOUNTS_MISSING")
    return {
      "schema":SCHEMA,
      "status":"HOLD_C05_SAME_RECIPIENT_AMOUNT_IS_NOT_GIFT_PAYOUT_IDENTITY",
      "pending_gift_count":2,
      "bounty_100000_gift_nominal_match_claims":0,
      "gift_100_same_user_nominal_claims":24,
      "gift_100_same_user_nominal_hashed_claims":24,
      "gift_100_same_user_nominal_bet_refunds":20,
      "gift_100_same_user_nominal_bet_payouts":4,
      "gift_100_exact_time_proximity_1day_claims":0,
      "source_nominal_match_is_unique_economic_payout":False,
      "independent_chain_finality_authenticated":False,
      "gift_paid_or_discharge_proven":False,
      "gift_cancellation_proven":False,
      "funded_retry_authorized":False,
      "financial_release_authorized":False,
      "production_modified":False,
    }

def load_private(path:Path, expected:str):
    require(path.is_absolute() and type(expected) is str and HEX64.fullmatch(expected),
            "C05_EVIDENCE_ARGS_INVALID")
    fd=os.open(path,os.O_RDONLY|getattr(os,"O_NOFOLLOW",0))
    try:
        before=os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and before.st_uid==os.geteuid() and
                before.st_nlink==1 and stat.S_IMODE(before.st_mode)==0o600 and
                0<before.st_size<=MAX_INPUT, "C05_PRIVATE_SOURCE_MODE_OR_SIZE")
        with os.fdopen(os.dup(fd),"rb") as f:
            raw=f.read(MAX_INPUT+1)
        after=os.fstat(fd)
        require(before.st_ino==after.st_ino and before.st_size==after.st_size and
                len(raw)==before.st_size and hashlib.sha256(raw).hexdigest()==expected,
                "C05_PRIVATE_SOURCE_SHA_CHANGED")
        return json.loads(raw)
    finally:
        os.close(fd)

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    modes=p.add_mutually_exclusive_group(required=True)
    modes.add_argument("--emit-hd-sql",action="store_true")
    modes.add_argument("--classify",action="store_true")
    p.add_argument("--input",type=Path)
    p.add_argument("--input-sha256")
    a=p.parse_args(argv)
    try:
        if a.emit_hd_sql:
            require(a.input is None and a.input_sha256 is None,
                    "C05_SQL_NO_PRIVATE_INPUT")
            print(SQL)
            return 3
        require(a.input is not None and a.input_sha256 is not None,
                "C05_PRIVATE_EVIDENCE_REQUIRED")
        print(json.dumps(classify(load_private(a.input,a.input_sha256)),sort_keys=True))
        return 3
    except (Hold,OSError,ValueError,TypeError,UnicodeError) as exc:
        reason=str(exc) if isinstance(exc,Hold) else "C05_PRIVATE_SOURCE_UNAVAILABLE"
        print(json.dumps({"schema":SCHEMA,"status":"STOP","reason":reason,
                          "financial_release_authorized":False,
                          "production_modified":False},sort_keys=True))
        return 2

if __name__=="__main__":
    sys.exit(main())

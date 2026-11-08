#!/usr/bin/env python3
"""C05 read-only source attribution for the historical 100,000-WOLO bounty gift.

A gift pointing to an opportunity is NOT entitlement evidence when source
reward valuation, assignee and publication are all absent. Only aggregates
leave PostgreSQL; STOP on source drift, HOLD on exact known observation.
This tool cannot grant payment authority, settle gifts, or write any ledger.
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

SOURCE_SCHEMA="wolo.c05.bounty-100k-gift-assignment-source-readonly.v1"
SCHEMA="wolo.c05.bounty-100k-gift-assignment-and-publication-hold.v1"
HEX64=re.compile(r"[0-9a-f]{64}\Z")
MAX_BYTES=16_384
SQL="""BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;
SET LOCAL statement_timeout='9000ms';
SET LOCAL lock_timeout='1000ms';
WITH source_gifts AS (
 SELECT g.id,g.user_id,g.amount,
        substring(lower(coalesce(g.note,'')) from 'bounty #[[:space:]]*([0-9]+)') AS ref
 FROM public.user_gifts g
 WHERE g.kind='WOLO' AND g.status='pending' AND g.amount=100000
), matched AS (
 SELECT g.id,g.user_id,g.amount,b.id AS opportunity_id,
        b.assigned_user_id,b.reward_wolo,b.status,b.published_at,b.expires_at
 FROM source_gifts g
 LEFT JOIN public.bounty_opportunities b
 ON g.ref IS NOT NULL AND b.id::text=g.ref
), outcome AS (
 SELECT count(*)::int AS gifts,
  count(*) FILTER (WHERE opportunity_id IS NOT NULL)::int AS linked,
  count(*) FILTER (WHERE opportunity_id IS NULL)::int AS unlinked,
  count(*) FILTER (WHERE opportunity_id IS NOT NULL
                  AND assigned_user_id IS NULL)::int AS unassigned,
  count(*) FILTER (WHERE opportunity_id IS NOT NULL
                  AND assigned_user_id=user_id)::int AS assigned_to_gift_recipient,
  count(*) FILTER (WHERE opportunity_id IS NOT NULL
                  AND assigned_user_id IS NOT NULL
                  AND assigned_user_id<>user_id)::int AS assigned_to_other_user,
  count(*) FILTER (WHERE opportunity_id IS NOT NULL
                  AND reward_wolo IS NULL)::int AS reward_null,
  count(*) FILTER (WHERE opportunity_id IS NOT NULL
                  AND reward_wolo=amount)::int AS reward_matches_gift,
  count(*) FILTER (WHERE opportunity_id IS NOT NULL
                  AND reward_wolo IS NOT NULL
                  AND reward_wolo<>amount)::int AS reward_conflicts,
  count(*) FILTER (WHERE opportunity_id IS NOT NULL
                  AND published_at IS NULL)::int AS unpublished,
  count(*) FILTER (WHERE opportunity_id IS NOT NULL
                  AND published_at IS NOT NULL)::int AS published,
  count(*) FILTER (WHERE opportunity_id IS NOT NULL
                  AND status='available')::int AS available,
  count(*) FILTER (WHERE opportunity_id IS NOT NULL
                  AND status<>'available')::int AS other_status,
  count(*) FILTER (WHERE opportunity_id IS NOT NULL
                  AND expires_at IS NOT NULL AND expires_at<now())::int AS expired,
  (SELECT count(*)::int FROM public.bounty_events e
   JOIN matched m ON e.opportunity_id=m.opportunity_id) AS related_events,
  (SELECT count(*)::int FROM public.bounty_events e
   JOIN matched m ON e.opportunity_id=m.opportunity_id
   WHERE NULLIF(btrim(coalesce(e.tx_hash,'')),'') IS NOT NULL) AS related_hashes
 FROM matched
)
SELECT jsonb_build_object(
 'schema','wolo.c05.bounty-100k-gift-assignment-source-readonly.v1',
 'database',current_database(),
 'gift_nominal_wolo','100000',
 'pending_100k_gifts',gifts,
 'linked_opportunities',linked,
 'unlinked_gifts',unlinked,
 'linked_unassigned_opportunities',unassigned,
 'linked_assigned_to_gift_recipient',assigned_to_gift_recipient,
 'linked_assigned_to_other_recipient',assigned_to_other_user,
 'linked_reward_null',reward_null,
 'linked_reward_matches_gift',reward_matches_gift,
 'linked_reward_conflicts',reward_conflicts,
 'linked_unpublished',unpublished,
 'linked_published',published,
 'linked_available_status',available,
 'linked_other_status',other_status,
 'linked_expired',expired,
 'related_bounty_events',related_events,
 'related_bounty_events_with_tx_hash',related_hashes,
 'independent_bounty_entitlement_authenticated',false,
 'chain_payment_finality_authenticated',false,
 'financial_release_authorized',false
)::text FROM outcome
WHERE current_database()='aoe2hd_db';
ROLLBACK;
"""

class Hold(ValueError): pass

def require(ok,reason):
    if not ok: raise Hold(reason)

def qty(x):
    require(type(x) is int and 0<=x<=10000,"C05_AGGREGATE_NONCANONICAL")
    return x

def classify(doc):
    required={"schema","database","gift_nominal_wolo","pending_100k_gifts",
      "linked_opportunities","unlinked_gifts",
      "linked_unassigned_opportunities",
      "linked_assigned_to_gift_recipient",
      "linked_assigned_to_other_recipient",
      "linked_reward_null","linked_reward_matches_gift","linked_reward_conflicts",
      "linked_unpublished","linked_published","linked_available_status",
      "linked_other_status","linked_expired","related_bounty_events",
      "related_bounty_events_with_tx_hash",
      "independent_bounty_entitlement_authenticated",
      "chain_payment_finality_authenticated","financial_release_authorized"}
    require(type(doc) is dict and set(doc)==required,"C05_SOURCE_FIELDS_DRIFT")
    require(doc["schema"]==SOURCE_SCHEMA and doc["database"]=="aoe2hd_db"
      and doc["gift_nominal_wolo"]=="100000"
      and doc["independent_bounty_entitlement_authenticated"] is False
      and doc["chain_payment_finality_authenticated"] is False
      and doc["financial_release_authorized"] is False,
      "C05_FORGED_BOUNTY_AUTHORITY")
    keys=required-{"schema","database","gift_nominal_wolo",
      "independent_bounty_entitlement_authenticated",
      "chain_payment_finality_authenticated","financial_release_authorized"}
    x={k:qty(doc[k]) for k in keys}
    n=x["pending_100k_gifts"];linked=x["linked_opportunities"]
    require(n==1 and linked==1 and x["unlinked_gifts"]==0,
      "C05_PINNED_GIFT_AND_OPPORTUNITY_DRIFT")
    require(x["linked_unassigned_opportunities"]+
      x["linked_assigned_to_gift_recipient"]+
      x["linked_assigned_to_other_recipient"]==linked,
      "C05_BOUNTY_ASSIGNEE_PARTITION_INVALID")
    require(x["linked_reward_null"]+x["linked_reward_matches_gift"]+
      x["linked_reward_conflicts"]==linked,
      "C05_REWARD_VALUATION_PARTITION_INVALID")
    require(x["linked_unpublished"]+x["linked_published"]==linked and
      x["linked_available_status"]+x["linked_other_status"]==linked
      and x["linked_expired"]<=linked and
      x["related_bounty_events_with_tx_hash"]<=x["related_bounty_events"],
      "C05_SOURCE_PUBLICATION_OR_EVENT_INCONSISTENT")
    require(x["linked_unassigned_opportunities"]==1 and
      x["linked_reward_null"]==1 and x["linked_unpublished"]==1 and
      x["linked_available_status"]==1 and
      x["related_bounty_events"]==0,
      "C05_BOUNTY_SOURCE_CHANGED_REQUIRES_INDEPENDENT_REVIEW")
    return {
      "schema":SCHEMA,
      "status":"HOLD_C05_BOUNTY_GIFT_HAS_NO_ASSIGNEE_NO_REWARD_AND_NOT_PUBLISHED",
      "gift_nominal_wolo":"100000","gift_source_record_count":n,
      "matched_opportunity_count":linked,
      "source_assigned_recipient_count":0,
      "source_reward_valuation_present_count":0,
      "source_published_count":0,
      "source_status_available_count":1,
      "related_bounty_event_count":0,
      "unknown_other_offchain_obligation_exists":True,
      "source_owner_assignment_is_entitlement_proof":False,
      "source_available_status_is_earned_payout_proof":False,
      "independent_bounty_entitlement_authenticated":False,
      "independent_chain_payment_finality_authenticated":False,
      "customer_retry_authorized":False,
      "financial_release_authorized":False,
      "production_modified":False}

def private_read(path:Path,sha:str):
    require(path.is_absolute() and not path.is_symlink() and
      type(sha) is str and HEX64.fullmatch(sha),
      "C05_PRIVATE_EVIDENCE_INPUT_FORMAT")
    st=path.lstat()
    require(stat.S_ISREG(st.st_mode) and st.st_uid==os.geteuid()
      and st.st_nlink==1 and stat.S_IMODE(st.st_mode)==0o600
      and 0<st.st_size<MAX_BYTES,"C05_PRIVATE_SOURCE_NOT_ROOTED")
    raw=path.read_bytes()
    require(len(raw)==st.st_size and hashlib.sha256(raw).hexdigest()==sha,
      "C05_PRIVATE_SOURCE_DIGEST_CHANGED")
    return json.loads(raw)

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    g=p.add_mutually_exclusive_group(required=True)
    g.add_argument("--emit-hd-sql",action="store_true")
    g.add_argument("--classify",action="store_true")
    p.add_argument("--input",type=Path);p.add_argument("--input-sha256")
    a=p.parse_args(argv)
    try:
        if a.emit_hd_sql:
            require(a.input is None and a.input_sha256 is None,
              "C05_SQL_MODE_NO_PRIVATE_INPUT")
            print(SQL);return 3
        require(a.input and a.input_sha256,"C05_PRIVATE_INPUT_REQUIRED")
        print(json.dumps(classify(private_read(a.input,a.input_sha256)),sort_keys=True))
        return 3
    except (Hold,ValueError,OSError,TypeError,UnicodeError) as e:
        why=str(e) if isinstance(e,Hold) else "C05_SOURCE_UNAVAILABLE"
        print(json.dumps({"schema":SCHEMA,"status":"STOP","reason":why,
          "financial_release_authorized":False,"production_modified":False},sort_keys=True))
        return 2

if __name__=="__main__":
    sys.exit(main())

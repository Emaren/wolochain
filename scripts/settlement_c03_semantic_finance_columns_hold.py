#!/usr/bin/env python3
"""C03 semantic money-column coverage, READ-ONLY and financial HARD HOLD.

A name-based ownership migration is incomplete even after adding payout/transfer:
marketplace, forge, staking, trophy, scheduled matches and sponsorship can all
contain WOLO amounts or chain transaction hashes without those name tokens.
This observer pins actual column-bearing names, never grants write authority.
"""
from __future__ import annotations
from datetime import datetime,timezone
import hashlib
import json
import os
import re
import subprocess
import sys

SCHEMA="wolo.c03.unclassified-financial-semantic-columns-hold.v1"
NAME_PATTERN="(wolo|bet|wager|settle|claim|escrow|refund|reward|stake|treasury|wallet|founder|bonus|payout|transfer)"
COLUMN_PATTERN="(amount.*wolo|wolo.*amount|tx_hash|transaction_hash|recipient_address|owner_address|escrow|payment|payout|withdraw|deposit|balance|stake|reward)"
EXPECTED={
 "aoe2hd_db":(
  "bounty_events","bounty_opportunities","bounty_valuations","event_tiles",
  "feature_requests","forge_commitments","forge_events","leagues",
  "marketplace_inquiries","marketplace_invoices","marketplace_payments",
  "marketplace_shops","marketplace_tax_payments","scheduled_match_funding_proofs",
  "scheduled_matches","staking_daily_stats","staking_events",
  "staking_events_repair_backup_20260622","staking_positions","trophies",
  "trophy_challenges","trophy_economics_versions","trophy_events","war_graph_rulesets"),
 "aoe2de_db":(
  "event_tiles","scheduled_matches","staking_daily_stats","staking_events",
  "staking_positions","trophies","trophy_challenges","trophy_economics_versions",
  "trophy_events")
}
SAFE=re.compile(r"[a-z_][a-z0-9_]{0,62}\Z")
class Hold(ValueError):pass
def need(v,s):
 if not v:raise Hold(s)
def query(db):
 need(db in EXPECTED,"DATABASE_NOT_ALLOWLISTED")
 return f"""
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;
WITH candidate AS (
 SELECT table_name,column_name
 FROM information_schema.columns
 WHERE table_schema='public'
 AND column_name ~* '{COLUMN_PATTERN}'
 AND table_name !~* '{NAME_PATTERN}'
)
SELECT table_name||'|'||string_agg(column_name,',' ORDER BY column_name)
 FROM candidate GROUP BY table_name ORDER BY table_name;
ROLLBACK;
"""
def parse(raw,db):
 need(db in EXPECTED and isinstance(raw,str) and len(raw.encode())<=32000,
      "SEMANTIC_RESULT_INVALID_OR_UNBOUNDED")
 d={}
 for line in raw.strip().splitlines():
  p=line.split("|")
  need(len(p)==2 and SAFE.fullmatch(p[0]) and p[0] not in d,
       "UNEXPECTED_OR_DUPLICATE_MONEY_BEARING_TABLE")
  cols=p[1].split(",")
  need(len(cols)==len(set(cols)) and all(SAFE.fullmatch(v) for v in cols),
       "UNKNOWN_MONEY_BEARING_COLUMN")
  need(all(re.search(COLUMN_PATTERN,c,re.IGNORECASE) for c in cols),
       "COL_VALUE_NOT_IN_RISK_QUERY")
  need(not re.search(NAME_PATTERN,p[0],re.IGNORECASE),
       "PATTERN_SCOPE_COLLISION")
  d[p[0]]=cols
 need(tuple(sorted(d))==tuple(sorted(EXPECTED[db])),
      "UNCLASSIFIED_FINANCIAL_SEMANTIC_TABLE_UNIVERSE_DRIFT")
 return {"database":db,"money_column_bearing_table_count":len(d),
         "candidate_financial_risk_tables":d,
         "all_candidates_finance_classified":False,
         "all_candidates_fenced":False}
def inspect(db):
 need(os.geteuid()==0 and db in EXPECTED,"ROOT_LOCAL_POSTGRES_OBSERVER_ONLY")
 p=subprocess.run(["runuser","-u","postgres","--","psql","-X","-qAt",
                   "-v","ON_ERROR_STOP=1","-d",db,"-c",query(db)],
                  capture_output=True,text=True,timeout=22)
 need(p.returncode==0 and not p.stderr.strip(),"READONLY_PG_CATALOG_FAILURE")
 return parse(p.stdout,db)
def main():
 try:
  d={name:inspect(name) for name in EXPECTED}
  payload={"schema":SCHEMA,"status":"HOLD_C03_ADDITIONAL_MONEY_COLUMN_TABLES_UNCLASSIFIED",
    "observed_at_utc":datetime.now(timezone.utc).isoformat(),
    "database_catalog":d,"financial_categorization_complete":False,
    "name_only_30_hd_11_de_scope_full_finance_fence":False,
    "all_writers_and_external_signers_isolated":False,
    "full_application_codepath_audit_complete":False,
    "automated_payout_retries_authorized":False,
    "neutral_owner_production_migration_authorized":False,
    "coordinated_c06_backup_authorized":False,
    "formal_c03_c06_c07_accepted":False,"financial_release_authorized":False}
  payload["catalog_sha256"]=hashlib.sha256(json.dumps(d,sort_keys=True,
      separators=(",",":")).encode()).hexdigest()
  print(json.dumps(payload,sort_keys=True,indent=2))
  return 3
 except (Hold,OSError,UnicodeError,subprocess.SubprocessError) as e:
  print(json.dumps({"schema":SCHEMA,"status":"STOP","reason":str(e)[:130],
                   "financial_release_authorized":False},sort_keys=True))
  return 2
if __name__=="__main__":sys.exit(main())

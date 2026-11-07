#!/usr/bin/env python3
"""C03 whole-HD/DE-PostgreSQL-public-schema finance-scope default-deny census.

Do not infer finance from table names alone. Inventory ALL user-facing public
base tables, classify conservatively by name OR financial columns OR explicit
asset/funding/provenance obligations. Any remaining relation is UNCLASSIFIED
until separately reviewed. This tool NEVER creates a writer fence, approves a
financial source category, snapshots bank state or authorizes a WOLO transfer.

Pre-migration baseline only. If roles/permissions change it MUST STOP, not
assert a post-migration fence. Only Linux local root -> PostgreSQL catalogue
SELECT with READ ONLY and ROLLBACK.
"""
from __future__ import annotations
from datetime import datetime, timezone
import hashlib
import json
import os
import re
import subprocess
import sys

SCHEMA="wolo.c03.full-public-schema-default-deny-financial-review-hold.v1"
NAME="(wolo|bet|wager|settle|claim|escrow|refund|reward|stake|treasury|wallet|founder|bonus|payout|transfer)"
SEMANTIC="(amount.*wolo|wolo.*amount|tx_hash|transaction_hash|recipient_address|owner_address|escrow|payment|payout|withdraw|deposit|balance|stake|reward)"
EXPECTED={
 "aoe2hd_db":{
    "legacy_owner":"aoe2hd_user",
    "total":190,"name_or_semantic":54,
    "explicit":(
     "championship_challenge_participants",
     "championship_custody_seats",
     "oracle_market_proposals",
     "oracle_paper_positions",
     "user_gifts",
     "war_graph_watcher_attestations",
    ),
 },
 "aoe2de_db":{
    "legacy_owner":"aoe2de_user",
    "total":52,"name_or_semantic":20,
    "explicit":("user_gifts",),
 },
}
ID=re.compile(r"[a-z_][a-z0-9_]{0,62}\Z")
MAX_RESPONSE=180_000
class Hold(ValueError):pass
def require(value,reason):
 if not value:raise Hold(reason)
def query(db):
 require(db in EXPECTED,"DATABASE_NOT_ALLOWLISTED")
 d=EXPECTED[db];role=d["legacy_owner"]
 explicit=",".join("'"+name+"'" for name in d["explicit"])
 return f"""
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;
WITH relations AS (
 SELECT c.oid,c.relname,c.relowner,
        (c.relname ~* '{NAME}') AS name_risk,
        EXISTS (
         SELECT 1 FROM pg_catalog.pg_attribute a
         WHERE a.attrelid=c.oid AND a.attnum>0 AND NOT a.attisdropped
         AND a.attname ~* '{SEMANTIC}'
        ) AS semantic_risk,
        c.relname IN ({explicit}) AS explicit_review,
        COALESCE(has_table_privilege('{role}',c.oid,'INSERT,UPDATE,DELETE,TRUNCATE'),false)
          OR COALESCE(has_any_column_privilege('{role}',c.oid,'INSERT,UPDATE'),false)
           AS old_role_write_capable,
        (SELECT string_agg(a.attname,',' ORDER BY a.attnum)
         FROM pg_catalog.pg_attribute a
         WHERE a.attrelid=c.oid AND a.attnum>0 AND NOT a.attisdropped)
         AS column_list
 FROM pg_catalog.pg_class c
 JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
 WHERE n.nspname='public' AND c.relkind IN ('r','p')
), report AS (
 SELECT 'META|'||current_database()||'|'||pg_get_userbyid(d.datdba) AS line
 FROM pg_catalog.pg_database d WHERE d.datname=current_database()
 UNION ALL
 SELECT 'TABLE|'||relname||'|'||pg_get_userbyid(relowner)||'|'||
  name_risk::integer||'|'||semantic_risk::integer||'|'||
  explicit_review::integer||'|'||old_role_write_capable::integer||'|'||
  column_list
 FROM relations
)
SELECT line FROM report ORDER BY line;
ROLLBACK;
"""
def parse(raw,db):
 require(db in EXPECTED and isinstance(raw,str) and
         0<len(raw.encode())<=MAX_RESPONSE,"INVALID_READONLY_CATALOG")
 x=EXPECTED[db];meta=[];tables={}
 for line in raw.strip().splitlines():
  parts=line.split("|")
  if parts[0]=="META":
   require(len(parts)==3 and not meta and parts[1]==db and parts[2]==x["legacy_owner"],
           "DATABASE_OWNER_IDENTITY_DRIFT")
   meta.append(parts[1:])
   continue
  require(parts[0]=="TABLE" and len(parts)==8,
          "UNKNOWN_CATALOG_RECORD")
  _,name,owner,flag_name,flag_sem,flag_exp,write,columns=parts
  require(bool(ID.fullmatch(name)) and bool(ID.fullmatch(owner)) and
          name not in tables,"INVALID_OR_DUPLICATE_TABLE")
  require(all(flag in ("0","1") for flag in (flag_name,flag_sem,flag_exp,write)),
          "CATALOG_FLAG_DRIFT")
  cols=columns.split(",")
  require(cols and len(cols)==len(set(cols)) and
          all(ID.fullmatch(c) for c in cols),"UNSAFE_OR_EMPTY_TABLE_COLUMNS")
  nr=bool(re.search(NAME,name,re.I))
  sr=any(re.search(SEMANTIC,c,re.I) for c in cols)
  er=name in x["explicit"]
  require((flag_name=="1")==nr and (flag_sem=="1")==sr and
          (flag_exp=="1")==er,"CANDIDATE_CLASSIFICATION_MISMATCH")
  risky=nr or sr or er
  if risky:require(owner==x["legacy_owner"] and write=="1",
                   "RISK_CANDIDATE_OWNER_OR_WRITER_DRIFT")
  tables[name]={"owner":owner,"name":nr,"semantic":sr,
                "explicit":er,"legacy_can_write":write=="1",
                "column_names":cols}
 require(len(meta)==1 and len(tables)==x["total"],
         "FULL_SCHEMA_TOTAL_DRIFT")
 existing={n for n,r in tables.items() if r["name"] or r["semantic"]}
 explicit={n for n,r in tables.items() if r["explicit"]}
 require(len(existing)==x["name_or_semantic"],"EXISTING_UNION_DRIFT")
 require(explicit==set(x["explicit"]) and not (explicit & existing),
         "MISSING_NEW_ASSET_FUNDING_PROVENANCE_SURFACE")
 unknown=sorted(set(tables)-existing-explicit)
 result={
  "database":db,"total_public_tables":len(tables),
  "name_or_semantic_candidates":len(existing),
  "new_explicit_review_candidates":sorted(explicit),
  "conservative_review_candidates":len(existing|explicit),
  "unclassified_tables":unknown,
  "unclassified_count":len(unknown),
  "all_candidates_owner_writable_currently":True,
  "exhaustive_app_writer_coverage_proven":False,
  "all_nonfinance_tables_classified":False,
  "catalog_schema_sha256":hashlib.sha256(json.dumps(tables,sort_keys=True,
                separators=(",",":")).encode()).hexdigest()
 }
 return result
def inspect(db):
 require(os.geteuid()==0 and db in EXPECTED,"ROOT_LOCAL_PG_CATALOG_ONLY")
 p=subprocess.run(["runuser","-u","postgres","--","psql","-X","-qAt",
      "-v","ON_ERROR_STOP=1","-d",db,"-c",query(db)],
      capture_output=True,text=True,timeout=28)
 require(p.returncode==0 and not p.stderr.strip(),"PG_FULL_SCHEMA_QUERY_FAILED")
 return parse(p.stdout,db)
def main():
 try:
  catalog={db:inspect(db) for db in EXPECTED}
  result={"schema":SCHEMA,"status":"HOLD_C03_PUBLIC_SCHEMA_FINANCIAL_REVIEW_INCOMPLETE",
       "observed_at_utc":datetime.now(timezone.utc).isoformat(),
       "databases":catalog,
       "finance_table_ownership_fence_proven":False,
       "financial_scope_complete":False,
       "user_gifts_bonds_nft_custody_require_independent_classification":True,
       "unclassified_tables_require_explicit_app_code_review":True,
       "unclassified_is_not_synonym_for_nonfinancial":True,
       "formal_c03_c06_c07_accepted":False,
       "funded_wolo_release_authorized":False}
  result["catalog_sha256"]=hashlib.sha256(json.dumps(catalog,sort_keys=True,
         separators=(",",":")).encode()).hexdigest()
  print(json.dumps(result,sort_keys=True,indent=2))
  return 3
 except (Hold,OSError,UnicodeError,subprocess.SubprocessError) as e:
  reason=str(e) if isinstance(e,Hold) else "CATALOG_OBSERVATION_ERROR"
  print(json.dumps({"schema":SCHEMA,"status":"STOP",
    "reason":reason[:160],"funded_wolo_release_authorized":False},
    sort_keys=True))
  return 2
if __name__=="__main__":sys.exit(main())

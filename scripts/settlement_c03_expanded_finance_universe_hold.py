#!/usr/bin/env python3
"""C03 live HD/DE payout/transfer inventory guard. READ-ONLY, release HARD HOLD.

Older 24 HD/10 DE finance-name patterns omitted real on-chain payout and NFT
transfer tables. This v2 inventory pins 30 HD/11 DE public relations, 40
attached sequences, trigger/view dependencies, and exact seven omitted names.
A heuristic name inventory is NEVER an exhaustive application-wide audit.
Never execute migration DDL or use this receipt for funded authorization.
"""
from __future__ import annotations
from datetime import datetime, timezone
import hashlib
import json
import os
import re
import subprocess
import sys

SCHEMA="wolo.c03.expanded-payout-transfer-finance-observer-hold.v1"
OLD_PATTERN="(wolo|bet|wager|settle|claim|escrow|refund|reward|stake|treasury|wallet|founder|bonus)"
PATTERN="(wolo|bet|wager|settle|claim|escrow|refund|reward|stake|treasury|wallet|founder|bonus|payout|transfer)"
EXPECTED={
 "aoe2hd_db":{
  "owner":"aoe2hd_user","schema_owner":"pg_database_owner","tables":30,"sequences":29,"triggers":15,
  "security_definer_triggers":0,"views":7,
  "newly_included":(
   "bounty_payouts","championship_transfer_groups",
   "championship_transfer_seats","trophy_payout_allocations",
   "trophy_payouts","war_graph_payout_events")},
 "aoe2de_db":{
  "owner":"aoe2de_user","schema_owner":"aoe2de_user","tables":11,"sequences":11,"triggers":0,
  "security_definer_triggers":0,"views":0,
  "newly_included":("trophy_payouts",)}
}
SAFE_ID=re.compile(r"[a-z_][a-z0-9_]{0,62}\Z")
MAX_BYTES=180000
class Hold(ValueError):pass
def need(ok,reason):
 if not ok:raise Hold(reason)
def query(db):
 need(db in EXPECTED,"DATABASE_NOT_ALLOWLISTED")
 owner=EXPECTED[db]["owner"]
 return f"""
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;
WITH f AS (
 SELECT c.oid,c.relname,c.relowner FROM pg_catalog.pg_class c
 JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
 WHERE n.nspname='public' AND c.relkind IN ('r','p')
 AND c.relname ~* '{PATTERN}'
),
lines AS (
 SELECT 'META|'||current_database()||'|'||pg_get_userbyid(d.datdba)||'|'||
  (SELECT pg_get_userbyid(nspowner) FROM pg_catalog.pg_namespace WHERE nspname='public')||'|'||
  has_database_privilege('{owner}',current_database(),'CREATE')::integer||'|'||
  has_schema_privilege('{owner}','public','CREATE')::integer AS line
 FROM pg_catalog.pg_database d WHERE d.datname=current_database()
 UNION ALL
 SELECT 'TABLE|'||f.relname||'|'||pg_get_userbyid(f.relowner) FROM f
 UNION ALL
 SELECT 'EXTRA|'||f.relname FROM f WHERE f.relname !~* '{OLD_PATTERN}'
 UNION ALL
 SELECT DISTINCT 'SEQUENCE|'||sn.nspname||'.'||sc.relname||'|'||
   pg_get_userbyid(sc.relowner)||'|'||f.relname
 FROM pg_catalog.pg_class sc
 JOIN pg_catalog.pg_namespace sn ON sn.oid=sc.relnamespace
 JOIN pg_catalog.pg_depend dep ON dep.objid=sc.oid AND dep.deptype IN ('a','i')
 JOIN f ON f.oid=dep.refobjid WHERE sc.relkind='S'
 UNION ALL
 SELECT 'TRIGGER|'||f.relname||'|'||t.tgname||'|'||
  pn.nspname||'.'||p.proname||'|'||pg_get_userbyid(p.proowner)||'|'||
  p.prosecdef::integer
 FROM pg_catalog.pg_trigger t
 JOIN f ON f.oid=t.tgrelid
 JOIN pg_catalog.pg_proc p ON p.oid=t.tgfoid
 JOIN pg_catalog.pg_namespace pn ON pn.oid=p.pronamespace
 WHERE NOT t.tgisinternal
 UNION ALL
 SELECT DISTINCT 'VIEW|'||vn.nspname||'.'||v.relname||'|'||
   pg_get_userbyid(v.relowner)
 FROM pg_catalog.pg_depend dep
 JOIN f ON f.oid=dep.refobjid
 JOIN pg_catalog.pg_rewrite rw ON rw.oid=dep.objid
 JOIN pg_catalog.pg_class v ON v.oid=rw.ev_class
 JOIN pg_catalog.pg_namespace vn ON vn.oid=v.relnamespace
 WHERE v.relkind IN ('v','m')
)
SELECT line FROM lines ORDER BY line;
ROLLBACK;
"""
def parse(raw,db):
 need(db in EXPECTED and isinstance(raw,str) and 0<len(raw.encode())<=MAX_BYTES,
      "UNBOUNDED_OR_WRONG_DATABASE_RESULT")
 x=EXPECTED[db]
 entries={"META":[],"TABLE":[],"EXTRA":[],"SEQUENCE":[],"TRIGGER":[],"VIEW":[]}
 for line in raw.strip().splitlines():
  parts=line.split("|");k=parts[0]
  lengths={"META":6,"TABLE":3,"EXTRA":2,"SEQUENCE":4,"TRIGGER":6,"VIEW":3}
  need(k in lengths and len(parts)==lengths[k],"UNEXPECTED_CATALOG_ROW")
  for idx,p in enumerate(parts[1:]):
   if (k=="META" and idx in (3,4)) or (k=="TRIGGER" and idx==4):
    need(p in ("0","1"),"INVALID_CATALOG_FLAG")
    continue
   need(all(SAFE_ID.fullmatch(v) for v in p.split(".")),"UNSAFE_CATALOG_IDENTIFIER")
  entries[k].append(tuple(parts[1:]))
 need(len(entries["META"])==1,"MISSING_DATABASE_META")
 meta=entries["META"][0]
 need(meta[0]==db and meta[1]==x["owner"] and
      meta[2]==x["schema_owner"] and meta[3]=="1" and meta[4]=="1",
      "LEGACY_OWNER_OR_SCHEMA_PRIVILEGE_DRIFT")
 need(len(entries["TABLE"])==x["tables"],"EXPANDED_FINANCE_TABLE_COUNT_DRIFT")
 need(len(entries["SEQUENCE"])==x["sequences"],"ATTACHED_SEQUENCES_DRIFT")
 need(len(entries["TRIGGER"])==x["triggers"],"TRIGGER_COUNT_DRIFT")
 need(len(entries["VIEW"])==x["views"],"DEPENDENT_VIEWS_DRIFT")
 names={name for name,owner in entries["TABLE"]}
 need(len(names)==x["tables"],"DUPLICATE_TABLES")
 need(all(re.search(PATTERN,name,re.IGNORECASE) for name in names),
      "UNREVIEWED_FINANCE_TABLE_NAME")
 need({name for name in names if not re.search(OLD_PATTERN,name,re.IGNORECASE)}
      ==set(x["newly_included"]),"OMITTED_PAYOUT_CATALOG_INCONSISTENT")
 need(all(o==x["owner"] for _,o in entries["TABLE"]),
      "FINANCE_TABLE_OWNER_CHANGED")
 extras=tuple(sorted(v[0] for v in entries["EXTRA"]))
 need(extras==tuple(sorted(x["newly_included"])),"MISSING_OR_UNREVIEWED_PAYOUT_TRANSFER_TABLE")
 need(len({tuple(row) for row in entries["SEQUENCE"]})==x["sequences"],
      "DUPLICATE_SEQUENCE_MAPPING")
 need(all(row[1]==x["owner"] for row in entries["SEQUENCE"]),
      "SEQUENCE_OWNER_CHANGED")
 need(all(row[2] in names for row in entries["SEQUENCE"]),
      "ATTACHED_SEQUENCE_PARENT_OUTSIDE_FINANCE_UNIVERSE")
 need(all(row[0] in names for row in entries["TRIGGER"]),
      "TRIGGER_PARENT_OUTSIDE_FINANCE_UNIVERSE")
 need(sum(t[4]=="1" for t in entries["TRIGGER"])==x["security_definer_triggers"],
      "SECURITY_DEFINER_TRIGGER_DRIFT")
 need(len({tuple(row) for row in entries["TRIGGER"]})==x["triggers"],
      "DUPLICATE_TRIGGERS")
 need(len({tuple(row) for row in entries["VIEW"]})==x["views"],"DUPLICATE_VIEWS")
 return {
   "database":db,"database_owner":meta[1],"schema_owner":meta[2],
   "legacy_can_create_database_objects":meta[3]=="1",
   "legacy_can_create_public_objects":meta[4]=="1",
   "finance_related_tables":len(entries["TABLE"]),
   "attached_sequences":len(entries["SEQUENCE"]),
   "external_triggers":len(entries["TRIGGER"]),
   "security_definer_triggers":sum(t[4]=="1" for t in entries["TRIGGER"]),
   "dependent_views":len(entries["VIEW"]),
   "newly_included_tables":list(extras),
   "all_finance_related_relations_legacy_owned":True
 }
def observe(db):
 need(os.geteuid()==0,"ROOT_REQUIRED_FOR_LOCAL_READONLY_CATALOG")
 p=subprocess.run(
  ["runuser","-u","postgres","--","psql","-X","-qAt","-v","ON_ERROR_STOP=1",
   "-d",db,"-c",query(db)],capture_output=True,text=True,timeout=22)
 need(p.returncode==0 and not p.stderr.strip(),"POSTGRES_READONLY_QUERY_FAILED")
 return parse(p.stdout,db)
def main():
 try:
  data={name:observe(name) for name in EXPECTED}
  result={
   "schema":SCHEMA,"observed_at_utc":datetime.now(timezone.utc).isoformat(),
   "status":"HOLD_C03_EXPANDED_PAYOUT_TRANSFER_UNIVERSE_NOT_YET_FENCED",
   "database_catalog":data,"financial_pattern_heuristic_only":True,
   "app_writers_codepath_exhaustiveness_proven":False,
   "zero_unrecognized_financial_tables_proven":False,
   "live_financial_owners_still_have_create":True,
   "neutral_owner_migration_authorized":False,
   "coordinated_offhost_backup_authorized":False,
   "formal_c03_c06_c07_accepted":False,
   "funded_release_authorized":False,
  }
  result["catalog_sha256"]=hashlib.sha256(json.dumps(data,sort_keys=True,
      separators=(",",":")).encode()).hexdigest()
  print(json.dumps(result,sort_keys=True,indent=2))
  return 3
 except (Hold,ValueError,UnicodeError,subprocess.SubprocessError,OSError) as e:
  print(json.dumps({"schema":SCHEMA,"status":"STOP","reason":str(e)[:130],
                   "funded_release_authorized":False},sort_keys=True))
  return 2
if __name__=="__main__":sys.exit(main())

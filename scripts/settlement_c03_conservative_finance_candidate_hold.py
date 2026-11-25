#!/usr/bin/env python3
"""C03 read-only candidate union: naming OR semantic money-bearing columns.

This is a strictly HOLD-only finance writer risk inventory, *not* a complete
finance data-flow classification, permission migration, or solvency proof.
The wider default-protect candidate intentionally includes configuration and
analytics tables until their write paths are reviewed independently.
"""
from __future__ import annotations
from datetime import datetime, timezone
import hashlib
import json
import os
import re
import subprocess
import sys

SCHEMA="wolo.c03.conservative-name-semantic-finance-writer-candidate-hold.v1"
NAME="(wolo|bet|wager|settle|claim|escrow|refund|reward|stake|treasury|wallet|founder|bonus|payout|transfer)"
SEMANTIC="(amount.*wolo|wolo.*amount|tx_hash|transaction_hash|recipient_address|owner_address|escrow|payment|payout|withdraw|deposit|balance|stake|reward)"
EXPECTED={
 "aoe2hd_db": {"role":"aoe2hd_user","all":54,"name":30,"semantic_only":24,
               "sequences":52,"triggers":23,"views":9,"security_definers":0},
 "aoe2de_db": {"role":"aoe2de_user","all":20,"name":11,"semantic_only":9,
               "sequences":20,"triggers":0,"views":0,"security_definers":0}
}
SAFE=re.compile(r"[a-z_][a-z0-9_]{0,62}\Z")
class Hold(ValueError):pass
def need(v,k):
    if not v: raise Hold(k)
def query(db):
    need(db in EXPECTED,"DATABASE_NOT_ALLOWLISTED")
    return f"""
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;
WITH raw AS (
 SELECT c.oid,c.relname,c.relowner
 FROM pg_catalog.pg_class c
 JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
 WHERE n.nspname='public' AND c.relkind IN ('r','p')
), semantic AS (
 SELECT DISTINCT raw.oid
 FROM raw JOIN pg_catalog.pg_attribute a ON a.attrelid=raw.oid
 WHERE a.attnum>0 AND NOT a.attisdropped
 AND a.attname ~* '{SEMANTIC}'
), chosen AS (
 SELECT raw.oid,raw.relname,raw.relowner,
  (raw.relname ~* '{NAME}') AS name_match,
  (raw.oid IN (SELECT oid FROM semantic)) AS semantic_match
 FROM raw
 WHERE raw.relname ~* '{NAME}' OR raw.oid IN (SELECT oid FROM semantic)
), chosen_seq AS (
 SELECT DISTINCT s.oid FROM pg_catalog.pg_class s
 JOIN pg_catalog.pg_depend d ON d.objid=s.oid AND d.deptype IN ('a','i')
 JOIN chosen c ON c.oid=d.refobjid WHERE s.relkind='S'
), chosen_trig AS (
 SELECT t.oid,p.prosecdef FROM pg_catalog.pg_trigger t
 JOIN chosen c ON c.oid=t.tgrelid JOIN pg_catalog.pg_proc p ON p.oid=t.tgfoid
 WHERE NOT t.tgisinternal
), chosen_view AS (
 SELECT DISTINCT v.oid FROM pg_catalog.pg_depend d
 JOIN chosen c ON c.oid=d.refobjid
 JOIN pg_catalog.pg_rewrite r ON r.oid=d.objid
 JOIN pg_catalog.pg_class v ON v.oid=r.ev_class WHERE v.relkind IN ('v','m')
), lines AS (
 SELECT 'META|'||current_database()||'|'||pg_get_userbyid(d.datdba)||'|'||
 has_database_privilege(pg_get_userbyid(d.datdba),current_database(),'CREATE')::integer||'|'||
 has_schema_privilege(pg_get_userbyid(d.datdba),'public','CREATE')::integer AS line
 FROM pg_catalog.pg_database d WHERE d.datname=current_database()
 UNION ALL
 SELECT 'TABLE|'||relname||'|'||pg_get_userbyid(relowner)||'|'||
 name_match::integer||'|'||semantic_match::integer FROM chosen
 UNION ALL SELECT 'COUNT|sequences|'||count(*) FROM chosen_seq
 UNION ALL SELECT 'COUNT|triggers|'||count(*) FROM chosen_trig
 UNION ALL SELECT 'COUNT|views|'||count(*) FROM chosen_view
 UNION ALL SELECT 'COUNT|security_definers|'||count(*) FROM chosen_trig WHERE prosecdef
)
SELECT line FROM lines ORDER BY line;
ROLLBACK;
"""
def parse(raw,db):
    need(db in EXPECTED and isinstance(raw,str)
         and 0<len(raw.encode())<=64000,"INVALID_READONLY_CATALOG_RESPONSE")
    e=EXPECTED[db]
    meta=[];tables={};counts={}
    for row in raw.strip().splitlines():
        vals=row.split("|")
        need(vals and vals[0] in ("META","TABLE","COUNT"),"UNKNOWN_CATALOG_ROW")
        if vals[0]=="META":
            need(len(vals)==5 and not meta,"META_SHAPE_OR_DUPLICATE")
            need(all(SAFE.fullmatch(v) for v in vals[1:3])
                 and vals[3:] == ["1","1"],"OWNER_OR_CREATE_PRIVILEGE_DRIFT")
            meta.append(vals[1:3])
        elif vals[0]=="TABLE":
            need(len(vals)==5 and all(SAFE.fullmatch(v) for v in vals[1:3])
                 and vals[3] in ("0","1") and vals[4] in ("0","1"),
                 "TABLE_SHAPE")
            name,owner=vals[1:3]
            need(name not in tables,"DUPLICATE_TABLE")
            need(vals[3]=="1" or vals[4]=="1","TABLE_WITHOUT_RISK_MATCH")
            need((vals[3]=="1")==bool(re.search(NAME,name,re.IGNORECASE)),
                 "TABLE_NAME_PATTERN_FALSIFIED")
            tables[name]={"owner":owner,"name":vals[3]=="1",
                          "semantic":vals[4]=="1"}
        else:
            need(len(vals)==3 and vals[1] in
                 ("sequences","triggers","views","security_definers")
                 and vals[1] not in counts and vals[2].isdigit()
                 and len(vals[2])<8,"COUNT_SHAPE")
            counts[vals[1]]=int(vals[2])
    need(meta==[[db,e["role"]]],"DATABASE_OWNER_CHANGED")
    need(len(tables)==e["all"],"CONSERVATIVE_CANDIDATE_COUNT_DRIFT")
    need(sum(v["name"] for v in tables.values())==e["name"],
         "NAME_BASED_FINANCE_SCOPE_DRIFT")
    need(sum(not v["name"] and v["semantic"] for v in tables.values())
         ==e["semantic_only"],"SEMANTIC_EXTRA_RISK_SCOPE_DRIFT")
    need(all(v["owner"]==e["role"] for v in tables.values()),
         "LEGACY_OWNER_OF_FINANCE_CANDIDATE_CHANGED")
    need(counts=={k:e[k] for k in
         ("sequences","triggers","views","security_definers")},
         "DEPENDENCY_SCOPE_DRIFT")
    return {"database":db,"legacy_owner":e["role"],"conservative_tables":len(tables),
            "name_based_tables":e["name"],"semantic_only_tables":e["semantic_only"],
            "dependencies":counts,
            "semantic_only_names":sorted(k for k,v in tables.items() if not v["name"]),
            "protected_table_scope_exhaustive":False,"writer_fence_proven":False}
def inspect(db):
    need(os.geteuid()==0 and db in EXPECTED,"LOCAL_ROOT_FIXED_DATABASE_ONLY")
    p=subprocess.run(["runuser","-u","postgres","--","psql","-X","-qAt",
                      "-v","ON_ERROR_STOP=1","-d",db,"-c",query(db)],
                     capture_output=True,text=True,timeout=25)
    need(p.returncode==0 and not p.stderr.strip(),"READONLY_QUERY_FAILED")
    return parse(p.stdout,db)
def main():
    try:
        out={db:inspect(db) for db in EXPECTED}
        result={"schema":SCHEMA,"status":"HOLD_C03_CONSERVATIVE_FINANCE_WRITER_CANDIDATE_UNCONTAINED",
           "observed_at_utc":datetime.now(timezone.utc).isoformat(),
           "databases":out,"finance_semantics_fully_classified":False,
           "complete_app_codepath_review":False,
           "external_writer_and_signer_fence_proven":False,
           "neutral_owner_live_migration_authorized":False,
           "coherent_c06_backup_authorized":False,
           "formal_c03_c06_c07_accepted":False,"financial_release_authorized":False}
        result["catalog_sha256"]=hashlib.sha256(json.dumps(out,
              sort_keys=True,separators=(",",":")).encode()).hexdigest()
        print(json.dumps(result,sort_keys=True,indent=2))
        return 3
    except (Hold,OSError,UnicodeError,subprocess.SubprocessError) as exc:
        print(json.dumps({"schema":SCHEMA,"status":"STOP",
              "reason":str(exc)[:150],"financial_release_authorized":False},sort_keys=True))
        return 2
if __name__=="__main__":sys.exit(main())

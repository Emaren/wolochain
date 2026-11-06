#!/usr/bin/env python3
"""C03 dependency-level PostgreSQL owner audit; read-only, never release authority.

A finance table ownership change must consider owned sequences, external
triggers, dependent views, legacy database/schema ownership, and unrelated
tables. This tool discovers those dependencies; naming heuristics do NOT prove
that the financial universe is complete. Does not issue executable DDL.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
import re
import subprocess
import sys

SCHEMA = "wolo.c03.finance-dependency-observation-hold.v1"
PATTERN = "(wolo|bet|wager|settle|claim|escrow|refund|reward|stake|treasury|wallet|founder|bonus)"
DATABASES = {"aoe2hd_db": ("aoe2hd_user", 24), "aoe2de_db": ("aoe2de_user", 10)}
ID = re.compile(r"[a-z_][a-z0-9_]{0,62}\Z")
MAX_OUTPUT = 160000
MAX_OBJECTS = 3000

class Hold(ValueError):
    pass

def require(ok, reason):
    if not ok:
        raise Hold(reason)

def query(database):
    require(database in DATABASES, "DB_NOT_ALLOWLISTED")
    role, count = DATABASES[database]
    return f"""
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;
WITH
f AS (
 SELECT c.oid,c.relname,c.relowner,c.relkind,c.relrowsecurity,c.relforcerowsecurity
 FROM pg_catalog.pg_class c
 JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
 WHERE n.nspname='public' AND c.relkind IN ('r','p')
 AND c.relname ~* '{PATTERN}'
),
lines AS (
 SELECT 'META|'||current_database()||'|'||pg_get_userbyid(d.datdba)||'|'||
  (SELECT pg_get_userbyid(nspowner) FROM pg_catalog.pg_namespace WHERE nspname='public')||'|'||
  has_schema_privilege('{role}','public','CREATE')::integer AS line
 FROM pg_catalog.pg_database d WHERE d.datname=current_database()
 UNION ALL
 SELECT 'TABLE|public.'||f.relname||'|'||pg_get_userbyid(f.relowner)||'|'||
  f.relkind::text||'|'||f.relrowsecurity::integer||'|'||f.relforcerowsecurity::integer
 FROM f
 UNION ALL
 SELECT DISTINCT 'SEQUENCE|'||ns.nspname||'.'||seq.relname||'|'||
  pg_get_userbyid(seq.relowner)||'|'||f.relname
 FROM pg_catalog.pg_class seq
 JOIN pg_catalog.pg_namespace ns ON ns.oid=seq.relnamespace
 JOIN pg_catalog.pg_depend dep ON dep.objid=seq.oid AND dep.deptype IN ('a','i')
 JOIN f ON f.oid=dep.refobjid
 WHERE seq.relkind='S'
 UNION ALL
 SELECT 'TRIGGER|public.'||f.relname||'|'||t.tgname||'|'||
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
 UNION ALL
 SELECT 'NONFINANCE_OWNER_COUNT|'||count(*)
 FROM pg_catalog.pg_class c
 JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
 WHERE n.nspname='public' AND c.relkind IN ('r','p','S','v','m')
 AND pg_get_userbyid(c.relowner)='{role}'
 AND c.relname !~* '{PATTERN}'
)
SELECT line FROM lines ORDER BY line;
ROLLBACK;
"""

def parse(raw, database):
    require(database in DATABASES and type(raw) is str and
            0 < len(raw.encode()) <= MAX_OUTPUT, "QUERY_OUTPUT_UNBOUNDED")
    rows = raw.strip().splitlines()
    require(len(rows) <= MAX_OBJECTS and len(rows) == len(set(rows)),
            "DUPLICATE_OR_TOO_MANY_DEPENDENCIES")
    result = {"meta": [], "tables": [], "sequences": [],
              "triggers": [], "views": [], "nonfinanceOwnerCount": []}
    for row in rows:
        cols = row.split("|")
        kind = cols[0]
        lengths = {"META":5,"TABLE":6,"SEQUENCE":4,"TRIGGER":6,
                   "VIEW":3,"NONFINANCE_OWNER_COUNT":2}
        require(kind in lengths and len(cols)==lengths[kind], "CATALOG_SHAPE_DRIFT")
        if kind=="META":
            require(cols[1]==database and all(ID.fullmatch(x) for x in cols[1:4])
                    and cols[4] in ("0","1"), "DATABASE_IDENTITY_DRIFT")
            result["meta"].append(cols[1:])
        elif kind=="NONFINANCE_OWNER_COUNT":
            require(cols[1].isdigit() and int(cols[1]) <= MAX_OBJECTS,
                    "UNRELATED_OBJECT_COUNT_INVALID")
            result["nonfinanceOwnerCount"].append(int(cols[1]))
        else:
            for value in cols[1:]:
                if kind=="TABLE" and value in ("r","p","0","1"):continue
                if kind=="TRIGGER" and value in ("0","1"):continue
                require(all(ID.fullmatch(x) for x in value.split(".")),
                        "UNSAFE_CATALOG_IDENTIFIER")
            result[{"TABLE":"tables","SEQUENCE":"sequences",
                    "TRIGGER":"triggers","VIEW":"views"}[kind]].append(cols[1:])
    expected_role, expected_tables = DATABASES[database]
    require(len(result["meta"])==1 and len(result["nonfinanceOwnerCount"])==1,
            "META_OR_UNRELATED_CENSUS_MISSING")
    require(result["meta"][0][1]==expected_role and
            result["meta"][0][3]=="1" and len(result["tables"])==expected_tables,
            "LEGACY_OWNER_OR_FINANCE_CENSUS_CHANGED")
    require(all(t[1]==expected_role for t in result["tables"]),
            "FINANCE_TABLE_OWNER_CHANGED")
    return result

def inspect(database):
    require(os.geteuid()==0, "ROOT_READ_ONLY_REQUIRED")
    statement=query(database)
    p=subprocess.run(["runuser","-u","postgres","--","psql","-X","-qAt",
                      "-v","ON_ERROR_STOP=1","-d",database,"-c",statement],
                     capture_output=True,text=True,timeout=18,check=False)
    require(p.returncode==0 and not p.stderr.strip() and
            len(p.stdout.encode())<=MAX_OUTPUT, "POSTGRES_CATALOG_UNAVAILABLE")
    return parse(p.stdout,database)

def main():
    try:
        db={name:inspect(name) for name in DATABASES}
        result={"schema":SCHEMA,"observedUtc":datetime.now(timezone.utc).isoformat(),
          "status":"HOLD","financeTableNamesHeuristicOnly":True,
          "completeFinancialUniverseProven":False,
          "migrationDdlAuthorized":False,"backupAuthorized":False,
          "financialReleaseAuthorized":False,"databaseCatalog":db,
          "dependencyCounts":{name:{"tables":len(v["tables"]),
            "attachedSequences":len(v["sequences"]),
            "externalTriggers":len(v["triggers"]),
            "dependentViews":len(v["views"]),
            "otherLegacyOwnedPublicRelations":v["nonfinanceOwnerCount"][0]}
            for name,v in db.items()}}
        result["catalogSha256"]=hashlib.sha256(json.dumps(db,sort_keys=True,
          separators=(",",":")).encode()).hexdigest()
    except (Hold,OSError,UnicodeError,subprocess.SubprocessError) as exc:
        reason=str(exc) if isinstance(exc,Hold) else "CATALOG_INSPECTION_UNAVAILABLE"
        print(json.dumps({"schema":SCHEMA,"status":"STOP","reason":reason,
              "financialReleaseAuthorized":False},sort_keys=True))
        return 2
    print(json.dumps(result,sort_keys=True,indent=2))
    return 3

if __name__=="__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""C03: read-only PostgreSQL owner/effective-writer boundary audit.

A REVOKE from the finance-table owning legacy role is not a writer fence.
Count owner, database, schema, role-membership and DML bypasses across user
schemas. This source cannot authorize quiescence, migration or a payment.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
import re
import subprocess
import sys

SCHEMA = "wolo.c03.legacy-db-owner-boundary-hold.v1"
TARGETS = {"aoe2hd_db": "aoe2hd_user", "aoe2de_db": "aoe2de_user"}
INT = re.compile(r"[0-9]{1,10}\Z")
MAX_STDOUT = 4096
FINANCE = r"(wolo|bet|wager|settle|claim|escrow|refund|reward|stake|treasury|wallet|founder|bonus)"
FIELDS = (
    "role_exists", "finance_named_relations", "finance_relations_owned",
    "finance_relations_dml_capable", "nonpublic_finance_relations",
    "legacy_database_owner", "legacy_public_schema_owner_or_member",
    "legacy_can_create_in_public", "superuser", "inherit", "bypass_rls",
    "active_legacy_db_sessions", "member_of_other_finance_owner_roles",
)

class AuditHold(ValueError):
    pass

def require(condition: bool, reason: str) -> None:
    if not condition:
        raise AuditHold(reason)

def query(database: str) -> str:
    require(database in TARGETS, "DATABASE_NOT_ALLOWLISTED")
    role = TARGETS[database]
    # Values are compile-time allowlisted identifiers, never user input.
    return f"""BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;
WITH legacy AS (SELECT to_regrole('{role}')::oid AS oid),
 finance AS (
   SELECT c.oid,c.relowner,n.nspname
   FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
   WHERE n.nspname NOT LIKE 'pg\\_%' ESCAPE '\\'
    AND n.nspname <> 'information_schema'
    AND c.relkind IN ('r','p','f','v')
    AND c.relname ~* '{FINANCE}'
 )
SELECT (l.oid IS NOT NULL)::integer,
 (SELECT count(*) FROM finance),
 (SELECT count(*) FROM finance f WHERE f.relowner=l.oid),
 (SELECT count(*) FROM finance f WHERE
   COALESCE(has_table_privilege(l.oid,f.oid,'INSERT,UPDATE,DELETE,TRUNCATE'),false) OR
   COALESCE(has_any_column_privilege(l.oid,f.oid,'INSERT,UPDATE'),false)),
 (SELECT count(*) FROM finance f WHERE f.nspname <> 'public'),
 (SELECT (d.datdba=l.oid)::integer FROM pg_catalog.pg_database d WHERE d.datname=current_database()),
 (SELECT COALESCE((n.nspowner=l.oid OR pg_has_role(l.oid,n.nspowner,'USAGE'))::integer,0)
    FROM pg_catalog.pg_namespace n WHERE n.nspname='public'),
 COALESCE(has_schema_privilege(l.oid,'public','CREATE')::integer,0),
 COALESCE((SELECT r.rolsuper::integer FROM pg_catalog.pg_roles r WHERE r.oid=l.oid),0),
 COALESCE((SELECT r.rolinherit::integer FROM pg_catalog.pg_roles r WHERE r.oid=l.oid),0),
 COALESCE((SELECT r.rolbypassrls::integer FROM pg_catalog.pg_roles r WHERE r.oid=l.oid),0),
 (SELECT count(*) FROM pg_catalog.pg_stat_activity s WHERE s.datname=current_database() AND s.usesysid=l.oid),
 (SELECT count(*) FROM (SELECT DISTINCT f.relowner FROM finance f WHERE f.relowner<>l.oid) owners
   WHERE COALESCE(pg_has_role(l.oid,owners.relowner,'MEMBER'),false))
FROM legacy l;
ROLLBACK;"""

def parse(raw: str, database: str) -> dict:
    require(database in TARGETS and isinstance(raw,str) and
            len(raw.encode("utf-8")) <= MAX_STDOUT, "OWNER_PROBE_OUTPUT_INVALID")
    lines = raw.strip().splitlines()
    require(len(lines) == 1, "OWNER_PROBE_CARDINALITY")
    pieces = lines[0].split("|")
    require(len(pieces) == len(FIELDS) and all(INT.fullmatch(p) for p in pieces),
            "OWNER_PROBE_SCHEMA_DRIFT")
    values = [int(v) for v in pieces]
    (role_exists, total, owned, dml, nonpublic, dbowner, schemaowner, createsch,
     superuser, inherit, bypass, sessions, member_owners) = values
    require(role_exists == 1 and 0 < total < 100000 and
            0 <= owned <= total and 0 <= dml <= total and 0 <= nonpublic <= total and
            all(v in (0,1) for v in (dbowner,schemaowner,createsch,superuser,inherit,bypass)) and
            0 <= sessions < 10000 and 0 <= member_owners <= total,
            "OWNER_PROBE_RESULT_OUT_OF_BOUNDS")
    result = dict(zip(FIELDS, values))
    result["legacy_role"] = TARGETS[database]
    result["implicit_owner_or_schema_bypass"] = bool(
        owned or dbowner or schemaowner or createsch or superuser or member_owners)
    result["finance_writer_capability"] = bool(
        dml or result["implicit_owner_or_schema_bypass"])
    return result

def inspect(database: str) -> dict:
    require(os.geteuid() == 0 and database in TARGETS, "LOCAL_ROOT_AND_ALLOWLIST_REQUIRED")
    proc = subprocess.run(
        ["runuser","-u","postgres","--","psql","-X","-qAt","-F","|",
         "-v","ON_ERROR_STOP=1","-d",database,"-c",query(database)],
        capture_output=True,text=True,timeout=15,check=False,
    )
    require(proc.returncode == 0 and not proc.stderr.strip() and
            len(proc.stdout.encode("utf-8")) <= MAX_STDOUT,
            "OWNER_PROBE_LOCAL_PG_UNAVAILABLE")
    return parse(proc.stdout,database)

def classify(observations: dict) -> dict:
    require(set(observations) == set(TARGETS) and
            all(observations[db].get("legacy_role") == role for db,role in TARGETS.items()),
            "DB_OWNER_BOTH_DATABASES_REQUIRED")
    return {
        "schema": SCHEMA,
        "observed_utc": datetime.now(timezone.utc).isoformat(),
        "status": "HOLD",
        "databases": observations,
        "owner_confers_implicit_privilege": True,
        "revoking_owner_dml_is_not_a_valid_fence": True,
        "total_producer_and_db_write_fence_proven": False,
        "database_ownership_changed": False,
        "live_grants_changed": False,
        "backup_authorized": False,
        "financial_release_authorized": False,
    }

def main() -> int:
    try:
        report = classify({db: inspect(db) for db in TARGETS})
    except (AuditHold, OSError, subprocess.SubprocessError, UnicodeError) as exc:
        code = str(exc) if isinstance(exc, AuditHold) else "OWNER_PROBE_UNAVAILABLE"
        print(json.dumps({"schema":SCHEMA,"status":"STOP","reason":code,
                          "financial_release_authorized":False},sort_keys=True))
        return 2
    print(json.dumps(report,sort_keys=True,indent=2))
    return 3

if __name__ == "__main__":
    sys.exit(main())

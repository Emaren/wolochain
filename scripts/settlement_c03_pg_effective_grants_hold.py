#!/usr/bin/env python3
"""C03 read-only PostgreSQL effective finance-write capability census.

For HD and DE, check the privileges of real legacy and restricted roles,
including inherited table/column privileges and selected SECURITY DEFINER
exposure. This is an observation, never a writer fence or financial permit.
Only local root/postgres catalog reads; no SQL or systemd mutation.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
import re
import subprocess
import sys

SCHEMA = "wolo.c03.effective-postgres-finance-capability-hold.v1"
DATABASES = ("aoe2hd_db", "aoe2de_db")
ROLES = ("aoe2hd_user", "aoe2de_user", "aoe2war_web_prod",
         "aoe2war_auth_owner")
REQUIRED_LEGACY = {"aoe2hd_db": "aoe2hd_user", "aoe2de_db": "aoe2de_user"}
INT = re.compile(r"\d{1,12}\Z")
MAX_RESPONSE = 32_768
FINANCE_PATTERN = "(wolo|bet|wager|settle|claim|escrow|refund|reward|stake|treasury|wallet|founder|bonus)"
SQL = """BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;
WITH roles(name) AS (
 VALUES ('aoe2hd_user'), ('aoe2de_user'), ('aoe2war_web_prod'),
        ('aoe2war_auth_owner')
), resolved AS (
 SELECT name, to_regrole(name) AS oid FROM roles
), rels AS (
 SELECT c.oid, c.relname ~* '""" + FINANCE_PATTERN + """' AS finance
 FROM pg_catalog.pg_class c
 JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
 WHERE n.nspname='public' AND c.relkind IN ('r','p')
)
SELECT r.name, (r.oid IS NOT NULL)::integer,
 (SELECT count(*) FROM rels),
 (SELECT count(*) FROM rels c WHERE c.finance),
 (SELECT count(*) FROM rels c WHERE
    COALESCE(has_table_privilege(r.oid,c.oid,'INSERT,UPDATE,DELETE,TRUNCATE'),false)
    OR COALESCE(has_any_column_privilege(r.oid,c.oid,'INSERT,UPDATE'),false)),
 (SELECT count(*) FROM rels c WHERE c.finance AND (
    COALESCE(has_table_privilege(r.oid,c.oid,'INSERT,UPDATE,DELETE,TRUNCATE'),false)
    OR COALESCE(has_any_column_privilege(r.oid,c.oid,'INSERT,UPDATE'),false))),
 (SELECT count(*) FROM pg_catalog.pg_proc p
  JOIN pg_catalog.pg_namespace n ON n.oid=p.pronamespace
  WHERE p.prosecdef AND n.nspname IN ('public','aoe2war_auth_v1')
   AND COALESCE(has_function_privilege(r.oid,p.oid,'EXECUTE'),false)),
 COALESCE((SELECT rolsuper::integer FROM pg_catalog.pg_roles WHERE oid=r.oid),0),
 COALESCE((SELECT rolbypassrls::integer FROM pg_catalog.pg_roles WHERE oid=r.oid),0)
FROM resolved r ORDER BY r.name;
ROLLBACK;
"""


class Hold(ValueError):
    pass


def require(ok: bool, reason: str) -> None:
    if not ok:
        raise Hold(reason)


def parse_rows(raw: str, database: str) -> dict:
    require(database in DATABASES and isinstance(raw,str) and
            len(raw.encode("utf-8")) <= MAX_RESPONSE, "INVALID_POSTGRES_OBSERVATION")
    out = {}
    for line in raw.splitlines():
        fields = line.split("|")
        require(len(fields) == 9 and fields[0] in ROLES and
                fields[0] not in out and all(INT.fullmatch(n) for n in fields[1:]),
                "ROLE_GRANTS_REPLY_DRIFT")
        values = [int(x) for x in fields[1:]]
        exists,total,finance_total,writes,finance_writes,definers,superuser,bypass = values
        require(exists in (0,1) and superuser in (0,1) and bypass in (0,1)
                and 0 < total < 100_000 and 0 <= finance_total <= total
                and 0 <= writes <= total and 0 <= finance_writes <= finance_total
                and 0 <= definers < 100_000, "GRANTS_RESULT_OUT_OF_BOUNDS")
        require(exists == 1 or (writes == 0 and finance_writes == 0 and
                definers == 0 and superuser == 0 and bypass == 0),
                "ABSENT_ROLE_HAS_RIGHTS")
        out[fields[0]] = {
            "role_exists":bool(exists), "public_relations":total,
            "finance_named_relations":finance_total,
            "public_write_capable_relations":writes,
            "finance_write_capable_relations":finance_writes,
            "selected_security_definer_functions_executable":definers,
            "superuser":bool(superuser), "bypass_rls":bool(bypass),
        }
    require(set(out) == set(ROLES) and
            out[REQUIRED_LEGACY[database]]["role_exists"],
            "REQUIRED_ROLE_INVENTORY_INCOMPLETE")
    return out


def inspect(database: str) -> dict:
    require(os.geteuid() == 0 and database in DATABASES,
            "LOCAL_POSTGRES_ADMIN_REQUIRED")
    p = subprocess.run(
        ["runuser","-u","postgres","--","psql","-X","-qAt",
         "-F","|","-v","ON_ERROR_STOP=1","-d",database,"-c",SQL],
        text=True, capture_output=True, timeout=16, check=False,
    )
    require(p.returncode == 0 and not p.stderr.strip() and
            len(p.stdout.encode("utf-8")) <= MAX_RESPONSE,
            "POSTGRES_READ_ONLY_CENSUS_UNAVAILABLE")
    return parse_rows(p.stdout, database)


def classify(hd: dict, de: dict) -> dict:
    require(set(hd) == set(ROLES) and set(de) == set(ROLES),
            "DB_ROLE_SET_INCOMPLETE")
    return {
        "schema":SCHEMA,
        "observed_utc":datetime.now(timezone.utc).isoformat(),
        "status":"HOLD",
        "databases":{"aoe2hd_db":hd,"aoe2de_db":de},
        "legacy_hd_finance_writer_capable":hd["aoe2hd_user"]["finance_write_capable_relations"] > 0,
        "legacy_de_finance_writer_capable":de["aoe2de_user"]["finance_write_capable_relations"] > 0,
        "selected_security_definer_audited_only":True,
        "all_schemas_roles_and_bypass_paths_certified":False,
        "cron_remote_sessions_and_reconnect_fenced":False,
        "financial_writers_quiesced":False,
        "database_permissions_changed":False,
        "backup_or_restore_authorized":False,
        "funded_release_authorized":False,
    }


def main() -> int:
    try:
        result=classify(inspect("aoe2hd_db"),inspect("aoe2de_db"))
    except (Hold, OSError, subprocess.SubprocessError, UnicodeError) as e:
        why=str(e) if isinstance(e,Hold) else "READ_ONLY_OBSERVATION_UNAVAILABLE"
        print(json.dumps({"schema":SCHEMA,"status":"STOP","reason":why,
                          "funded_release_authorized":False},sort_keys=True))
        return 2
    print(json.dumps(result,sort_keys=True,indent=2))
    return 3


if __name__=="__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""C03: exact HD auth-owner capability review. READ ONLY, NEVER a finance permit.

The restricted R25 Steam login requires three narrowly scoped SECURITY DEFINER
helpers. A financial ownership migration must not confuse this auth exception
with general finance access or overlook newly added definer/trigger routes.

Observe the COMPLETE non-system definer catalog, auth-owner table privileges,
auth-owner public.users writable columns, table triggers and role escalation.
The three function *bodies* are pinned by SHA256(pg_get_functiondef) from the
owner-reviewed physical HD catalog, not merely by mutable function names.
Any change is STOP, and a successful observation remains a financial HOLD.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
import re
import subprocess
import sys

SCHEMA = "wolo.c03.hd-auth-definer-exact-capability-hold.v1"
DATABASE = "aoe2hd_db"
EXPECTED_FUNCTIONS = {
    "aoe2war_auth_v1.complete_steam_login": "dcb05f3694ac25600a3765b2a1e1858f0d1c5ffcbae29101a54553c65e9b719b",
    "aoe2war_auth_v1.read_user": "53816fe020df6cdc5e5d969b74c1d0e16490203c5f078b24419ea8eb95e40d84",
    "aoe2war_auth_v1.touch_session": "50a48dd1c628a47fec75ea161203871f27b2fa3f56608279e515b4733b05c1cc",
}
EXPECTED_WRITABLE_RELATIONS = {"aoe2war_auth_v1.steam_nonces", "public.users"}
EXPECTED_DELETE_TRUNCATE = {("aoe2war_auth_v1.steam_nonces", "1", "1")}
EXPECTED_USER_COLUMNS = {
    "email": ("0", "1"),
    "in_game_name": ("0", "1"),
    "last_seen": ("1", "1"),
    "steam_id": ("1", "1"),
    "steam_persona_name": ("1", "1"),
    "uid": ("1", "0"),
    "verification_level": ("1", "1"),
    "verification_method": ("1", "1"),
}
EXPECTED_ROLES = {"aoe2war_auth_owner", "aoe2war_web_prod"}
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
IDENT = re.compile(r"[a-z_][a-z0-9_]{0,62}(?:\.[a-z_][a-z0-9_]{0,62})?\Z")
MAX_OUTPUT_BYTES = 32768
SQL = """
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;
SELECT 'F|'||n.nspname||'.'||p.proname||'|'||
  pg_get_userbyid(p.proowner)||'|'||
  COALESCE(array_to_string(p.proconfig,';'),'')||'|'||
  pg_catalog.encode(pg_catalog.sha256(
    pg_catalog.convert_to(pg_get_functiondef(p.oid),'UTF8')),'hex')||'|'||
  pg_catalog.has_function_privilege('aoe2war_web_prod',p.oid,'EXECUTE')::int
FROM pg_catalog.pg_proc p
JOIN pg_catalog.pg_namespace n ON n.oid=p.pronamespace
WHERE p.prosecdef AND n.nspname !~ '^pg_'
  AND n.nspname <> 'information_schema'
ORDER BY 1;
SELECT 'W|'||n.nspname||'.'||c.relname
FROM pg_catalog.pg_class c
JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
WHERE n.nspname !~ '^pg_' AND n.nspname <> 'information_schema'
  AND c.relkind IN ('r','p') AND
  (pg_catalog.has_table_privilege('aoe2war_auth_owner',c.oid,'INSERT,UPDATE,DELETE,TRUNCATE')
  OR pg_catalog.has_any_column_privilege('aoe2war_auth_owner',c.oid,'INSERT,UPDATE'))
ORDER BY 1;
SELECT 'D|'||n.nspname||'.'||c.relname||'|'||
  pg_catalog.has_table_privilege('aoe2war_auth_owner',c.oid,'DELETE')::int||'|'||
  pg_catalog.has_table_privilege('aoe2war_auth_owner',c.oid,'TRUNCATE')::int
FROM pg_catalog.pg_class c
JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
WHERE n.nspname !~ '^pg_' AND n.nspname <> 'information_schema'
  AND c.relkind IN ('r','p') AND
  (pg_catalog.has_table_privilege('aoe2war_auth_owner',c.oid,'DELETE')
  OR pg_catalog.has_table_privilege('aoe2war_auth_owner',c.oid,'TRUNCATE'))
ORDER BY 1;
SELECT 'C|'||a.attname||'|'||
  pg_catalog.has_column_privilege('aoe2war_auth_owner',a.attrelid,a.attnum,'INSERT')::int||'|'||
  pg_catalog.has_column_privilege('aoe2war_auth_owner',a.attrelid,a.attnum,'UPDATE')::int
FROM pg_catalog.pg_attribute a
WHERE a.attrelid='public.users'::regclass
  AND a.attnum > 0 AND NOT a.attisdropped
  AND (pg_catalog.has_column_privilege('aoe2war_auth_owner',a.attrelid,a.attnum,'INSERT')
  OR pg_catalog.has_column_privilege('aoe2war_auth_owner',a.attrelid,a.attnum,'UPDATE'))
ORDER BY 1;
SELECT 'T|'||n.nspname||'.'||c.relname||'|'||t.tgname
FROM pg_catalog.pg_trigger t
JOIN pg_catalog.pg_class c ON c.oid=t.tgrelid
JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
WHERE NOT t.tgisinternal
  AND ((n.nspname='public' AND c.relname='users')
       OR (n.nspname='aoe2war_auth_v1' AND c.relname='steam_nonces'))
ORDER BY 1;
SELECT 'H|'||
  pg_catalog.has_schema_privilege('aoe2war_auth_owner','public','CREATE')::int||'|'||
  pg_catalog.pg_has_role('aoe2war_auth_owner','aoe2hd_user','MEMBER')::int||'|'||
  pg_catalog.pg_has_role('aoe2war_web_prod','aoe2hd_user','MEMBER')::int||'|'||
  pg_catalog.has_schema_privilege('aoe2war_web_prod','public','CREATE')::int;
SELECT 'R|'||rolname||'|'||rolsuper::int||'|'||
  rolbypassrls::int||'|'||rolcreaterole::int
FROM pg_catalog.pg_roles
WHERE rolname IN ('aoe2war_auth_owner','aoe2war_web_prod')
ORDER BY 1;
ROLLBACK;
"""


class Hold(ValueError):
    pass


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise Hold(reason)


def parse(raw: str) -> dict:
    require(isinstance(raw, str) and 0 < len(raw.encode()) <= MAX_OUTPUT_BYTES,
            "CATALOG_RESPONSE_SIZE")
    functions = {}
    relations = set()
    deletions = set()
    columns = {}
    roles = set()
    guards = []
    triggers = []
    for line in raw.splitlines():
        p = line.split("|")
        kind = p[0]
        if kind == "F":
            require(len(p) == 6 and IDENT.fullmatch(p[1]) and
                    IDENT.fullmatch(p[2]) and HEX64.fullmatch(p[4]) and
                    p[5] in ("0", "1") and p[1] not in functions,
                    "DEFINER_ROW_INVALID_OR_DUPLICATE")
            functions[p[1]] = p[2:]
        elif kind == "W":
            require(len(p) == 2 and IDENT.fullmatch(p[1]) and
                    p[1] not in relations, "WRITABLE_RELATION_ROW_INVALID")
            relations.add(p[1])
        elif kind == "D":
            require(len(p) == 4 and IDENT.fullmatch(p[1]) and
                    p[2] in ("0", "1") and p[3] in ("0", "1") and
                    (p[1], p[2], p[3]) not in deletions,
                    "DELETE_TRUNCATE_ROW_INVALID")
            deletions.add((p[1], p[2], p[3]))
        elif kind == "C":
            require(len(p) == 4 and IDENT.fullmatch(p[1]) and
                    p[2] in ("0", "1") and p[3] in ("0", "1") and
                    p[1] not in columns, "COLUMN_PRIVILEGE_ROW_INVALID")
            columns[p[1]] = (p[2], p[3])
        elif kind == "T":
            require(len(p) == 3 and IDENT.fullmatch(p[1]) and
                    IDENT.fullmatch(p[2]), "TRIGGER_ROW_INVALID")
            triggers.append((p[1], p[2]))
        elif kind == "H":
            require(len(p) == 5 and all(x in ("0", "1") for x in p[1:]),
                    "ROLE_MEMBERSHIP_ROW_INVALID")
            guards.append(p[1:])
        elif kind == "R":
            require(len(p) == 5 and p[1] in EXPECTED_ROLES and
                    p[1] not in roles and p[2:] == ["0", "0", "0"],
                    "ROLE_ESCALATION_ROW_INVALID")
            roles.add(p[1])
        else:
            raise Hold("UNKNOWN_CATALOG_RECORD")
    require(set(functions) == set(EXPECTED_FUNCTIONS),
            "UNREVIEWED_SECURITY_DEFINER_ADDED_OR_REMOVED")
    for name, expect_digest in EXPECTED_FUNCTIONS.items():
        owner, config, digest, executable = functions[name]
        require(owner == "aoe2war_auth_owner" and
                config == "search_path=pg_catalog" and
                digest == expect_digest and executable == "1",
                "AUTH_DEFINER_BODY_OWNER_PATH_OR_EXECUTE_DRIFT")
    require(relations == EXPECTED_WRITABLE_RELATIONS,
            "AUTH_OWNER_FINANCIAL_WRITE_REACHABILITY_DRIFT")
    require(deletions == EXPECTED_DELETE_TRUNCATE,
            "AUTH_OWNER_DELETE_TRUNCATE_SCOPE_DRIFT")
    require(columns == EXPECTED_USER_COLUMNS,
            "AUTH_OWNER_USER_COLUMN_PRIVILEGE_DRIFT")
    require(not triggers, "AUTH_MUTATION_TRIGGER_REACHABILITY")
    require(guards == [["0", "0", "0", "0"]] and roles == EXPECTED_ROLES,
            "AUTH_ROLE_MEMBERSHIP_OR_PUBLIC_CREATE_DRIFT")
    return {
        "schema": SCHEMA,
        "status": "HOLD_C03_GLOBAL_FINANCIAL_WRITER_FENCE_UNPROVEN",
        "observed_utc": datetime.now(timezone.utc).isoformat(),
        "auth_definer_function_sha256": {k: v[2] for k, v in sorted(functions.items())},
        "auth_owner_writable_relations": sorted(relations),
        "auth_owner_writable_user_columns": {k: list(v) for k, v in sorted(columns.items())},
        "auth_owner_delete_truncate_relations": sorted(x[0] for x in deletions),
        "auth_mutation_triggers": 0,
        "auth_role_escalation_or_public_create": False,
        "complete_non_system_definer_inventory_reviewed": True,
        "observed_auth_function_scope_only": True,
        "app_financial_writers_fenced": False,
        "preconnected_legacy_postgres_clients_fenced": False,
        "direct_chain_rpc_cli_signers_fenced": False,
        "finance_authorized": False,
        "database_mutated": False,
    }


def inspect() -> dict:
    require(os.geteuid() == 0, "ROOT_READ_ONLY_ONLY")
    p = subprocess.run(
        ["runuser", "-u", "postgres", "--", "psql", "-X", "-qAt",
         "-v", "ON_ERROR_STOP=1", "-d", DATABASE, "-c", SQL],
        capture_output=True, text=True, check=False, timeout=18,
    )
    require(p.returncode == 0 and not p.stderr.strip() and
            len(p.stdout.encode()) <= MAX_OUTPUT_BYTES,
            "CATALOG_READ_ONLY_QUERY_UNAVAILABLE")
    return parse(p.stdout)


def main() -> int:
    try:
        print(json.dumps(inspect(), sort_keys=True))
        return 3  # This is evidence for a HOLD, never a financial PASS.
    except (Hold, OSError, subprocess.SubprocessError, UnicodeError) as exc:
        reason = str(exc) if isinstance(exc, Hold) else "CATALOG_OBSERVATION_UNAVAILABLE"
        print(json.dumps({"schema": SCHEMA, "status": "STOP",
                          "reason": reason, "finance_authorized": False,
                          "database_mutated": False}, sort_keys=True))
        return 2


if __name__ == "__main__":
    sys.exit(main())

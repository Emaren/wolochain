#!/usr/bin/env python3
"""C03 cross-prove live PG privileges against source-bound connected clients.

This is a READ-ONLY, ROOT-PRIVATE, aggregate-only HOLD/STOP observer.
Two independent physical observers must be near-simultaneous. NO DDL,
client termination, service control, snapshot, payment or release permit.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys

SCHEMA = "wolo.c03.effective-grants-bound-existing-sessions-finance-hold.v1"
GRANTS_SCHEMA = "wolo.c03.effective-postgres-expanded-payout-capability-hold.v2"
SESSIONS_SCHEMA = "wolo.c03.existing-pg-client-origin-hold.v1"
ALLOWED = {
    ("aoe2hd_db", "aoe2hd_user"): {"aoe2hdbets-api.service", "aoe2hdbets-web.service"},
    ("aoe2hd_db", "aoe2war_web_prod"): {"aoe2hdbets-web-prod.service"},
    ("aoe2de_db", "aoe2de_user"): {"aoe2dewarwagers-api.service"},
}
EXPECTED_ROLES = {"aoe2hd_user", "aoe2de_user", "aoe2war_web_prod", "aoe2war_auth_owner"}
PUBLIC_TABLES = {"aoe2hd_db": 190, "aoe2de_db": 52}
LEGACY = {"aoe2hd_db": "aoe2hd_user", "aoe2de_db": "aoe2de_user"}
MAX_BYTES = 65536
SHA = re.compile(r"[0-9a-f]{64}\Z")

class Hold(ValueError):
    pass

def need(condition, reason):
    if not condition:
        raise Hold(reason)

def strict_int(value, upper):
    need(type(value) is int and 0 <= value <= upper, "C03_UNEXPECTED_COUNTER")
    return value

def timestamp(raw):
    need(type(raw) is str and len(raw) <= 40, "C03_SOURCE_TIMESTAMP_MISSING")
    try:
        time = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        raise Hold("C03_SOURCE_TIMESTAMP_INVALID") from None
    need(time.tzinfo is not None and time.utcoffset().total_seconds() == 0,
         "C03_SOURCE_TIMESTAMP_NOT_UTC")
    return time.astimezone(timezone.utc)

def private_json(path: Path, digest: str):
    need(path.is_absolute() and type(digest) is str and SHA.fullmatch(digest),
         "C03_SOURCE_ARGS_INVALID")
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        before = os.fstat(fd)
        need(stat.S_ISREG(before.st_mode) and before.st_uid == os.geteuid()
             and before.st_nlink == 1 and stat.S_IMODE(before.st_mode) == 0o600
             and 0 < before.st_size <= MAX_BYTES, "C03_PRIVATE_EVIDENCE_MODE_OR_SIZE")
        with os.fdopen(os.dup(fd), "rb") as f:
            raw = f.read(MAX_BYTES + 1)
        after = os.fstat(fd)
        need(before.st_size == after.st_size and before.st_ino == after.st_ino
             and len(raw) == before.st_size
             and hashlib.sha256(raw).hexdigest() == digest,
             "C03_PRIVATE_EVIDENCE_SOURCE_SHA_DRIFT")
        return json.loads(raw)
    finally:
        os.close(fd)

def classify(grants: dict, clients: dict, *, now=None):
    need(type(grants) is dict and type(clients) is dict, "C03_TWO_SOURCE_OBJECTS_REQUIRED")
    need(grants.get("schema") == GRANTS_SCHEMA and grants.get("status") == "HOLD"
         and clients.get("schema") == SESSIONS_SCHEMA and clients.get("status") == "HOLD",
         "C03_SOURCE_OBSERVER_SCHEMA_OR_STATUS_DRIFT")
    for flag in ("financial_writers_quiesced", "funded_release_authorized",
                 "database_permissions_changed", "all_schemas_roles_and_bypass_paths_certified"):
        need(grants.get(flag) is False, "C03_GRANTS_FALSE_FINANCE_ADMISSION")
    for flag in ("finance_writer_denial_proven", "global_c03_gate_accepted",
                 "funded_release_authorized", "production_modified",
                 "live_pg_session_termination_authorized"):
        need(clients.get(flag) is False, "C03_CLIENTS_FALSE_FINANCE_ADMISSION")
    need(clients.get("protected_3030_rollback_pg_client_proven") is True
         and clients.get("exact_socket_to_process_to_systemd_binding") is True
         and clients.get("process_population_fresh_for_this_observation_only") is True,
         "C03_CLIENT_PG_TO_UNIT_BINDING_UNVERIFIED")
    a, b = timestamp(grants.get("observed_utc")), timestamp(clients.get("observed_utc"))
    current = now if now is not None else datetime.now(timezone.utc)
    need(type(current) is datetime and current.tzinfo is not None,
         "C03_TRUSTED_UTC_CLOCK_REQUIRED")
    current = current.astimezone(timezone.utc)
    need(abs((a-b).total_seconds()) <= 120 and
         0 <= (current-a).total_seconds() <= 300 and
         0 <= (current-b).total_seconds() <= 300,
         "C03_TWO_CENSUSES_NOT_FRESH_AND_COHERENT")
    dbs = grants.get("databases")
    need(type(dbs) is dict and set(dbs) == set(PUBLIC_TABLES),
         "C03_HD_DE_GRANTS_INCOMPLETE")
    summary = {}
    for db, total in PUBLIC_TABLES.items():
        rows = dbs[db]
        need(type(rows) is dict and set(rows) == EXPECTED_ROLES, "C03_GRANT_ROLE_DRIFT")
        for role, row in rows.items():
            need(type(row) is dict and row.get("role_exists") is True,
                 "C03_REQUIRED_ROLE_MISSING")
            need(strict_int(row.get("public_relations"), 100000) == total,
                 "C03_PUBLIC_TABLE_CENSUS_CHANGED")
            writes = strict_int(row.get("public_write_capable_relations"), total)
            finance_writes = strict_int(row.get("finance_write_capable_relations"), total)
            finance_total = strict_int(row.get("finance_named_relations"), total)
            need(finance_writes <= writes and finance_writes <= finance_total,
                 "C03_GRANT_RELATION_COUNTER_CONTRADICTION")
            need(row.get("superuser") is False and row.get("bypass_rls") is False,
                 "C03_ELEVATED_ROLE_DRIFT")
            strict_int(row.get("selected_security_definer_functions_executable"), 1000)
            if role == "aoe2war_web_prod":
                need(writes == 0 and finance_writes == 0,
                     "C03_R25_RESTRICTED_ROLE_WRITE_ACCESS_REGRESSION")
            if role == "aoe2war_auth_owner":
                need(writes == (1 if db == "aoe2hd_db" else 0)
                     and finance_writes == 0,
                     "C03_NARROW_AUTH_OWNER_SCOPE_DRIFT")
        owner = rows[LEGACY[db]]
        summary[db] = {
            "total_public_tables": total,
            "legacy_owner_write_capable_tables": owner["public_write_capable_relations"],
            "legacy_owner_finance_named_write_capable_tables":
                owner["finance_write_capable_relations"],
            "modern_web_write_capable_tables": rows["aoe2war_web_prod"]["public_write_capable_relations"],
        }
    records = clients.get("records")
    need(type(records) is list and 0 < len(records) <= 80 and
         strict_int(clients.get("total_bound_existing_sessions"), 80) == len(records),
         "C03_PG_CLIENT_COUNT_INCONSISTENT")
    seen = set()
    by_service = {}
    owner_connections = 0
    for item in records:
        need(type(item) is dict, "C03_UNEXPECTED_CLIENT_RECORD")
        db, role, service = (item.get("database"), item.get("role"), item.get("source_service"))
        need((db, role) in ALLOWED and service in ALLOWED[(db, role)],
             "C03_UNREVIEWED_CLIENT_IDENTITY_OR_ORIGIN")
        key = (db, strict_int(item.get("pg_backend_pid"), 2**31-1))
        need(key[1] > 0 and key not in seen and
             item.get("finance_write_permission_denied") is False and
             item.get("safe_to_terminate") is False, "C03_PG_CLIENT_IDENTITY_DRIFT")
        seen.add(key)
        by_service[service] = by_service.get(service, 0)+1
        if role == LEGACY[db]:
            owner_connections += 1
    need(by_service.get("aoe2hdbets-web.service", 0) >= 1,
         "C03_PROTECTED_3030_ROLLBACK_DISAPPEARED")
    need(by_service.get("aoe2hdbets-web-prod.service", 0) >= 1,
         "C03_RESTRICTED_R25_EXISTING_CLIENT_DISAPPEARED")
    need(owner_connections > 0, "C03_OWNER_SESSIONS_CHANGED_REVIEW_REQUIRED")
    active_owner_writes = sum(summary[d]["legacy_owner_write_capable_tables"]
                              for d in PUBLIC_TABLES)
    status = ("HOLD_C03_LIVE_OWNER_SESSIONS_RETAIN_EFFECTIVE_WRITE_CAPABILITY"
              if active_owner_writes else
              "HOLD_C03_OWNER_CONNECTIONS_EXIST_BUT_NEGATIVE_DML_UNPROVEN")
    return {
        "schema": SCHEMA, "status": status,
        "legacy_owner_connected_sessions": owner_connections,
        "protected_3030_owner_role_sessions": by_service["aoe2hdbets-web.service"],
        "legacy_hd_api_sessions": by_service.get("aoe2hdbets-api.service",0),
        "legacy_de_api_sessions": by_service.get("aoe2dewarwagers-api.service",0),
        "restricted_r25_sessions": by_service["aoe2hdbets-web-prod.service"],
        "tables": summary,
        "c03_writer_fence_complete": False,
        "non_database_native_rpc_rest_and_external_paths_fenced": False,
        "privileged_existing_sessions_terminated": False,
        "old_3030_rollback_mutated": False,
        "c06_backup_authorized": False,
        "c07_restore_authorized": False,
        "financial_release_authorized": False,
        "production_mutated": False,
    }

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--grants",type=Path,required=True)
    p.add_argument("--grants-sha256",required=True)
    p.add_argument("--sessions",type=Path,required=True)
    p.add_argument("--sessions-sha256",required=True)
    a=p.parse_args(argv)
    try:
        need(os.geteuid()==0, "C03_ROOT_PRIVATE_AUDIT_ONLY")
        report=classify(private_json(a.grants,a.grants_sha256),
                        private_json(a.sessions,a.sessions_sha256))
        print(json.dumps(report,sort_keys=True))
        return 3
    except (Hold, OSError, ValueError, UnicodeError, TypeError, RecursionError):
        print(json.dumps({"schema":SCHEMA,"status":"STOP_C03_BOUND_SOURCE_UNVERIFIED",
                          "c03_writer_fence_complete":False,
                          "financial_release_authorized":False,
                          "production_mutated":False},sort_keys=True))
        return 2

if __name__ == "__main__":
    sys.exit(main())

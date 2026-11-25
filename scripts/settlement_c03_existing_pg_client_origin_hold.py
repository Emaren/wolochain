#!/usr/bin/env python3
"""C03 existing PostgreSQL client-to-systemd origin audit. READ ONLY / HOLD.

Maps client_addr *from pg_stat_activity* through exact TCP source port and
kernel ss PID to /proc/PID/cgroup, with two catalog samples to veto a changed
session population. Never stops processes, changes roles, edits the DB or
authorizes a finance migration, backup or payment.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import subprocess
import sys

SCHEMA = "wolo.c03.existing-pg-client-origin-hold.v1"
ALLOWED = {
    ("aoe2hd_db", "aoe2hd_user"): frozenset({
        "aoe2hdbets-api.service", "aoe2hdbets-web.service"}),
    ("aoe2hd_db", "aoe2war_web_prod"): frozenset({
        "aoe2hdbets-web-prod.service"}),
    ("aoe2de_db", "aoe2de_user"): frozenset({
        "aoe2dewarwagers-api.service"}),
}
REQUIRED = frozenset({
    ("aoe2hd_db", "aoe2hd_user"), ("aoe2de_db", "aoe2de_user"),
})
PROTECTED_ROLLBACK = "aoe2hdbets-web.service"
SOURCE_SQL = """BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;
SELECT datname,usename,pid,coalesce(state,'?'),host(client_addr),
       client_port,extract(epoch FROM backend_start)::bigint
FROM pg_stat_activity
WHERE datname IN ('aoe2hd_db','aoe2de_db') AND backend_type='client backend'
ORDER BY datname,usename,pid;
ROLLBACK;"""
SOURCE_HASH = hashlib.sha256(SOURCE_SQL.encode()).hexdigest()
IP_PORT = re.compile(r"^(?:\[([0-9a-fA-F:.%]+)\]|([0-9.]+)):(\d{1,5})$")
UNIT = re.compile(r"([A-Za-z0-9_.@-]+\.service)(?:/|\n|$)")
PID = re.compile(r"\bpid=(\d{1,9})\b")
MAX_ROWS = 80

class AuditHold(ValueError):
    pass

def need(ok: bool, reason: str):
    if not ok:
        raise AuditHold(reason)

def run(args, timeout=15, input=None):
    p = subprocess.run(args, input=input, capture_output=True, text=True,
                       timeout=timeout, check=False)
    need(p.returncode == 0 and not p.stderr.strip(),
         "LOCAL_READONLY_PROBE_FAILED_" + str(args[0]))
    need(len(p.stdout.encode()) < 65536, "PROBE_OUTPUT_OVERSIZED")
    return p.stdout

def parse_catalog(raw: str):
    rows = {}
    for line in raw.splitlines():
        if not line.strip():
            continue
        need("|" in line, "PG_CATALOG_UNEXPECTED_OUTPUT")
        cols = line.split("|")
        need(len(cols) == 7, "PG_CATALOG_COLUMN_DRIFT")
        db, role, pgpid, state, addr, port, start = cols
        need((db, role) in ALLOWED and
             pgpid.isdecimal() and port.isdecimal() and start.isdecimal() and
             0 < int(pgpid) < 2**31 and 0 < int(port) <= 65535,
             "PG_ROLE_OR_CLIENT_ID_DRIFT")
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            raise AuditHold("PG_CLIENT_ADDRESS_MISSING_OR_NON_IP") from None
        need(ip.is_loopback, "NONLOCAL_FINANCIAL_POSTGRES_CLIENT")
        key = int(pgpid)
        need(key not in rows, "DUPLICATE_POSTGRES_BACKEND")
        rows[key] = {
            "database": db, "role": role, "state": state,
            "source_ip": str(ip), "source_port": int(port),
            "backend_start": int(start), "postgres_backend_pid": key,
        }
        need(len(rows) <= MAX_ROWS, "TOO_MANY_CLIENT_BACKENDS")
    need(rows, "NO_HD_DE_CLIENT_BACKENDS_OBSERVED")
    need(REQUIRED.issubset({(v["database"], v["role"]) for v in rows.values()}),
         "REQUIRED_HD_DE_LEGACY_POOLS_ABSENT")
    return rows

def endpoint(text: str):
    m = IP_PORT.fullmatch(text)
    if not m:
        return None
    try:
        ip = ipaddress.ip_address(m[1] or m[2])
        port = int(m[3])
    except ValueError:
        return None
    return (str(ip), port) if 0 < port <= 65535 else None

def parse_sockets(raw: str):
    mapping = {}
    for line in raw.splitlines():
        meta = line.split("users:", 1)[0].split()
        if len(meta) < 4:
            continue
        local, peer = endpoint(meta[-2]), endpoint(meta[-1])
        if not local or not peer or peer[1] != 5432 or not peer[0] in (
                "127.0.0.1", "::1"):
            continue
        pid = PID.search(line)
        need(pid is not None, "LOCAL_PG_CLIENT_PID_UNREADABLE")
        mapping.setdefault(local, set()).add(int(pid[1]))
    return mapping

def parse_cgroup(text: str) -> str:
    matches = UNIT.findall(text)
    need(len(set(matches)) == 1, "AMBIGUOUS_PROCESS_CGROUP")
    return matches[0]

def parse_stat_start(text: str) -> int:
    # /proc/PID/stat's comm field can itself contain spaces or parentheses.
    i = text.rfind(") ")
    need(i > 0, "PROCESS_STAT_MALFORMED")
    fields = text[i+2:].split()
    need(len(fields) > 19 and fields[19].isdecimal(),
         "PROCESS_STAT_START_MISSING")
    return int(fields[19])

def process_identity(pid: int):
    need(1 < pid < 2**31, "BAD_CLIENT_PID")
    root = Path("/proc") / str(pid)
    try:
        before = (root / "stat").read_text()
        cgroup = (root / "cgroup").read_text()
        after = (root / "stat").read_text()
    except (OSError, UnicodeError):
        raise AuditHold("PROCESS_ORIGIN_UNAVAILABLE") from None
    need(parse_stat_start(before) == parse_stat_start(after),
         "PROCESS_PID_REUSED_DURING_INSPECTION")
    return parse_cgroup(cgroup), parse_stat_start(before)

def qualify(first, socket_map, second, identities):
    need(first == second, "PG_CLIENT_POPULATION_CHANGED_DURING_AUDIT")
    records = []
    for pgpid, source in sorted(first.items()):
        candidates = socket_map.get((source["source_ip"], source["source_port"]), set())
        need(len(candidates) == 1, "PG_CLIENT_PROCESS_SOCKET_AMBIGUOUS")
        ospid = next(iter(candidates))
        need(ospid in identities, "PROCESS_ORIGIN_UNAVAILABLE")
        service, process_start = identities[ospid]
        need(service in ALLOWED[(source["database"], source["role"])],
             "PROCESS_ROLE_OR_SERVICE_NOT_ALLOWLISTED")
        records.append({
            "database": source["database"], "role": source["role"],
            "backend_state_at_probe": source["state"],
            "pg_backend_pid": pgpid, "source_os_pid": ospid,
            "source_service": service, "process_start_ticks": process_start,
            "finance_write_permission_denied": False,
            "safe_to_terminate": False,
        })
    rollback = [r for r in records if r["source_service"] == PROTECTED_ROLLBACK]
    need(len(rollback) >= 1, "PROTECTED_3030_ROLLBACK_CLIENT_NOT_IDENTIFIED")
    return {
        "schema": SCHEMA,
        "status": "HOLD",
        "observed_utc": datetime.now(timezone.utc).isoformat(),
        "source_sql_sha256": SOURCE_HASH,
        "source_services": sorted(set(x["source_service"] for x in records)),
        "total_bound_existing_sessions": len(records),
        "protected_3030_rollback_pg_client_proven": True,
        "exact_socket_to_process_to_systemd_binding": True,
        "process_population_fresh_for_this_observation_only": True,
        "records": records,
        "live_pg_session_termination_authorized": False,
        "finance_writer_denial_proven": False,
        "global_c03_gate_accepted": False,
        "funded_release_authorized": False,
        "production_modified": False,
        "next_proof": "approved writer quarantine plus negative live-role finance DML, coordinated C06/C07, preserve old 3030 PID",
    }

def sample_catalog():
    return parse_catalog(run([
        "runuser", "-u", "postgres", "--", "psql", "-X", "-qAt",
        "-F", "|", "-v", "ON_ERROR_STOP=1", "-d", "postgres",
        "-c", SOURCE_SQL,
    ], timeout=20))

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("inspect",), default="inspect")
    args = parser.parse_args()
    try:
        need(os.geteuid() == 0 and sys.platform == "linux", "HOST_ROOT_ONLY")
        first = sample_catalog()
        sockets = parse_sockets(run(["ss", "-Hntp", "state", "established"]))
        pids = {pid for source in first.values()
                for pid in sockets.get((source["source_ip"], source["source_port"]), set())}
        identities = {pid: process_identity(pid) for pid in pids}
        second = sample_catalog()
        result = qualify(first, sockets, second, identities)
        for r in result["records"]:
            identity_now = process_identity(r["source_os_pid"])
            need(identity_now == identities[r["source_os_pid"]],
                 "SOURCE_PROCESS_RESTARTED_DURING_AUDIT")
        print(json.dumps(result, sort_keys=True))
        return 3
    except (AuditHold, OSError, subprocess.TimeoutExpired, ValueError) as exc:
        print(json.dumps({
            "schema": SCHEMA, "status": "STOP",
            "reason": str(exc)[:120],
            "finance_writer_denial_proven": False,
            "global_c03_gate_accepted": False,
            "funded_release_authorized": False,
            "production_modified": False}, sort_keys=True))
        return 2

if __name__ == "__main__":
    sys.exit(main())

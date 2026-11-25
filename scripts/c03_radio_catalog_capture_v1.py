#!/usr/bin/env python3
"""Fixed Radio metadata-only capture candidate. Native owner admission required."""
import hashlib
import json
import os
from pathlib import Path
import selectors
import signal
import socket
import stat
import subprocess
import tempfile
import time

SQL_SHA = "f784141424dce5f3cb1169d9bc58351509f4a766babced13f51a62edee3818ac"
INSTALL = Path("/usr/local/libexec/aoe2war")
DATABASES = ("aoe2hd_db", "aoe2de_db")
CAP = 2 * 1024 * 1024 + 16384
TARGETS = frozenset((
    ("public", "radio_station_state"), ("public", "radio_programs"),
    ("public", "radio_program_items"), ("public", "radio_assets"),
    ("public", "radio_submissions"), ("public", "radio_listener_states"),
    ("public", "radio_track_ratings"), ("aoe2war_public_v2", "radio_station_display"),
    ("aoe2war_public_v2", "radio_published_tracks"),
))

def require(ok, code):
    if not ok:
        raise ValueError(code)

def unique(pairs):
    result = {}
    for k, v in pairs:
        require(k not in result, "DUPLICATE_JSON_KEY")
        result[k] = v
    return result

def trusted_sql():
    # Check every directory component; do not follow symlinks or accept writable ancestors.
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for name in INSTALL.parts[1:]:
            nxt = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = nxt
            st = os.fstat(fd)
            require(st.st_uid == 0 and not st.st_mode & 0o022, "UNTRUSTED_INSTALL_DIRECTORY")
        sqlfd = os.open("c03_radio_catalog_readonly.sql", os.O_RDONLY | os.O_NOFOLLOW, dir_fd=fd)
        with os.fdopen(sqlfd, "rb") as f:
            st = os.fstat(f.fileno())
            require(stat.S_ISREG(st.st_mode) and st.st_uid == 0 and st.st_nlink == 1
                    and not st.st_mode & 0o022 and st.st_size == 11319, "UNTRUSTED_SQL")
            raw = f.read(11320)
            require(len(raw) == st.st_size and hashlib.sha256(raw).hexdigest() == SQL_SHA,
                    "SQL_DIGEST_MISMATCH")
            return raw
    finally:
        os.close(fd)

def bounded_stdout(proc, cap=CAP, seconds=35):
    deadline = time.monotonic() + seconds
    result = bytearray()
    try:
        with selectors.DefaultSelector() as sel:
            sel.register(proc.stdout, selectors.EVENT_READ)
            while True:
                remaining = deadline - time.monotonic()
                require(remaining > 0 and sel.select(remaining), "OUTER_TIMEOUT")
                chunk = os.read(proc.stdout.fileno(), 65536)
                if not chunk:
                    break
                result.extend(chunk)
                require(len(result) <= cap, "OUTER_BYTE_CAP")
        require(proc.wait(timeout=max(0.01, deadline-time.monotonic())) == 0, "PSQL_FAILED")
        return bytes(result)
    except BaseException:
        if proc.poll() is None:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.wait(timeout=5)
        raise
    finally:
        proc.stdout.close()

def validate(raw, database):
    require(len(raw) <= CAP, "OUTER_BYTE_CAP")
    rows = raw.decode("utf-8").splitlines()
    require(len(rows) == 3, "INCOMPLETE_CAPTURE")
    records = {}
    for row in rows:
        tag, sep, body = row.partition("\t")
        require(sep and tag not in records, "INVALID_CAPTURE_ROW")
        records[tag] = json.loads(body, object_pairs_hook=unique)
    require(set(records) == {"RADIO_CATALOG_META", "RADIO_CATALOG", "FINAL_NONAUTHORIZATION"},
            "UNEXPECTED_CAPTURE_TAG")
    meta = records["RADIO_CATALOG_META"]
    require(meta["database"] == database and meta["session_user"] == "postgres"
            and meta["current_user"] == "postgres" and meta["read_only"] == "on"
            and str(meta["server_version"]).startswith("16.") and meta["snapshot"]
            and meta["captured_at"], "DATABASE_IDENTITY_OR_READONLY_MISMATCH")
    catalog = records["RADIO_CATALOG"]
    rels = catalog["relations"]
    require(len(rels) == len(TARGETS) and
            {(r["schema_name"], r["relation_name"]) for r in rels} == TARGETS,
            "INCOMPLETE_RELATION_SCOPE")
    require(records["FINAL_NONAUTHORIZATION"] == {
        "metadata_only": True, "mutations": False, "production_admitted": False,
        "dynamic_dependency_proof": False, "rights_proven": False, "funding": "DENIED"},
        "NONAUTHORIZATION_MISMATCH")
    return records

def capture(database, raw):
    require(database in DATABASES, "DATABASE_NOT_ADMITTED")
    env = {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "HOME": "/var/lib/postgresql",
           "PGOPTIONS": "-c default_transaction_read_only=on",
           "PGCONNECT_TIMEOUT": "4"}
    cmd = ["/usr/sbin/runuser", "-u", "postgres", "--",
           "/usr/lib/postgresql/16/bin/psql", "-X", "-q", "-A", "-t", "-w",
           "-F", "\t", "-v", "ON_ERROR_STOP=1", "-h", "/var/run/postgresql",
           "-p", "5432", "-U", "postgres", "-d", database]
    with tempfile.TemporaryFile() as source:
        source.write(raw)
        source.seek(0)
        proc = subprocess.Popen(cmd, stdin=source, stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL, env=env,
                                start_new_session=True)
        result = bounded_stdout(proc)
    validate(result, database)
    return result

def main():
    import sys
    try:
        require(len(sys.argv) == 1, "NO_ARGUMENTS_SUPPORTED")
        require(os.geteuid() == 0 and socket.gethostname() == "ubuntu-4gb-hel1-11",
                "NATIVE_ROOT_HOST_REQUIRED")
        os.umask(0o077)
        require(Path(__file__).resolve() == INSTALL / "c03_radio_catalog_capture_v1.py",
                "ROOT_INSTALL_REQUIRED")
        raw = trusted_sql()
        results = {db: capture(db, raw) for db in DATABASES}
        target = Path(tempfile.mkdtemp(prefix="aoe2war-radio-catalog-v1-", dir="/var/lib"))
        evidence = {}
        for db, data in results.items():
            path = target / (db + ".tsv")
            with path.open("xb") as f:
                f.write(data)
                f.flush()
                os.fsync(f.fileno())
            evidence[db] = {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
        receipt = {"status": "RADIO_METADATA_CAPTURED_REVIEW_ONLY", "sql_sha256": SQL_SHA,
                   "directory": str(target), "reports": evidence,
                   "production_admitted": False, "funding": "DENIED"}
        with (target / "receipt.json").open("xb") as f:
            f.write((json.dumps(receipt, sort_keys=True) + "\n").encode())
            f.flush()
            os.fsync(f.fileno())
        fd = os.open(target, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
        print(json.dumps(receipt, sort_keys=True))
        return 0
    except (ValueError, OSError, KeyError, TypeError, subprocess.SubprocessError):
        print('{"status":"HOLD_RADIO_CAPTURE_NOT_ACCEPTED","production_admitted":false,"funding":"DENIED"}')
        return 2

if __name__ == "__main__":
    raise SystemExit(main())

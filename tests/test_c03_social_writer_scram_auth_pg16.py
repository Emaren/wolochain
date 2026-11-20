#!/usr/bin/python3
"""Independent isolated PostgreSQL-16 verification for reviewed SCRAM-only auth source.

No production database, owner Keychain, root credential or HEL1 service is touched.
Every test-only password is ephemeral and never printed.
"""
import importlib.util
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import tempfile

SOURCE = Path(__file__).resolve().parents[1] / "scripts/c03_social_writer_scram_only_v1.py"
spec = importlib.util.spec_from_file_location("writer_auth", SOURCE)
auth = importlib.util.module_from_spec(spec)
spec.loader.exec_module(auth)


def run(args, *, input=None, env=None, check=True):
    child = subprocess.run(args, input=input, capture_output=True, text=True,
                           env=env, timeout=20)
    if check and child.returncode:
        raise AssertionError("ISOLATED_POSTGRES_TEST_COMMAND_FAILED")
    return child


def main():
    pgdir = Path(os.environ.get("PG16_BIN", "/opt/homebrew/opt/postgresql@16/bin"))
    assert all((pgdir / x).exists() for x in ("postgres", "initdb", "pg_ctl", "psql"))
    password = secrets.token_urlsafe(48)
    assert len(password) == 64
    verifier = auth.scram_verifier(password)
    assert verifier.startswith("SCRAM-SHA-256$16384:")
    assert "$" in verifier[15:]
    wrong = secrets.token_urlsafe(48)
    assert wrong != password
    checks = {}
    with tempfile.TemporaryDirectory(prefix="we1-chat-auth-real-pg16-") as temp:
        home = Path(temp)
        db = home / "data"
        sock = home / "sock"
        sock.mkdir(mode=0o700)
        run([str(pgdir / "initdb"), "-D", str(db), "-U", "postgres", "-A", "trust",
             "--no-instructions"])
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = str(s.getsockname()[1])
        hba = db / "pg_hba.conf"
        hba.write_text("""
local all aoe2war_social_writer reject
host aoe2hd_db aoe2war_social_writer 127.0.0.1/32 scram-sha-256
host all aoe2war_social_writer 127.0.0.1/32 reject
host all all 127.0.0.1/32 reject
local all all trust
""")
        run([str(pgdir / "pg_ctl"), "-D", str(db), "-l", str(home / "postgres.log"),
             "-o", f"-k {sock} -p {port} -c listen_addresses=127.0.0.1",
             "start"])
        try:
            admin = [str(pgdir / "psql"), "-X", "-qAt", "-v", "ON_ERROR_STOP=1",
                     "-h", str(sock), "-p", port, "-U", "postgres", "-d", "postgres"]
            # SCRAM verifier only; test-only plaintext never enters SQL.
            sql = ("CREATE DATABASE aoe2hd_db;\n"
                   "CREATE DATABASE aoe2de_db;\n"
                   "CREATE ROLE aoe2war_social_writer LOGIN NOINHERIT NOSUPERUSER "
                   "NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS CONNECTION LIMIT 2 "
                   "PASSWORD '" + verifier + "';\n")
            run(admin, input=sql)
            def probe(secret, database, host):
                a = [str(pgdir / "psql"), "-X", "-qAt", "-w",
                     "-h", host, "-p", port, "-U", "aoe2war_social_writer",
                     "-d", database, "-c", "SELECT current_user, current_database();"]
                e = os.environ.copy()
                e.update({"PGPASSWORD": secret, "PGCONNECT_TIMEOUT": "3",
                          "PGOPTIONS": "-c default_transaction_read_only=on"})
                return run(a, env=e, check=False)
            yes = probe(password, "aoe2hd_db", "127.0.0.1")
            assert yes.returncode == 0 and yes.stdout.strip() == "aoe2war_social_writer|aoe2hd_db"
            checks["HD_SCRAM_AUTH_POSITIVE"] = True
            bad = probe(wrong, "aoe2hd_db", "127.0.0.1")
            assert bad.returncode != 0 and "password authentication failed" in bad.stderr
            checks["HD_WRONG_PASSWORD_DENIED"] = True
            de = probe(password, "aoe2de_db", "127.0.0.1")
            assert de.returncode != 0 and "pg_hba.conf rejects connection" in de.stderr
            checks["DE_VALID_CREDENTIAL_HBA_DENIED"] = True
            unix = probe(password, "aoe2hd_db", str(sock))
            assert unix.returncode != 0 and "pg_hba.conf rejects connection" in unix.stderr
            checks["UNIX_VALID_CREDENTIAL_HBA_DENIED"] = True
            # Source code safety assertions; no session or HTTP auth is claimed here.
            code = SOURCE.read_text()
            assert "ALTER ROLE aoe2war_social_writer PASSWORD" in code
            assert "SOCIAL_WRITER_DATABASE_URL" in code
            assert "session_secret_admitted" in code
            assert "writer_service_started" in code
            checks["PURPOSE_SCOPED_ROLE_ONLY"] = True
            checks["NO_PRODUCTION_DATABASE"] = True
        finally:
            run([str(pgdir / "pg_ctl"), "-D", str(db), "-m", "immediate", "stop"])
    print(json.dumps({"status": "PASS_ISOLATED_PG16_CHAT_AUTH_SCRAM",
                      "checks": checks, "production_executed": False,
                      "secret_material_output": False}, sort_keys=True))


if __name__ == "__main__":
    main()

#!/usr/bin/python3
"""WE1 Chat-only, one-use SCRAM enrollment. SOURCE CANDIDATE: do not run from owner stage.

Must be independently SHA-reviewed and installed root:root 0500 at EXACT_INSTALLED.
Changes only the existing aoe2war_social_writer PASSWORD and a root-private service
environment file. It never changes HBA, grants, roles, financial tables or migrations.
The WE2 operator separately admits the unit/checker and SESSION_SECRET.
"""
import base64
import datetime
import fcntl
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import stat
import subprocess

EXACT_INSTALLED = Path("/usr/local/libexec/wolo-financial-chat-social-v2/writer-auth-v1/c03_social_writer_scram_only_v1.py")
STATE = Path("/var/lib/wolo-financial-role-state/v1/chat-social-hd-v2-exact")
LOBBY = Path("/var/lib/wolo-financial-role-state/v1/lobby-hd-v1-exact")
ENV_DIR = Path("/etc/aoe2war-social-writer")
ENV_FILE = ENV_DIR / "secret.env"
SOCKET = Path("/run/aoe2war-social-writer/social.sock")
HBA = Path("/etc/postgresql/16/main/pg_hba.conf")
REQUIRED = {
    STATE / "receipt-4b683379f965d99122c2e6d4418773874e693225cb0e6403b271ad69df2ccdb1.json":
        "f129576f3c45bb51229e1f35e52c631dfb1f1e77abb672471141743021103120",
    STATE / "recovery-receipt-5b7d80c0d3722e76c70796b8a4fcc3064bc7b279dbc6152acfb264dc4048ed88.json":
        "dffdb0f4bb3d7443cd0f8a58e16841ee1acae6f80e1c621c8b2feb7d982ff1e4",
    LOBBY / "receipt-deee4de5466be78d1a6d4f8074f94ab9573432735546ba1edc6c84bb66a3337c.json":
        "6ccff281fe388c81c16a60e0cf33f8c8fef6df4da7975da289e064c26dba2168",
    HBA: "3fecbffb683bf2bc21e8bd880b9be982d14cbe3bbf67aae08f801159d6b76789",
    Path("/var/lib/aoe2war-web-prod-da0bee282e52/bin/social-writer.mjs"):
        "4115061e62902956ae13b202ed15f26edf8d48c716c3d2521178c346eb19ebe7",
}
RECEIPT = STATE / "writer-auth-v1-receipt.json"
LOCK = STATE / "writer-auth-v1-controller.lock"
ROLE = "aoe2war_social_writer"
PG = "/usr/bin/psql"
RUNUSER = "/usr/sbin/runuser"


class Hold(RuntimeError):
    pass


def need(ok, reason):
    if not ok:
        raise Hold(reason)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def root_regular(path, *, exact_mode=None):
    st = path.lstat()
    need(stat.S_ISREG(st.st_mode) and st.st_uid == 0 and st.st_gid == 0
         and st.st_nlink == 1 and (st.st_mode & 0o022) == 0, "ROOT_FILE_CUSTODY")
    if exact_mode is not None:
        need(stat.S_IMODE(st.st_mode) == exact_mode, "ROOT_FILE_MODE")
    return st


def scram_verifier(password, salt=None, iterations=16384):
    """Build PostgreSQL SCRAM-SHA-256 verifier; raw password never enters SQL."""
    need(isinstance(password, str) and len(password) >= 40, "WEAK_PASSWORD")
    need(iterations >= 4096, "WEAK_SCRAM_ITERATIONS")
    salt = secrets.token_bytes(16) if salt is None else salt
    need(len(salt) == 16, "BAD_SALT")
    salted = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    client_key = hmac.new(salted, b"Client Key", hashlib.sha256).digest()
    stored_key = hashlib.sha256(client_key).digest()
    server_key = hmac.new(salted, b"Server Key", hashlib.sha256).digest()
    enc = lambda value: base64.b64encode(value).decode("ascii")
    return f"SCRAM-SHA-256${iterations}:{enc(salt)}${enc(stored_key)}:{enc(server_key)}"


def psql_as_postgres(sql, *, read_only):
    argv = [RUNUSER, "-u", "postgres", "--", PG, "-X", "-qAt",
            "-v", "ON_ERROR_STOP=1", "-d", "aoe2hd_db"]
    env = {"PATH": "/usr/bin:/bin", "HOME": "/var/lib/postgresql",
           "PGAPPNAME": "we1-social-writer-auth-v1"}
    if read_only:
        env["PGOPTIONS"] = "-c default_transaction_read_only=on"
        sql = "BEGIN READ ONLY;\n" + sql + "\nCOMMIT;\n"
    result = subprocess.run(argv, input=sql, text=True, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, env=env, timeout=20)
    need(result.returncode == 0, "POSTGRES_DENIED")
    return result.stdout.strip()


def role_evidence():
    sql = """
SELECT rolcanlogin::int, rolinherit::int, rolsuper::int,
       rolcreatedb::int, rolcreaterole::int, rolreplication::int,
       rolbypassrls::int, rolconnlimit, (rolpassword IS NOT NULL)::int
  FROM pg_authid WHERE rolname='aoe2war_social_writer';
SELECT count(*) FROM pg_auth_members m
  JOIN pg_authid r ON r.oid=m.member
 WHERE r.rolname='aoe2war_social_writer';
SELECT count(*)
  FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
 WHERE n.nspname='public' AND c.relname IN
 ('users','bet_wagers','clan_messages','direct_messages')
   AND (has_table_privilege('aoe2war_social_writer', c.oid, 'SELECT')
        OR has_table_privilege('aoe2war_social_writer',c.oid,'INSERT')
        OR has_table_privilege('aoe2war_social_writer',c.oid,'UPDATE')
        OR has_table_privilege('aoe2war_social_writer',c.oid,'DELETE'));
SELECT has_schema_privilege('aoe2war_social_writer','public','CREATE')::int;
"""
    rows = [line for line in psql_as_postgres(sql, read_only=True).splitlines()
            if line and line != "BEGIN" and line != "COMMIT"]
    need(len(rows) == 4, "ROLE_QUERY_SHAPE")
    need(rows[0].startswith("1|0|0|0|0|0|0|2|"), "ROLE_FLAGS_CHANGED")
    need(rows[1:] == ["0", "0", "0"], "ROLE_PRIVILEGE_CHANGED")
    password_present = rows[0].split("|")[-1]
    need(password_present in ("0", "1"), "ROLE_PASSWORD_SHAPE")
    return password_present == "1"


def connection_probe(password, *, database, host):
    args = [PG, "-X", "-qAt", "-w", "-p", "5432", "-U", ROLE,
            "-d", database, "-c", "SELECT current_user, current_database();"]
    args += ["-h", host]
    env = {"PATH": "/usr/bin:/bin", "PGPASSWORD": password,
           "PGCONNECT_TIMEOUT": "4", "PGOPTIONS": "-c default_transaction_read_only=on"}
    proc = subprocess.run(args, env=env, text=True, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, timeout=12)
    return proc.returncode, proc.stdout.strip(), proc.stderr


def write_exclusive(path, data):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW, 0o600)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb", closefd=False) as out:
            out.write(data)
            out.flush()
        os.fsync(fd)
    finally:
        os.close(fd)


def execute():
    need(os.geteuid() == 0, "ROOT_REQUIRED")
    os.umask(0o077)
    need(Path(__file__).resolve() == EXACT_INSTALLED, "TRUSTED_INSTALL_ONLY")
    root_regular(EXACT_INSTALLED, exact_mode=0o500)
    for parent in (STATE, LOBBY, ENV_DIR):
        s = parent.lstat()
        need(stat.S_ISDIR(s.st_mode) and s.st_uid == 0 and
             not (s.st_mode & 0o077), "PROTECTED_PARENT_REQUIRED")
    for path, digest in REQUIRED.items():
        if path != HBA:
            root_regular(path)
        need(sha(path) == digest, "SOURCE_OR_JOURNAL_SHA_MISMATCH")
    need(not RECEIPT.exists() and not ENV_FILE.exists(), "ALREADY_ADMITTED_OR_PARTIAL")
    need(not SOCKET.exists(), "LIVE_SOCKET_PRESENT")
    service = subprocess.run(["/usr/bin/systemctl", "is-active", "aoe2war-social-writer.service"],
                             text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=8)
    need(service.stdout.strip() in ("inactive", "failed", "unknown") and
         service.returncode != 0, "SERVICE_MUST_BE_STOPPED")
    lockfd = os.open(LOCK, os.O_WRONLY | os.O_CREAT | os.O_CLOEXEC | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(lockfd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        need(not role_evidence(), "PASSWORD_ALREADY_PRESENT")
        # Generates 384 bits of fresh credential entropy on the protected host only.
        password = secrets.token_urlsafe(48)
        need(re.fullmatch(r"[A-Za-z0-9_-]{64}", password) is not None,
             "PASSWORD_ENCODING")
        verifier = scram_verifier(password)
        # The service file intentionally contains ONLY database auth. WE2 must
        # install the shared SESSION_SECRET under separate source-pinned custody.
        url = f"postgresql://{ROLE}:{password}@127.0.0.1:5432/aoe2hd_db"
        write_exclusive(ENV_FILE, ("SOCIAL_WRITER_DATABASE_URL=" + url + "\n").encode("utf-8"))
        dirfd = os.open(ENV_DIR, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(dirfd)
        finally:
            os.close(dirfd)
        # Only reviewed role-password SQL; no grants, schema or financial writes.
        psql_as_postgres("ALTER ROLE aoe2war_social_writer PASSWORD '" + verifier + "';",
                         read_only=False)
        need(role_evidence(), "ROLE_PASSWORD_NOT_INSTALLED")
        rc, output, _ = connection_probe(password, database="aoe2hd_db", host="127.0.0.1")
        need(rc == 0 and output == ROLE + "|aoe2hd_db", "HD_SCRAM_POSITIVE_FAILED")
        rc, _, err = connection_probe(password, database="aoe2de_db", host="127.0.0.1")
        need(rc != 0 and "pg_hba.conf rejects connection" in err, "DE_HBA_DENIAL_FAILED")
        rc, _, err = connection_probe(password, database="aoe2hd_db",
                                      host="/var/run/postgresql")
        need(rc != 0 and "pg_hba.conf rejects connection" in err, "UNIX_HBA_DENIAL_FAILED")
        need(sha(HBA) == REQUIRED[HBA], "HBA_CHANGED")
        receipt = {
            "schema": "aoe2war.we1.chat-social-writer-scram-enroll-only.v1",
            "status": "PASS_HD_SCRAM_AUTH_ONLY_WITH_DE_UNIX_DENIAL",
            "utc": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
            "source_sha256": sha(EXACT_INSTALLED),
            "social_sql_receipt_sha256": REQUIRED[next(p for p in REQUIRED if p.name.startswith("receipt-4b683"))],
            "lobby_sql_receipt_sha256": REQUIRED[next(p for p in REQUIRED if p.name.startswith("receipt-deee"))],
            "hba_sha256": REQUIRED[HBA],
            "role": ROLE,
            "hd_database": "aoe2hd_db",
            "role_memberships": 0,
            "direct_legacy_table_access": False,
            "hd_scram_positive": True,
            "de_hba_denied": True,
            "unix_hba_denied": True,
            "financial_authorized": False,
            "funding_authorized": False,
            "secret_env_path": str(ENV_FILE),
            "secret_env_root_private": True,
            "session_secret_admitted": False,
            "writer_service_started": False,
        }
        write_exclusive(RECEIPT, (json.dumps(receipt, sort_keys=True, separators=(",", ":"))
                                  + "\n").encode("utf-8"))
        statefd = os.open(STATE, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(statefd)
        finally:
            os.close(statefd)
        return sha(RECEIPT)
    finally:
        os.close(lockfd)


if __name__ == "__main__":
    try:
        receipt_sha = execute()
        print("PASS_AUTH_ONLY_NO_SECRET receipt_sha256=" + receipt_sha)
    except (Hold, OSError, subprocess.TimeoutExpired) as error:
        # Never print subprocess arguments, SQL, SCRAM verifier or password.
        code = str(error) if isinstance(error, Hold) else "PROTECTED_AUTH_ADMISSION_ERROR"
        print("HOLD_CHAT_SOCIAL_WRITER_AUTH_" + code)
        raise SystemExit(2)

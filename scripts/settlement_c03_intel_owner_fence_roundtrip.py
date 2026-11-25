#!/usr/bin/env python3
"""Rehearse a committed owner transfer and its inverse on the Intel C07 parity clones."""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
import uuid


PRIVATE = Path.home() / ".wolo-owner-authority"
ORIGINAL = PRIVATE / "c07-role-graph-physical-rehearsal-20261109"
ORIGINAL_SHA = "cd1c2d24739534f14b6ce7e452b9a0e2ec9287bf9a5b0dc8f3dc49186179db6a"
TOOLS = Path.home() / ".local/aoe2war-pg16-16.15/bin"
SCOPE = {
    "hd": (190, 180, 39, "pending_wolo_claims"),
    "de": (52, 50, 0, "trophy_payouts"),
}
NEW_OWNER = "c03_rehearsal_finance_owner"
PORT = "54451"

# Tables precede sequences so ownership of their dependent sequences moves with them.
OBJECTS = """
    SELECT CASE c.relkind WHEN 'S' THEN 'SEQUENCE ' ELSE 'TABLE ' END ||
           format('%I.%I',n.nspname,c.relname),
           pg_get_userbyid(c.relowner), c.relkind::text
      FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
     WHERE n.nspname='public' AND c.relkind IN ('r','p','S')
    UNION ALL
    SELECT format('FUNCTION %I.%I(%s)',n.nspname,p.proname,
                  pg_get_function_identity_arguments(p.oid)),
           pg_get_userbyid(p.proowner), 'function'
      FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
     WHERE n.nspname='public' AND p.prokind='f' AND NOT p.prosecdef
    ORDER BY 1
"""


class RehearsalError(RuntimeError):
    pass


def require(condition, reason):
    if not condition:
        raise RehearsalError(reason)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def run(argv, label, *, input=None, timeout=100):
    result = subprocess.run(argv, input=input, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            timeout=timeout, env={**os.environ, "LC_ALL": "C", "PGCONNECT_TIMEOUT": "4"})
    if result.returncode:
        state = re.search(rb"ERROR: +([0-9A-Z]{5})\b", result.stderr)
        raise RehearsalError(label + (" " + state[1].decode() if state else ""))
    return result.stdout


def stopped(pgdata):
    require(not pgdata.is_symlink() and (pgdata / "PG_VERSION").read_text() == "16\n"
            and not (pgdata / "postmaster.pid").exists(), "SOURCE_NOT_STOPPED_PG16")
    require(not any(entry.is_symlink() for entry in pgdata.rglob("*")), "CLUSTER_CONTAINS_SYMLINK")
    state = run([TOOLS / "pg_controldata", pgdata], "PG_CONTROLDATA_FAILED")
    require(b"Database cluster state:               shut down\n" in state, "SOURCE_NOT_CLEANLY_STOPPED")


def assert_no_legacy_writes(sql, old):
    # Effective checks include inherited and explicit column grants and writable views.
    require(sql(f"""
        SELECT NOT EXISTS (
          SELECT FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
           WHERE n.nspname NOT LIKE 'pg\\_%' AND n.nspname<>'information_schema'
             AND CASE WHEN c.relkind='S' THEN has_sequence_privilege('{old}',c.oid,'USAGE,UPDATE')
                      WHEN c.relkind IN ('r','p','v','f')
                      THEN has_table_privilege('{old}',c.oid,'INSERT,UPDATE,DELETE,TRUNCATE,TRIGGER')
                        OR has_any_column_privilege('{old}',c.oid,'INSERT,UPDATE')
                      ELSE false END
        ) AND NOT EXISTS (
          SELECT FROM pg_namespace n WHERE n.nspname NOT LIKE 'pg\\_%'
             AND n.nspname<>'information_schema' AND has_schema_privilege('{old}',n.oid,'CREATE')
        ) AND NOT EXISTS (
          SELECT FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
           WHERE n.nspname NOT LIKE 'pg\\_%' AND n.nspname<>'information_schema'
             AND (p.prosecdef OR p.prokind='p')
             AND has_schema_privilege('{old}',n.oid,'USAGE')
             AND has_function_privilege('{old}',p.oid,'EXECUTE')
        ) AND NOT has_database_privilege('{old}',current_database(),'CREATE');
    """) == "t", "LEGACY_EFFECTIVE_WRITE_OR_DDL_REMAINS")


@contextmanager
def legacy_backend(args):
    env = {**os.environ, "LC_ALL": "C", "PGOPTIONS": "-c statement_timeout=10000"}
    with subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                          stderr=subprocess.DEVNULL, text=True, env=env) as proc:
        def query(statement, expected="00000"):
            proc.stdin.write(statement + "\n\\echo c03-status :SQLSTATE\n")
            proc.stdin.flush()
            rows = []
            for _ in range(10):
                line = proc.stdout.readline().strip()
                if line.startswith("c03-status "):
                    require(line == "c03-status " + expected, "UNEXPECTED_LEGACY_SQLSTATE")
                    return rows
                require(line, "LEGACY_BACKEND_CLOSED")
                rows.append(line)
            raise RehearsalError("LEGACY_BACKEND_MARKER_MISSING")

        try:
            yield query
        finally:
            proc.stdin.close()
            if proc.poll() is None:
                proc.terminate()


def check_auth(sql, uid, nonce_tag):
    # Exercise the real definer bodies with a new synthetic identity in a rolled-back
    # transaction. No real Steam credential or OpenID assertion enters the test.
    require(sql("""
        SELECT count(*)=3 AND bool_and(prosecdef
            AND pg_get_userbyid(proowner)='aoe2war_auth_owner'
            AND proconfig=ARRAY['search_path=pg_catalog']
            AND md5(pg_get_functiondef(oid))=CASE proname
              WHEN 'complete_steam_login' THEN '5f9ed5c71d3867b5ce08b8ca70374fc5'
              WHEN 'read_user' THEN '7a3fa3a9ff027bec46caf10d92080f3d'
              WHEN 'touch_session' THEN '0a95ed3ac1676477785d1ecc6adc1a17'
              ELSE '' END)
        FROM pg_proc WHERE pronamespace='aoe2war_auth_v1'::regnamespace;
    """) == "t", "AUTH_DEFINER_BODY_OR_TOPOLOGY_DRIFT")
    steam_id = str(10000000000000000 + uuid.uuid4().int % 90000000000000000)
    require(sql(f"SELECT count(*)=0 FROM public.users WHERE steam_id='{steam_id}' OR uid='{uid}'") == "t",
            "SYNTHETIC_AUTH_ID_COLLISION")
    nonce = f"to_char(clock_timestamp() AT TIME ZONE 'UTC','YYYY-MM-DD\"T\"HH24:MI:SS\"Z\"') || '{nonce_tag}'"
    call = f"aoe2war_auth_v1.complete_steam_login('{steam_id}',NULL,'{uid}',NULL,nonce)"
    require(sql(f"""
        BEGIN;
        SET LOCAL SESSION AUTHORIZATION aoe2war_web_prod;
        DO $check$
        DECLARE nonce text := {nonce};
        BEGIN
          PERFORM 1 FROM aoe2war_public_v1.player_badges WHERE false;
          IF {call} IS DISTINCT FROM '{uid}' THEN
            RAISE EXCEPTION USING ERRCODE='P7101', MESSAGE='AUTH_FIXTURE_LOGIN_FAILED';
          END IF;
          PERFORM aoe2war_auth_v1.touch_session('{uid}', '{uid}@invalid.example');
          IF (SELECT count(*) FROM aoe2war_auth_v1.read_user('{uid}')) <> 1 THEN
            RAISE EXCEPTION USING ERRCODE='P7102', MESSAGE='AUTH_FIXTURE_READ_FAILED';
          END IF;
          BEGIN
            PERFORM {call};
            RAISE EXCEPTION USING ERRCODE='P7103', MESSAGE='AUTH_NONCE_REPLAY_WAS_ACCEPTED';
          EXCEPTION WHEN unique_violation THEN NULL;
          END;
          BEGIN
            PERFORM aoe2war_auth_v1.complete_steam_login('{steam_id}',NULL,'{uid}',NULL,
                '2000-01-01T00:00:00Z{nonce_tag}');
            RAISE EXCEPTION USING ERRCODE='P7104', MESSAGE='AUTH_STALE_NONCE_WAS_ACCEPTED';
          EXCEPTION WHEN invalid_parameter_value THEN NULL;
          END;
          BEGIN
            UPDATE public.users SET wallet_address=wallet_address WHERE false;
            RAISE EXCEPTION USING ERRCODE='P7105', MESSAGE='AUTH_RUNTIME_WALLET_UPDATE_WAS_ACCEPTED';
          EXCEPTION WHEN insufficient_privilege THEN NULL;
          END;
        END
        $check$;
        ROLLBACK;
        SELECT count(*)=0 FROM public.users WHERE uid='{uid}';
    """) == "t", "AUTH_POSITIVE_REPLAY_EXPIRY_OR_WALLET_PROBE_FAILED")


def exercise(socket, scope):
    tables, sequences, functions, protected_table = SCOPE[scope]
    old = f"aoe2{scope}_user"
    db = f"c07_{scope}_isolated"
    connect = ["-h", str(socket), "-p", PORT, "-d", db]
    psql = [TOOLS / "psql", "-XqAt", *connect]

    def sql(statement):
        return run([*psql, "-v", "ON_ERROR_STOP=1", "-v", "VERBOSITY=sqlstate"], "ISOLATED_SQL_FAILED",
                   input=statement.encode()).decode().strip()

    def schema_hash():
        return digest(run([TOOLS / "pg_dump", *connect, "--create", "--schema-only",
                           "--restrict-key=C03IntelOwnerFence"], "SCHEMA_FINGERPRINT_FAILED"))

    schema_owner = sql("SELECT pg_get_userbyid(nspowner) FROM pg_namespace WHERE nspname='public';")
    require(schema_owner in ("pg_database_owner", old), "PUBLIC_SCHEMA_OWNER_DRIFT")
    preflight = sql(f"""
        SELECT concat_ws('|',current_setting('server_version_num')::int/10000=16,
           current_setting('listen_addresses')='',
           pg_get_userbyid(datdba)='{old}',
           (SELECT NOT (rolsuper OR rolcreaterole OR rolcreatedb OR rolreplication OR rolbypassrls)
              FROM pg_roles WHERE oid=datdba),
           NOT EXISTS(SELECT FROM pg_auth_members WHERE member=datdba),
           NOT EXISTS(SELECT FROM pg_roles WHERE rolname='{NEW_OWNER}'))
        FROM pg_database WHERE datname=current_database();
    """)
    require(preflight == "t|t|t|t|t|t", "ORIGINAL_ROLE_OR_ISOLATION_DRIFT " + preflight)
    rows = [line.split("\t") for line in sql(
        f"SELECT concat_ws(E'\\t',obj,owner,kind) FROM ({OBJECTS.rstrip()}) AS s(obj,owner,kind)"
    ).splitlines()]
    require(all(owner == old for _, owner, _ in rows), "UNREVIEWED_OBJECT_OWNER")
    counts = tuple(sum(kind in kinds for _, _, kind in rows)
                   for kinds in (("r", "p"), ("S",), ("function",)))
    require(counts == (tables, sequences, functions), "PUBLIC_OBJECT_SCOPE_DRIFT")

    schema_before = schema_hash()
    targets = [obj for obj, _, _ in sorted(rows, key=lambda row: row[2] == "S")]
    if schema_owner == old:
        targets.append("SCHEMA public")
    targets.append(f"DATABASE {db}")

    def move_ownership(owner, *, create=False, drop=False):
        ddl = ["BEGIN;", "SET LOCAL lock_timeout='3s';", "SET LOCAL statement_timeout='60s';"]
        if create:
            ddl.append(f"CREATE ROLE {NEW_OWNER} NOLOGIN NOINHERIT;")
        ddl.extend(f"ALTER {target} OWNER TO {owner};" for target in targets)
        if drop:
            ddl.append(f"DROP ROLE {NEW_OWNER};")
        sql("\n".join([*ddl, "COMMIT;"]))

    fixture = uuid.uuid4().hex
    if scope == "hd":
        check_auth(sql, "u_" + fixture, fixture)
    probe_delete = f"DELETE FROM public.{protected_table} WHERE false;"
    probe_ddl = "CREATE SCHEMA c03_rehearsal_legacy_probe;"
    probe_sequence = "SELECT nextval('public.users_id_seq');"
    with legacy_backend([*psql, "-U", old]) as connected:
        pid = connected("SELECT pg_backend_pid();")
        connected(probe_delete)
        connected(probe_sequence)
        connected("BEGIN;")
        connected(probe_ddl)
        connected("ROLLBACK;")
        connected("BEGIN;")
        connected(f"LOCK TABLE public.{protected_table} IN ACCESS SHARE MODE;")
        try:
            move_ownership(NEW_OWNER, create=True)
        except RehearsalError as error:
            require(str(error) == "ISOLATED_SQL_FAILED 55P03", "LOCK_DID_NOT_REFUSE_WITH_TIMEOUT")
        else:
            raise RehearsalError("FENCE_COMMITTED_WITH_LEGACY_LOCK")
        require(schema_hash() == schema_before, "PARTIAL_CHANGE_AFTER_LOCK_TIMEOUT")
        connected("ROLLBACK;")
        move_ownership(NEW_OWNER, create=True)
        try:
            assert_no_legacy_writes(sql, old)
            require(connected("SELECT pg_backend_pid();") == pid, "LEGACY_BACKEND_ID_CHANGED")
            for statement in (probe_delete, probe_ddl, probe_sequence):
                connected(statement, "42501")
                with legacy_backend([*psql, "-U", old]) as fresh:
                    fresh(statement, "42501")
            if scope == "hd":
                connected("SELECT * FROM aoe2war_auth_v1.read_user('c03_rehearsal_probe');", "42501")
                check_auth(sql, "u_" + fixture, fixture)
        finally:
            move_ownership(old, drop=True)
        require(connected("SELECT pg_backend_pid();") == pid, "LEGACY_BACKEND_CHANGED_ON_ROLLBACK")
        connected(probe_delete)
        connected(probe_sequence)
        connected("BEGIN;")
        connected(probe_ddl)
        connected("ROLLBACK;")
    require(schema_hash() == schema_before, "SCHEMA_OWNER_OR_ACL_ROLLBACK_DRIFT")
    return {"tables": tables, "sequences": sequences, "functions": functions,
            "owner_acl_roundtrip_sha256": schema_before,
            "same_backend_and_fresh_dml_ddl_sequence_denied": True,
            "legacy_lock_timeout_left_no_partial_migration": True,
            "protected_auth_synthetic_login_replay_and_wallet_checks": scope == "hd"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scope", choices=SCOPE)
    args = parser.parse_args()
    require(sys.platform == "darwin" and platform.machine() == "x86_64" and os.geteuid() != 0,
            "INTEL_ONLY_UNPRIVILEGED")
    receipt = ORIGINAL / "receipt.json"
    metadata = receipt.lstat()
    require(stat.S_ISREG(metadata.st_mode) and stat.S_IMODE(metadata.st_mode) == 0o600
            and metadata.st_uid == os.geteuid() and metadata.st_nlink == 1
            and digest(receipt.read_bytes()) == ORIGINAL_SHA, "SOURCE_PARITY_RECEIPT_DRIFT")
    source = PRIVATE / f"c07-role-{args.scope}-v1" / "pgdata"
    stopped(source)
    root = Path(tempfile.mkdtemp(prefix=f"c03-{args.scope}-", dir=PRIVATE))
    clone = root / "db"
    socket = root / "s"
    socket.mkdir(mode=0o700)
    run(["cp", "-c", "-R", source, clone], "APFS_CLONE_FAILED", timeout=200)
    stopped(clone)
    opts = (f"-c listen_addresses= -c unix_socket_directories={shlex.quote(str(socket))}"
            f" -c unix_socket_permissions=0700 -p {PORT}")
    try:
        run([TOOLS / "pg_ctl", "-D", clone, "-o", opts, "-l", root / "postgres.log",
             "-w", "start"], "CLONE_START_FAILED")
        result = exercise(socket, args.scope)
    finally:
        if (clone / "postmaster.pid").exists():
            run([TOOLS / "pg_ctl", "-D", clone, "-m", "fast", "-w", "stop"], "CLONE_STOP_FAILED")
        stopped(clone)
        stopped(source)
        shutil.rmtree(root)
    result.update(scope=args.scope, utc=datetime.now(timezone.utc).isoformat(),
                  source_parity_receipt_sha256=ORIGINAL_SHA,
                  script_sha256=digest(Path(__file__).read_bytes()),
                  original_and_clone_stopped=True, production_authorized=False)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except (RehearsalError, OSError, subprocess.SubprocessError) as exc:
        print(f"C03_REHEARSAL_REFUSED {exc}", file=sys.stderr)
        sys.exit(3)

#!/usr/bin/env python3
"""Opt-in disposable real PostgreSQL16 HD Library contract test, SOURCE ONLY.

Entirely synthetic DB, dedicated unix socket, TCP disabled, temporary PGDATA.
No remote connections, production catalog reads, grants, or admission.
"""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tempfile

PG = Path("/usr/lib/postgresql/16/bin")
INSTALL = Path("scripts/c03_library_public_projection_candidate.sql").resolve()
INVERSE = Path("scripts/c03_library_public_projection_inverse_candidate.sql").resolve()
EXPECTED = "{aoe2hd_user=arwdDxt/aoe2hd_user,aoe2war_r25_web_ro=r/aoe2hd_user}"


def call(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run([str(x) for x in args], capture_output=True, text=True, check=False)
    if check and result.returncode != 0:
        # All subprocesses target a fresh synthetic PGDATA, never a live catalog.
        raise RuntimeError(f"DISPOSABLE_PG16_CMD_FAILED exit={result.returncode} "
                           f"stderr={result.stderr[-1400:]} stdout={result.stdout[-400:]}")
    return result


def main() -> None:
    if os.environ.get("WE1_C03_DISPOSABLE_ONLY") != "1" or os.geteuid() == 0:
        raise SystemExit("HOLD: explicit unprivileged disposable-only opt-in required")
    if not all((PG / n).is_file() for n in ("initdb", "pg_ctl", "psql", "createdb")):
        raise SystemExit("HOLD: independent Linux PostgreSQL16 binaries missing")
    if not (INSTALL.is_file() and INVERSE.is_file()):
        raise SystemExit("HOLD: exact candidate files missing")
    checks: list[str] = []

    def ok(condition: bool, label: str) -> None:
        if not condition:
            raise AssertionError(label)
        checks.append(label)

    with tempfile.TemporaryDirectory(prefix="we1-c03-hd-library-pg16-") as temp:
        base = Path(temp)
        base.chmod(0o700)
        data, sock = base / "data", base / "socket"
        sock.mkdir(mode=0o700)
        port = str(41000 + os.getpid() % 5000)
        started = False

        def psql(query: str | None = None, *, db: str = "aoe2hd_db",
                 as_user: str | None = None, file: Path | None = None,
                 check: bool = True) -> subprocess.CompletedProcess[str]:
            args = [str(PG / "psql"), "-X", "-A", "-t", "-v", "ON_ERROR_STOP=1",
                    "-h", str(sock), "-p", port, "-d", db]
            if as_user:
                args += ["-U", as_user]
            if file is not None:
                args += ["-f", str(file)]
            elif query is not None:
                args += ["-c", query]
            else:
                raise ValueError("query or file needed")
            return call(*args, check=check)

        def scalar(query: str, as_user: str | None = None) -> str:
            return psql(query, as_user=as_user).stdout.strip()

        try:
            call(PG / "initdb", "-D", data, "--no-sync", "--auth-local=trust", "--auth-host=reject")
            call(PG / "pg_ctl", "-D", data, "-o",
                 f"-c listen_addresses= -c unix_socket_directories={sock} -c port={port}",
                 "-w", "-l", base / "postgres.log", "start")
            started = True
            for database in ("aoe2hd_db", "aoe2de_db"):
                call(PG / "createdb", "-h", sock, "-p", port, database)
            ok(True, "new private PG16 cluster with no TCP and HD+DE synthetic databases")
            schema = r'''
CREATE ROLE aoe2hd_user NOLOGIN;
CREATE ROLE aoe2war_web_prod LOGIN NOINHERIT;
CREATE ROLE aoe2war_r25_web_ro NOLOGIN NOINHERIT;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
CREATE TABLE public.users(id integer PRIMARY KEY,uid text NOT NULL,verification_method text);
CREATE TABLE public.user_activity_events(id integer PRIMARY KEY,user_id integer,type varchar(40),label varchar(80),metadata jsonb,created_at timestamp(6));
CREATE TABLE public.watcher_client_events(id bigint PRIMARY KEY,user_id integer,user_uid varchar(100),event_type varchar(40),created_at timestamp(6),watcher_id varchar(80),session_id varchar(80),replay_hash varchar(64),ip_address varchar(80),user_agent varchar(512),metadata jsonb);
ALTER TABLE public.users OWNER TO aoe2hd_user;
ALTER TABLE public.user_activity_events OWNER TO aoe2hd_user;
ALTER TABLE public.watcher_client_events OWNER TO aoe2hd_user;
SET ROLE aoe2hd_user;
GRANT SELECT ON public.user_activity_events,public.watcher_client_events TO aoe2war_r25_web_ro;
RESET ROLE;
CREATE TABLE public.financial_escrow_test(id integer,amount integer);
INSERT INTO public.users VALUES (1,'scribe','steam'),(3,'aoe2hd_ai_test','system');
INSERT INTO public.user_activity_events VALUES
(1,1,'replay_upload','private-filename.zip','{"packageUpload":true,"uploadedCount":3,"gameIds":[17,"secret",19],"privateToken":"secret"}',now()),
(2,999,'replay_upload','orphan.zip','{"packageUpload":true,"gameIds":[22]}',now()),
(3,1,'private_auth_change','secret','{"privateToken":"secret"}',now());
INSERT INTO public.watcher_client_events VALUES
(1,1,'scribe','batch_upload_file_succeeded',now(),'private-watcher','private-session','hash','192.0.2.99','browser-agent','{"privateToken":"secret"}'),
(2,999,'unknown','batch_upload_file_succeeded',now(),'orphan','orphan','hash',null,null,'{}'),
(3,3,'aoe2hd_ai_test','batch_upload_file_succeeded',now(),'system','system','hash',null,null,'{}'),
(4,1,'different-uid','batch_upload_file_succeeded',now(),'mismatch','mismatch','hash',null,null,'{}'),
(5,1,'scribe','private_login',now(),'private','private','hash',null,null,'{}');
'''
            psql(schema)
            ok(scalar(f"SELECT count(*) FROM pg_class WHERE oid IN ('public.user_activity_events'::regclass,'public.watcher_client_events'::regclass) AND relacl::text='{EXPECTED}'") == "2",
               "two exact original HD explicit event relacls")
            snapshot = r'''
SELECT 'rel:'||c.relname||':'||coalesce(c.relacl::text,'<NULL>')
 FROM pg_class c WHERE c.relnamespace='public'::regnamespace AND c.relkind IN ('r','p','S')
UNION ALL
SELECT 'att:'||c.relname||'.'||a.attname||':'||coalesce(a.attacl::text,'<NULL>')
 FROM pg_class c JOIN pg_attribute a ON a.attrelid=c.oid
 WHERE c.relnamespace='public'::regnamespace AND c.relkind IN ('r','p') AND a.attnum>0 AND NOT a.attisdropped
ORDER BY 1'''
            before = scalar(snapshot)
            negative = psql(db="aoe2de_db",file=INSTALL,check=False)
            ok(negative.returncode != 0 and "LIBRARY_HD_ONLY_ROLE_OR_SCHEMA_PREIMAGE_HOLD" in negative.stderr,
               "same SQL refuses DE before creating any schema")
            ok(psql("SELECT to_regnamespace('aoe2war_library_activity_public') IS NULL", db="aoe2de_db").stdout.strip() == "t",
               "DE preflight leaves no installed schema")
            psql(file=INSTALL)
            ok(scalar(snapshot) == before, "install preserves raw base relacl and attacl byte-exact")
            web = "aoe2war_web_prod"
            ok(scalar("SELECT count(*) FROM aoe2war_library_activity_public.replay_uploads",web) == "1",
               "upload read selects exactly recognized existing human")
            ok(scalar("SELECT count(*) FROM aoe2war_library_watcher_public.batch_receipts",web) == "1",
               "watcher read excludes orphan, system, inconsistent UID and private classes")
            ok(scalar("SELECT label IS NULL FROM aoe2war_library_activity_public.replay_uploads",web) == "t",
               "no private raw upload filename in label")
            ok(scalar("SELECT metadata?'privateToken' FROM aoe2war_library_activity_public.replay_uploads",web) == "f",
               "private metadata key removed")
            ok(scalar("SELECT metadata?'filenames' FROM aoe2war_library_activity_public.replay_uploads",web) == "f",
               "filename array unavailable")
            ok(scalar("SELECT metadata->'gameIds' FROM aoe2war_library_activity_public.replay_uploads",web) == "[17, 19]",
               "non-numeric gameId string removed; bounded integer provenance retained")
            ok(scalar("SELECT watcher_id='private-watcher' OR session_id='private-session' FROM aoe2war_library_watcher_public.batch_receipts",web) == "f",
               "raw watcher and session identifiers not projected")
            for table in ("user_activity_events","watcher_client_events","financial_escrow_test"):
                n=psql(f"SELECT * FROM public.{table}",as_user=web,check=False)
                ok(n.returncode != 0 and "permission denied" in n.stderr,
                   f"direct web SELECT denied on {table}")
            n=psql("INSERT INTO aoe2war_library_activity_public.replay_uploads(id) VALUES (99)",as_user=web,check=False)
            ok(n.returncode != 0 and "permission denied" in n.stderr, "no writable view privilege")
            psql(file=INVERSE)
            ok(scalar(snapshot) == before, "no-CASCADE inverse restores original raw relacl and attacl")
            ok(scalar("SELECT to_regnamespace('aoe2war_library_activity_public') IS NULL AND to_regnamespace('aoe2war_library_watcher_public') IS NULL") == "t",
               "inverse removed new schemas without CASCADE")
            ok(scalar("SELECT count(*) FROM public.user_activity_events") == "3" and
               scalar("SELECT count(*) FROM public.watcher_client_events") == "5",
               "original synthetic event history intact")
        finally:
            if started:
                call(PG / "pg_ctl", "-D", data, "-m", "immediate", "-w", "stop", check=False)
    print(f"C03_LIBRARY_HD_OWNER_REAL_PG16_PASS {len(checks)}/{len(checks)} "
          "synthetic SOURCE_ONLY no_HEL1_SQL no_financial_admission")


if __name__ == "__main__":
    main()

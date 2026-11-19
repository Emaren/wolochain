#!/usr/bin/env python3
"""WE1: real PgBouncer + PostgreSQL16 on synthetic ephemeral sockets only.

Never accepts a pre-existing PGDATA, socket, DSN, systemd unit, or production role.
Not a financial host attestor, permit, or production maintenance controller.
"""
import getpass
import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import tempfile
import time

PG = pathlib.Path("/usr/lib/postgresql/16/bin")
POOL = pathlib.Path("/usr/sbin/pgbouncer")
SENTINEL = "WE1_POOL_END"


def run(args, expected=True, timeout=35):
    p = subprocess.run([str(x) for x in args], capture_output=True, text=True, timeout=timeout)
    if (p.returncode == 0) != expected:
        raise AssertionError("unexpected command result: " + repr(args) + " " + p.stderr[-900:])
    return p


def require(ok, reason):
    if not ok:
        raise AssertionError(reason)


def read_psql(proc, sql):
    proc.stdin.write(sql + "\n\\echo " + SENTINEL + "\n")
    proc.stdin.flush()
    lines = []
    for _ in range(30):
        line = proc.stdout.readline()
        require(bool(line), "pooled client exited: " + str(lines))
        lines.append(line.strip())
        if SENTINEL in line:
            return "\n".join(lines)
    raise AssertionError("pooled client no sentinel")


def main():
    require(os.environ.get("WE1_C03_DISPOSABLE_POOL_ONLY") == "1", "EXPLICIT_DISPOSABLE_POOL_OPTIN_REQUIRED")
    require(os.geteuid() != 0, "ROOT_IS_NOT_A_DISPOSABLE_TEST_CLIENT")
    require(POOL.is_file() and all((PG / n).is_file() for n in ("initdb", "pg_ctl", "psql", "postgres")), "MISSING_REAL_PG16_OR_PGBOUNCER")
    require("16" in run([PG / "postgres", "--version"]).stdout, "NOT_POSTGRESQL16")
    checks = []
    def passed(name, condition):
        require(condition, name)
        checks.append(name)
    with tempfile.TemporaryDirectory(prefix="we1-c03-pg16-pool-") as tmp:
        root = pathlib.Path(tmp)
        cluster = root / "new_cluster"
        socket = root / "private_socket"
        socket.mkdir(mode=0o700)
        owner = getpass.getuser()
        port = 51000 + os.getpid() % 9000
        pool_port = port + 10000
        init = run([PG / "initdb", "-D", cluster, "--no-sync", "--auth-local=trust", "--auth-host=reject"])
        passed("new PG16 cluster created under private temporary PGDATA", (cluster / "PG_VERSION").read_text().strip() == "16")
        hba = cluster / "pg_hba.conf"
        original = hba.read_bytes()
        hba_hash = hashlib.sha256(original).hexdigest()
        pgopts = "-c listen_addresses= -c unix_socket_directories=" + str(socket) + " -c port=" + str(port)
        def ctl(*args, expected=True):
            return run([PG / "pg_ctl", "-D", cluster, *args], expected=expected)
        def startpg():
            ctl("-o", pgopts, "-w", "-l", root / "pg.log", "start")
        def stoppg():
            ctl("-m", "immediate", "-w", "stop")
        def sql(s):
            return run([PG / "psql", "-X", "-A", "-t", "-v", "ON_ERROR_STOP=1", "-h", socket, "-p", port,
                        "-U", owner, "-d", "postgres", "-c", s]).stdout.strip()
        started = False
        pool = None
        client = None
        plog = None
        try:
            startpg()
            started = True
            sql("CREATE ROLE c03_pool_owner NOLOGIN NOINHERIT; CREATE ROLE c03_pool_writer LOGIN NOINHERIT;")
            sql("CREATE TABLE public.c03_pool_finance(id serial PRIMARY KEY, val integer NOT NULL);"
                "ALTER TABLE public.c03_pool_finance OWNER TO c03_pool_owner;"
                "ALTER SEQUENCE public.c03_pool_finance_id_seq OWNER TO c03_pool_owner;"
                "GRANT SELECT,INSERT,UPDATE,DELETE ON public.c03_pool_finance TO c03_pool_writer;"
                "GRANT USAGE,UPDATE ON SEQUENCE public.c03_pool_finance_id_seq TO c03_pool_writer;")
            sql("CREATE FUNCTION public.c03_pool_definer() RETURNS void LANGUAGE sql SECURITY DEFINER AS $$ "
                "INSERT INTO public.c03_pool_finance(val) VALUES (777); $$;"
                "ALTER FUNCTION public.c03_pool_definer() OWNER TO c03_pool_owner;"
                "REVOKE EXECUTE ON FUNCTION public.c03_pool_definer() FROM PUBLIC;"
                "GRANT EXECUTE ON FUNCTION public.c03_pool_definer() TO c03_pool_owner,c03_pool_writer;")
            preimage = sql("SELECT rolcanlogin::text FROM pg_roles WHERE rolname='c03_pool_writer';"
                           "SELECT relacl::text FROM pg_class WHERE oid='public.c03_pool_finance'::regclass;"
                           "SELECT relacl::text FROM pg_class WHERE oid='public.c03_pool_finance_id_seq'::regclass;"
                           "SELECT proacl::text FROM pg_proc WHERE oid='public.c03_pool_definer()'::regprocedure")
            config = root / "pgbouncer.ini"
            auth = root / "users.txt"
            auth.write_text('"c03_pool_writer" ""\n"' + owner + '" ""\n')
            config.write_text(
                "[databases]\npostgres = host=" + str(socket) + " port=" + str(port) + " dbname=postgres\n\n"
                "[pgbouncer]\nlisten_addr =\nlisten_port = " + str(pool_port) + "\nunix_socket_dir = " + str(socket) + "\n"
                "auth_type = trust\nauth_file = " + str(auth) + "\npool_mode = session\n"
                "max_client_conn = 12\ndefault_pool_size = 4\nserver_login_retry = 1\n"
                "server_connect_timeout = 3\nquery_timeout = 4\n"
                "logfile = " + str(root / "pgbouncer.log") + "\npidfile = " + str(root / "pgbouncer.pid") + "\n")
            def startpool():
                nonlocal pool, plog
                plog = (root / "pgbouncer-stdout.log").open("a")
                pool = subprocess.Popen([str(POOL), str(config)], stdout=plog, stderr=subprocess.STDOUT)
                for _ in range(80):
                    if (socket / (".s.PGSQL." + str(pool_port))).exists():
                        return
                    require(pool.poll() is None, "PgBouncer exited early: " + (root / "pgbouncer.log").read_text()[-800:] if (root / "pgbouncer.log").exists() else "PgBouncer early exit")
                    time.sleep(0.1)
                raise AssertionError("PgBouncer never created its real private socket")
            def stoppool():
                nonlocal pool, plog
                if pool is not None:
                    pool.terminate()
                    try:
                        pool.wait(timeout=6)
                    except subprocess.TimeoutExpired:
                        pool.kill()
                        pool.wait(timeout=6)
                    pool = None
                if plog is not None:
                    plog.close()
                    plog = None
            def pool_cmd(query, expected=True):
                return run([PG / "psql", "-X", "-A", "-t", "-v", "ON_ERROR_STOP=1", "-h", socket,
                            "-p", pool_port, "-U", "c03_pool_writer", "-d", "postgres", "-c", query], expected=expected, timeout=15)
            startpool()
            passed("real PgBouncer unix socket and session pool startup", pool is not None and pool.poll() is None)
            client = subprocess.Popen([str(PG / "psql"), "-X", "-q", "-A", "-t", "-v", "ON_ERROR_STOP=0",
                                       "-h", str(socket), "-p", str(pool_port), "-U", "c03_pool_writer",
                                       "-d", "postgres"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                      stderr=subprocess.STDOUT, text=True, bufsize=1)
            backend = read_psql(client, "SELECT pg_backend_pid();").splitlines()[0]
            passed("pooled session backed by actual PostgreSQL backend PID", backend.isdigit())
            initial = read_psql(client, "INSERT INTO public.c03_pool_finance(val) VALUES (11);"
                                           "SELECT count(*) FROM public.c03_pool_finance WHERE val=11;")
            passed("existing pool client committed synthetic write", "ERROR" not in initial and "1" in initial.splitlines())
            deny = b"local all all reject\nlocal replication all reject\nhost all all 0.0.0.0/0 reject\nhost all all ::/0 reject\n"
            hba.write_bytes(deny)
            ctl("reload")
            direct = run([PG / "psql", "-X", "-h", socket, "-p", port, "-U", owner, "-d", "postgres", "-c", "SELECT 1"], expected=False)
            passed("all-reject HBA reload denies a new real direct client", "reject" in direct.stderr.lower() or "pg_hba" in direct.stderr.lower())
            still = read_psql(client, "INSERT INTO public.c03_pool_finance(val) VALUES (12);"
                                           "SELECT count(*) FROM public.c03_pool_finance WHERE val=12;")
            passed("existing real PgBouncer session survives HBA reload and commits", "ERROR" not in still and "1" in still.splitlines())
            hba.write_bytes(original)
            ctl("reload")
            sql("ALTER ROLE c03_pool_writer NOLOGIN; REVOKE ALL ON public.c03_pool_finance FROM c03_pool_writer;"
                "REVOKE ALL ON SEQUENCE public.c03_pool_finance_id_seq FROM c03_pool_writer;"
                "REVOKE EXECUTE ON FUNCTION public.c03_pool_definer() FROM c03_pool_writer;")
            denied = [read_psql(client, q) for q in (
                "INSERT INTO public.c03_pool_finance(val) VALUES (13);",
                "SELECT nextval('public.c03_pool_finance_id_seq');",
                "SELECT public.c03_pool_definer();")]
            passed("preconnected pooler loses table sequence and SECURITY DEFINER authority", all("ERROR" in x for x in denied))
            passed("denied PgBouncer session retained same physical backend", backend in read_psql(client, "SELECT pg_backend_pid();").splitlines())
            client.terminate()
            try:
                client.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                client.kill()
                client.communicate()
            client = None
            stoppool()
            stoppg()
            started = False
            hba.write_bytes(deny)
            startpg()
            started = True
            blocked = run([PG / "psql", "-X", "-h", socket, "-p", port, "-U", owner, "-d", "postgres", "-c", "SELECT 1"], expected=False)
            passed("all-reject HBA startup denial survives full postmaster restart", "reject" in blocked.stderr.lower() or "pg_hba" in blocked.stderr.lower())
            startpool()
            failed_pool = pool_cmd("SELECT 1;", expected=False)
            passed("new real PgBouncer cannot obtain backend under restarted deny HBA", failed_pool.returncode != 0)
            stoppool()
            stoppg()
            started = False
            hba.write_bytes(original)
            startpg()
            started = True
            passed("HBA original physical preimage restored byte-for-byte", hashlib.sha256(hba.read_bytes()).hexdigest() == hba_hash)
            sql("ALTER ROLE c03_pool_writer LOGIN; GRANT SELECT,INSERT,UPDATE,DELETE ON public.c03_pool_finance TO c03_pool_writer;"
                "GRANT USAGE,UPDATE ON SEQUENCE public.c03_pool_finance_id_seq TO c03_pool_writer;"
                "GRANT EXECUTE ON FUNCTION public.c03_pool_definer() TO c03_pool_writer;")
            inverse = sql("SELECT rolcanlogin::text FROM pg_roles WHERE rolname='c03_pool_writer';"
                           "SELECT relacl::text FROM pg_class WHERE oid='public.c03_pool_finance'::regclass;"
                           "SELECT relacl::text FROM pg_class WHERE oid='public.c03_pool_finance_id_seq'::regclass;"
                           "SELECT proacl::text FROM pg_proc WHERE oid='public.c03_pool_definer()'::regprocedure")
            passed("synthetic raw role table sequence and function ACL inverse matches exactly", inverse == preimage)
            startpool()
            positive = pool_cmd("INSERT INTO public.c03_pool_finance(val) VALUES (14);")
            passed("restored pooler returns only original synthetic writer capability", positive.returncode == 0)
            stoppool()
            print(json.dumps({"status": "PASS", "postgres": "16", "real_pgbouncer": True, "pool_mode": "session",
                              "case_count": len(checks), "checks": checks, "tcp_listening": False,
                              "ephemeral_cluster": True, "hba_original_sha256": hba_hash,
                              "hba_deny_sha256": hashlib.sha256(deny).hexdigest()}, sort_keys=True))
        finally:
            if client is not None:
                client.terminate()
                try:
                    client.communicate(timeout=3)
                except subprocess.TimeoutExpired:
                    client.kill()
                    client.communicate()
            stoppool()
            if started:
                ctl("-m", "immediate", "-w", "stop", expected=True)


if __name__ == "__main__":
    main()

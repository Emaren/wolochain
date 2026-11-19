#!/usr/bin/env python3
"""Real disposable PG16 negative proof: SECURITY DEFINER installer ownership and PUBLIC pseudo-role.

Source-only counterexample; not WE3 installer execution or live financial finding.
"""
import json
import os
import pathlib
import subprocess
import tempfile

PG = pathlib.Path("/usr/lib/postgresql/16/bin")


def run(parts, expected=True):
    p = subprocess.run([str(z) for z in parts], capture_output=True, text=True, timeout=30)
    if (p.returncode == 0) != expected:
        raise AssertionError("unexpected exit " + repr(parts) + "\n" + p.stderr[-700:])
    return p


def main():
    if os.environ.get("C03_DISPOSABLE_OWNER_PUBLIC_ONLY") != "1":
        raise RuntimeError("C03_DISPOSABLE_OWNER_PUBLIC_OPTIN_REQUIRED")
    if os.geteuid() == 0 or not all((PG / x).exists() for x in ("postgres", "initdb", "pg_ctl", "psql")):
        raise RuntimeError("C03_REQUIRES_NONROOT_REAL_PG16")
    checks = []
    def check(v, label):
        if not v:
            raise AssertionError(label)
        checks.append(label)
    with tempfile.TemporaryDirectory(prefix="c03-owner-public-proof-") as tmp:
        root = pathlib.Path(tmp)
        sock = root / "sock"
        sock.mkdir(mode=0o700)
        data = root / "pgdata"
        port = 44000 + os.getpid() % 7000
        run([PG / "initdb", "-D", data, "--no-sync", "--auth-local=trust", "--auth-host=reject"])
        started = False
        def psql(stmt, expected=True):
            return run([PG / "psql", "-X", "-A", "-t", "-v", "ON_ERROR_STOP=1",
                        "-h", sock, "-p", port, "-d", "postgres", "-c", stmt],expected)
        try:
            run([PG / "pg_ctl", "-D", data, "-o", "-c listen_addresses= -c unix_socket_directories="
                 + str(sock) + " -c port=" + str(port),
                 "-w", "-l", root / "pg.log", "start"])
            started = True
            check(psql("SHOW server_version_num").stdout.strip().startswith("16"),
                  "real PG16 private socket only")
            psql("""CREATE ROLE c03_legacy_nonfinancial NOLOGIN NOINHERIT NOSUPERUSER;
              CREATE ROLE c03_unprivileged LOGIN NOINHERIT NOSUPERUSER;
              CREATE ROLE c03_writer LOGIN NOINHERIT NOSUPERUSER;
              CREATE TABLE public.c03_legacy_social(id serial PRIMARY KEY,body text);
              ALTER TABLE public.c03_legacy_social OWNER TO c03_legacy_nonfinancial;""")
            original=psql("SELECT relacl::text FROM pg_class WHERE oid='public.c03_legacy_social'::regclass").stdout.strip()
            check(original=="", "legacy raw ACL starts NULL")
            psql("""CREATE SCHEMA social_gateway_v1;
              CREATE VIEW social_gateway_v1.visible_social AS
              SELECT id,body FROM public.c03_legacy_social;
              CREATE FUNCTION social_gateway_v1.append_demo(msg text)
              RETURNS integer LANGUAGE plpgsql SECURITY DEFINER
              SET search_path=pg_catalog,pg_temp AS $fn$
              DECLARE new_id integer;
              BEGIN
                INSERT INTO public.c03_legacy_social(body) VALUES(msg) RETURNING id INTO new_id;
                RETURN new_id;
              END $fn$;
              REVOKE ALL ON FUNCTION social_gateway_v1.append_demo(text) FROM PUBLIC;
              GRANT USAGE ON SCHEMA social_gateway_v1 TO c03_writer;
              GRANT EXECUTE ON FUNCTION social_gateway_v1.append_demo(text) TO c03_writer;""")
            result=psql("""SELECT (SELECT rolsuper FROM pg_roles r
                    JOIN pg_proc p ON p.proowner=r.oid
                    WHERE p.oid='social_gateway_v1.append_demo(text)'::regprocedure),
                    (SELECT r.rolsuper FROM pg_roles r JOIN pg_namespace n
                     ON n.nspowner=r.oid WHERE n.nspname='social_gateway_v1'),
                    (SELECT r.rolsuper FROM pg_roles r JOIN pg_class c
                     ON c.relowner=r.oid WHERE c.oid='social_gateway_v1.visible_social'::regclass)""").stdout.strip()
            check(result=="t|t|t",
                  "unqualified CREATE by cluster admin gives SECURITY DEFINER function schema and view superuser ownership")
            check(psql("SELECT relacl::text FROM pg_class WHERE oid='public.c03_legacy_social'::regclass").stdout.strip()==original,
                  "elevated owner did not alter original raw ACL despite elevated capabilities")
            failed=psql("SELECT has_function_privilege('public','social_gateway_v1.append_demo(text)','EXECUTE')",False)
            check("role \"public\" does not exist" in failed.stderr.lower(),
                  "has_function_privilege rejects PUBLIC pseudo-role as an actual role")
            correct=psql("SELECT has_function_privilege('c03_unprivileged','social_gateway_v1.append_demo(text)','EXECUTE')").stdout.strip()
            check(correct=="f","actual unprivileged role cannot EXECUTE protected function")
            allowed=psql("SELECT has_function_privilege('c03_writer','social_gateway_v1.append_demo(text)','EXECUTE')").stdout.strip()
            check(allowed=="t","exact social writer principal can EXECUTE protected function")
            print(json.dumps({"status":"PASS","postgres":"16","case_count":len(checks),
                              "checks":checks,"source_only":True,"finance_host_touched":False},
                             sort_keys=True))
        finally:
            if started:
                run([PG / "pg_ctl", "-D", data, "-m", "immediate", "-w", "stop"])


if __name__ == "__main__":
    main()

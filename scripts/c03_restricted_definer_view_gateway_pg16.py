#!/usr/bin/env python3
"""WE1: real disposable PG16 restricted non-login gateway executor experiment.

Prove whether a new simple updatable-view write can execute with a restricted
SECURITY DEFINER owner, while all legacy base objects and serial sequences
remain ungranted and original raw ACLs are byte-identical. This is NEVER an
HEL1 installer, C03 physical witness or financial maintenance permit.

Synthetic worst case: broad legacy owner also owns financial wagers, and
ON DELETE CASCADE exists from financial wager to users. Does not claim
that view rewriting removes all privileged view-owner/trigger risks.
"""
from __future__ import annotations
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import tempfile

PG = Path("/usr/lib/postgresql/16/bin")


def run(argv, success=True):
    p = subprocess.run([str(s) for s in argv], capture_output=True,
                       text=True, timeout=35)
    if (p.returncode == 0) != success:
        raise AssertionError(f"wrong status {argv!r}; {p.stderr[-800:]}")
    return p


def main():
    if os.environ.get("C03_RESTRICTED_VIEW_GATEWAY_DISPOSABLE_ONLY") != "1":
        raise RuntimeError("C03_RESTRICTED_GATEWAY_EXPLICIT_OPTIN_REQUIRED")
    if os.geteuid() == 0 or not all((PG / x).is_file()
                                    for x in ("postgres", "initdb", "pg_ctl", "psql")):
        raise RuntimeError("C03_REQUIRES_NONROOT_REAL_PG16")
    checks = []
    def check(value, name):
        if not value:
            raise AssertionError(name)
        checks.append(name)
    with tempfile.TemporaryDirectory(prefix="we1-c03-restricted-view-pg16-") as tmp:
        root = Path(tmp)
        socket = root / "socket"
        socket.mkdir(mode=0o700)
        pgdata = root / "pgdata"
        port = 44000 + os.getpid() % 8000
        run([PG / "initdb", "-D", pgdata, "--no-sync",
             "--auth-local=trust", "--auth-host=reject"])
        started = False
        def sql(q, role=None, success=True):
            a=[PG / "psql", "-X", "-A", "-t", "-v", "ON_ERROR_STOP=1",
               "-h", socket, "-p", port, "-d", "postgres"]
            if role: a.extend(("-U",role))
            return run(a + ["-c", q], success=success).stdout.strip()
        try:
            run([PG / "pg_ctl", "-D", pgdata,
                 "-o", "-c listen_addresses= -c unix_socket_directories="
                       +str(socket)+" -c port="+str(port),
                 "-w", "-l", root/"pg.log", "start"])
            started=True
            check(sql("SHOW server_version_num").startswith("16"),
                  "fresh real PG16 without TCP listening")
            sql("""
CREATE ROLE c03_broad_legacy_owner NOLOGIN NOINHERIT NOSUPERUSER;
CREATE ROLE c03_narrow_executor NOLOGIN NOINHERIT NOSUPERUSER
 NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
CREATE ROLE c03_social_writer LOGIN NOINHERIT NOSUPERUSER
 NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
CREATE TABLE public.users(id serial PRIMARY KEY,uid text UNIQUE NOT NULL);
CREATE TABLE public.clan_messages(id serial PRIMARY KEY,
 author_user_id integer REFERENCES public.users(id),body text NOT NULL);
CREATE TABLE public.bet_wagers(id serial PRIMARY KEY,
 user_id integer REFERENCES public.users(id) ON DELETE CASCADE,
 stake integer NOT NULL);
ALTER TABLE public.users OWNER TO c03_broad_legacy_owner;
ALTER TABLE public.clan_messages OWNER TO c03_broad_legacy_owner;
ALTER TABLE public.bet_wagers OWNER TO c03_broad_legacy_owner;
ALTER SEQUENCE public.users_id_seq OWNER TO c03_broad_legacy_owner;
ALTER SEQUENCE public.clan_messages_id_seq OWNER TO c03_broad_legacy_owner;
ALTER SEQUENCE public.bet_wagers_id_seq OWNER TO c03_broad_legacy_owner;
INSERT INTO public.users(id,uid) VALUES (1,'scribe'),(2,'cascade-demo');
INSERT INTO public.bet_wagers(user_id,stake) VALUES(1,900),(2,800);
""")
            acl="""SELECT relname||'='||coalesce(relacl::text,'<NULL>') FROM pg_class
                WHERE relnamespace='public'::regnamespace
                  AND relname IN ('users','clan_messages','bet_wagers',
                    'users_id_seq','clan_messages_id_seq','bet_wagers_id_seq')
                ORDER BY relname"""
            original=sql(acl)
            check(len(original.splitlines())==6 and
                  all(v.endswith("<NULL>") for v in original.splitlines()),
                  "six original financial and social table/sequence raw ACLs are NULL")
            check(sql("""SELECT count(*) FROM pg_constraint
              WHERE conrelid='public.bet_wagers'::regclass AND
               confrelid='public.users'::regclass AND confdeltype='c'""")=="1",
                  "genuine financial ON DELETE CASCADE to broad-owned users")
            sql("""
CREATE SCHEMA c03_gateway AUTHORIZATION c03_broad_legacy_owner;
-- The legacy owner still backs simple updatable views.
CREATE VIEW c03_gateway.user_identity WITH (security_barrier=true) AS
 SELECT id,uid FROM public.users;
CREATE VIEW c03_gateway.message_history WITH (security_barrier=true) AS
 SELECT id,author_user_id,body FROM public.clan_messages;
ALTER VIEW c03_gateway.user_identity OWNER TO c03_broad_legacy_owner;
ALTER VIEW c03_gateway.message_history OWNER TO c03_broad_legacy_owner;
GRANT USAGE ON SCHEMA c03_gateway TO c03_narrow_executor,c03_social_writer;
GRANT SELECT ON c03_gateway.user_identity TO c03_narrow_executor;
GRANT SELECT ON c03_gateway.message_history TO c03_narrow_executor;
-- The serial default on an updatable view still checks executor sequence USAGE.
-- Keep all original sequence ACL bytes by limiting the broad owner to a single
-- fixed insert-only leaf, callable ONLY by the restricted NOLOGIN executor.
CREATE FUNCTION c03_gateway.leaf_append_clan(p_author integer,p_body text)
RETURNS integer LANGUAGE plpgsql SECURITY DEFINER
SET search_path=pg_catalog,pg_temp AS $leaf$
DECLARE result_id integer;
BEGIN
 IF p_author IS NULL OR p_body IS NULL OR length(btrim(p_body))=0
    OR length(p_body)>1200 THEN RAISE EXCEPTION 'DENIED_LEAF_REQUEST'; END IF;
 INSERT INTO public.clan_messages(author_user_id,body)
 VALUES(p_author,p_body) RETURNING id INTO result_id;
 RETURN result_id;
END $leaf$;
ALTER FUNCTION c03_gateway.leaf_append_clan(integer,text)
 OWNER TO c03_broad_legacy_owner;
REVOKE ALL ON FUNCTION c03_gateway.leaf_append_clan(integer,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION c03_gateway.leaf_append_clan(integer,text)
 TO c03_narrow_executor;
CREATE FUNCTION c03_gateway.send_clan(p_uid text,p_body text)
RETURNS integer LANGUAGE plpgsql SECURITY DEFINER
SET search_path=pg_catalog,pg_temp AS $fn$
DECLARE actor integer; msg_id integer;
BEGIN
 IF p_uid IS NULL OR p_body IS NULL OR length(btrim(p_body))=0
    OR length(p_body)>1200 THEN RAISE EXCEPTION 'INVALID_SOCIAL_WRITE'; END IF;
 SELECT id INTO actor FROM c03_gateway.user_identity WHERE uid=p_uid;
 IF NOT FOUND THEN RAISE EXCEPTION 'INVALID_ACTOR'; END IF;
 SELECT c03_gateway.leaf_append_clan(actor,p_body) INTO msg_id;
 RETURN msg_id;
END $fn$;
-- Installer may have elevated privileges, but MUST NOT own definer function.
GRANT CREATE ON SCHEMA c03_gateway TO c03_narrow_executor;
ALTER FUNCTION c03_gateway.send_clan(text,text) OWNER TO c03_narrow_executor;
REVOKE CREATE ON SCHEMA c03_gateway FROM c03_narrow_executor;
REVOKE ALL ON FUNCTION c03_gateway.send_clan(text,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION c03_gateway.send_clan(text,text) TO c03_social_writer;
""")
            check(original==sql(acl),
                  "installation changes zero original table or sequence raw ACLs")
            check(sql("""SELECT r.rolsuper::text||'|'||r.rolcanlogin::text
               FROM pg_proc p JOIN pg_roles r ON r.oid=p.proowner
               WHERE p.oid='c03_gateway.send_clan(text,text)'::regprocedure""")=="false|false",
                  "SECURITY DEFINER owner is nonlogin nonsuperuser narrow executor")
            check(sql("""SELECT r.rolsuper::text FROM pg_roles r
                 JOIN pg_class c ON c.relowner=r.oid
                 WHERE c.oid='c03_gateway.message_history'::regclass""")=="false",
                  "new base-backed view owner is not superuser")
            check(sql("SELECT has_schema_privilege('c03_narrow_executor','c03_gateway','CREATE')")=="f",
                  "function executor cannot CREATE new gateway objects")
            check(sql("SELECT count(*) FROM pg_auth_members WHERE member='c03_narrow_executor'::regrole")=="0",
                  "function executor has no inherited or SET ROLE membership")
            check(sql("SELECT has_table_privilege('c03_narrow_executor','public.users','DELETE')")=="f",
                  "executor cannot DELETE users (financial cascade path)")
            check(sql("SELECT has_table_privilege('c03_narrow_executor','public.bet_wagers','UPDATE')")=="f",
                  "executor cannot UPDATE financial table")
            check(sql("SELECT has_table_privilege('c03_narrow_executor','public.clan_messages','INSERT')")=="f",
                  "executor cannot direct INSERT original social table")
            check(sql("SELECT has_sequence_privilege('c03_narrow_executor','public.clan_messages_id_seq','USAGE')")=="f",
                  "executor has no direct original serial USAGE")
            check(sql("SELECT has_table_privilege('c03_narrow_executor','c03_gateway.message_history','SELECT')")=="t",
                  "executor may SELECT only from new narrow social view")
            check(sql("SELECT has_table_privilege('c03_narrow_executor','c03_gateway.message_history','INSERT')")=="f",
                  "executor cannot directly INSERT social view")
            check(sql("SELECT has_function_privilege('c03_narrow_executor','c03_gateway.leaf_append_clan(integer,text)','EXECUTE')")=="t",
                  "narrow executor may invoke fixed insert-only privileged leaf")
            check(sql("SELECT has_function_privilege('c03_social_writer','c03_gateway.leaf_append_clan(integer,text)','EXECUTE')")=="f",
                  "raw social writer cannot invoke privileged leaf directly")
            check(sql("SELECT has_table_privilege('c03_social_writer','c03_gateway.message_history','SELECT')")=="f",
                  "raw social writer cannot SELECT underlying social view")
            check(sql("SELECT has_function_privilege('public','c03_gateway.send_clan(text,text)','EXECUTE')")=="f",
                  "PUBLIC has no EXECUTE")
            check(sql("SELECT c03_gateway.send_clan('scribe','first restricted social text')",
                      role="c03_social_writer")=="1",
                  "restricted definer inserted through insert-only privileged leaf without sequence grant")
            check(sql("SELECT body FROM public.clan_messages WHERE id=1")=="first restricted social text",
                  "original social message persisted")
            # This negative MUST NOT delete original users or financial bets.
            denied=sql("SET ROLE c03_narrow_executor; DELETE FROM public.users WHERE id=1",
                       success=False)
            check(sql("SELECT count(*) FROM public.bet_wagers")=="2",
                  "direct user DELETE by narrow executor denied and financial rows intact")
            denied=sql("SET ROLE c03_social_writer; INSERT INTO public.bet_wagers(user_id,stake) VALUES(1,1)",
                       success=False)
            check(sql("SELECT count(*) FROM public.bet_wagers")=="2",
                  "writer direct financial INSERT denied")
            check(original==sql(acl),
                  "real social write preserves all six original raw ACLs")
            # Explicitly demonstrate that the broad legacy owner is different:
            # it can delete user2 and PostgreSQL cascades a financial wager.
            sql("SET ROLE c03_broad_legacy_owner; DELETE FROM public.users WHERE id=2")
            check(sql("SELECT count(*) FROM public.bet_wagers")=="1",
                  "broad legacy owner CAN trigger financial ON DELETE CASCADE")
            check(sql("SELECT count(*) FROM public.users WHERE id=1")=="1",
                  "restricted writer's original sender remains present")
            # Drop only newly added objects. No REVOKE on original relations.
            sql("""
REVOKE EXECUTE ON FUNCTION c03_gateway.send_clan(text,text) FROM c03_social_writer;
DROP FUNCTION c03_gateway.send_clan(text,text) RESTRICT;
REVOKE EXECUTE ON FUNCTION c03_gateway.leaf_append_clan(integer,text) FROM c03_narrow_executor;
DROP FUNCTION c03_gateway.leaf_append_clan(integer,text) RESTRICT;
REVOKE SELECT ON c03_gateway.user_identity FROM c03_narrow_executor;
REVOKE SELECT ON c03_gateway.message_history FROM c03_narrow_executor;
DROP VIEW c03_gateway.user_identity,c03_gateway.message_history RESTRICT;
REVOKE USAGE ON SCHEMA c03_gateway FROM c03_narrow_executor,c03_social_writer;
DROP SCHEMA c03_gateway RESTRICT;
DROP ROLE c03_social_writer;
DROP ROLE c03_narrow_executor;
""")
            check(original==sql(acl),
                  "exact inverse restores original raw social and finance ACLs")
            check(sql("SELECT to_regnamespace('c03_gateway') IS NULL")=="t",
                  "inverse removed entire new-only schema")
            check(sql("""SELECT count(*) FROM pg_roles WHERE rolname IN
                   ('c03_narrow_executor','c03_social_writer')""")=="0",
                  "inverse dropped only new executor and writer roles")
            check(sql("SELECT count(*) FROM public.clan_messages")=="1",
                  "inverse preserves committed social message")
            check(sql("SELECT count(*) FROM public.bet_wagers")=="1",
                  "inverse has no further financial effects")
            print(json.dumps({
                "status":"PASS","pg_major":16,"case_count":len(checks),
                "checks":checks,"private_pgdata":True,"no_tcp":True,
                "restricted_definer_owner":True,"original_acl_sha256":
                sha256(original.encode()).hexdigest(),"finance_host_touched":False,
                "only_disposable_synthetic_financial_rows_modified":True,
                "not_production_admission":True
            },sort_keys=True))
        finally:
            if started:
                run([PG/"pg_ctl","-D",pgdata,"-m","immediate","-w","stop"])


if __name__ == "__main__":
    main()

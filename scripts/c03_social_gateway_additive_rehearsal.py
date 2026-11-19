#!/usr/bin/env python3
"""C03 experiment: additive SECURITY DEFINER social gateway, real disposable PG16 only.

Not a production installer, privilege manifest, actual WE3-compatible endpoint,
owner attestation or evidence of financial noninterference on HEL1.
"""
import getpass
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile

PG = Path(os.environ.get("WE1_C03_PG16_BIN", "/usr/lib/postgresql/16/bin"))
TABLES = ("clan_messages", "direct_conversations",
          "direct_conversation_participants", "direct_messages")
LEGACY_ACL = ("clan_messages_id_seq", "direct_conversations_id_seq",
              "direct_conversation_participants_id_seq",
              "direct_messages_id_seq", "direct_message_drafts")
FUNCTIONS = ("clan_send(integer,integer,text,text)",
             "direct_open(integer,integer)",
             "direct_add_participant(integer,integer)",
             "direct_send(integer,integer,text)",
             "clear_draft(integer,integer)")


def call(args, success=True):
    p = subprocess.run([str(a) for a in args], capture_output=True, text=True, timeout=25)
    if (p.returncode == 0) != success:
        raise AssertionError("command exit mismatch " + repr(args) + " " + p.stderr[-650:])
    return p


def main():
    if os.environ.get("WE1_C03_DISPOSABLE_GATEWAY_ONLY") != "1":
        raise RuntimeError("EXPLICIT_DISPOSABLE_SOCIAL_GATEWAY_OPTIN_REQUIRED")
    if os.geteuid() == 0 or not all((PG / p).is_file() for p in
                                     ("initdb", "pg_ctl", "postgres", "psql")):
        raise RuntimeError("NEED_NONROOT_REAL_POSTGRES16_BINARIES")
    checks = []
    def ok(condition, name):
        if not condition:
            raise AssertionError(name)
        checks.append(name)
    with tempfile.TemporaryDirectory(prefix="we1-c03-additive-gateway-") as rootstr:
        root = Path(rootstr)
        sock = root / "socket"
        sock.mkdir(mode=0o700)
        data = root / "pgdata"
        port = 45000 + os.getpid() % 7000
        user = getpass.getuser()
        call([PG / "initdb", "-D", data, "--no-sync", "--auth-local=trust", "--auth-host=reject"])
        started = False
        def query(statement, role=user, success=True):
            return call([PG / "psql", "-X", "-A", "-t", "-v", "ON_ERROR_STOP=1",
                         "-U", role, "-h", sock, "-p", port, "-d", "postgres",
                         "-c", statement], success=success).stdout.strip()
        try:
            call([PG / "pg_ctl", "-D", data,
                  "-o", "-c listen_addresses= -c unix_socket_directories=" + str(sock) +
                  " -c port=" + str(port), "-w", "-l", root / "pg.log", "start"])
            started = True
            ok(query("SHOW server_version_num").startswith("16"),
               "real PG16 private socket no network listener")
            query("""
CREATE ROLE c03_legacy_owner NOLOGIN NOINHERIT;
CREATE ROLE c03_finance_owner NOLOGIN NOINHERIT;
CREATE ROLE c03_gateway_owner NOLOGIN NOINHERIT;
CREATE ROLE c03_social_writer LOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
CREATE TABLE public.users(id integer PRIMARY KEY, uid text UNIQUE, wallet_balance numeric);
CREATE TABLE public.clan_members(clan_id integer, user_id integer, status text);
CREATE TABLE public.clan_messages(id serial PRIMARY KEY,clan_id integer,author_user_id integer,body text,audience text,created_at timestamptz,updated_at timestamptz);
CREATE TABLE public.direct_conversations(id serial PRIMARY KEY,pair_key text UNIQUE,created_at timestamptz,updated_at timestamptz);
CREATE TABLE public.direct_conversation_participants(id serial PRIMARY KEY,conversation_id integer,user_id integer,joined_at timestamptz,UNIQUE(conversation_id,user_id));
CREATE TABLE public.direct_messages(id serial PRIMARY KEY,conversation_id integer,sender_user_id integer,body text,created_at timestamptz);
CREATE TABLE public.direct_message_drafts(conversation_id integer,user_id integer);
CREATE TABLE public.financial_test_escrow(id serial PRIMARY KEY,amount integer);
ALTER TABLE public.users OWNER TO c03_legacy_owner;
ALTER TABLE public.clan_members OWNER TO c03_legacy_owner;
ALTER TABLE public.clan_messages OWNER TO c03_legacy_owner;
ALTER TABLE public.direct_conversations OWNER TO c03_legacy_owner;
ALTER TABLE public.direct_conversation_participants OWNER TO c03_legacy_owner;
ALTER TABLE public.direct_messages OWNER TO c03_legacy_owner;
ALTER TABLE public.direct_message_drafts OWNER TO c03_legacy_owner;
ALTER TABLE public.financial_test_escrow OWNER TO c03_finance_owner;
INSERT INTO public.users VALUES (1,'sender',1000),(2,'recipient',2000),(3,'outsider',3000);
INSERT INTO public.clan_members VALUES (7,1,'active');
INSERT INTO public.direct_message_drafts VALUES(44,1),(44,2);
""")
            def rawacl():
                return query("""SELECT relname||'='||COALESCE(relacl::text,'<NULL>')
                  FROM pg_class WHERE relnamespace='public'::regnamespace
                  AND relname IN ('clan_messages_id_seq','direct_conversations_id_seq',
                   'direct_conversation_participants_id_seq','direct_messages_id_seq',
                   'direct_message_drafts') ORDER BY relname""")
            before = rawacl()
            ok(len(before.splitlines())==5 and all(x.endswith("<NULL>") for x in before.splitlines()),
               "five original legacy ACLs are genuinely raw NULL")
            # If any unreviewed enabled triggers exist on the actual social DML
            # tables, the candidate MUST refuse admission. Test its negative.
            def enabled_triggers():
                return int(query("""SELECT count(*) FROM pg_trigger
                  WHERE tgenabled IN ('O','A','R') AND NOT tgisinternal
                  AND tgrelid IN (SELECT to_regclass('public.'||x) FROM
                  unnest(ARRAY['clan_messages','direct_conversations',
                  'direct_conversation_participants','direct_messages',
                  'direct_message_drafts']) x)"""))
            ok(enabled_triggers()==0, "no unreviewed enabled user triggers preflight")
            query("""CREATE FUNCTION public.c03_injected_trigger() RETURNS trigger
              LANGUAGE plpgsql SECURITY DEFINER AS $$
              BEGIN INSERT INTO public.financial_test_escrow(amount) VALUES(999); RETURN NEW; END $$;
              ALTER FUNCTION public.c03_injected_trigger() OWNER TO c03_finance_owner;
              CREATE TRIGGER c03_injected AFTER INSERT ON public.clan_messages
              FOR EACH ROW EXECUTE FUNCTION public.c03_injected_trigger();""")
            ok(enabled_triggers()==1, "finance trigger reachability drift forces HOLD preflight")
            query("""DROP TRIGGER c03_injected ON public.clan_messages;
                     DROP FUNCTION public.c03_injected_trigger();""")
            ok(enabled_triggers()==0, "hostile trigger removed from disposable fixture")
            query("""CREATE SCHEMA c03_social_gateway AUTHORIZATION c03_gateway_owner;
GRANT USAGE ON SCHEMA c03_social_gateway TO c03_social_writer,c03_legacy_owner;
CREATE FUNCTION c03_social_gateway.clan_send(actor integer, clan integer, content text, audience text)
RETURNS integer LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE mid integer;
BEGIN
 IF actor<=0 OR length(content)>1200 OR length(btrim(content))=0 OR
    audience NOT IN ('clan','public') OR
    NOT EXISTS(SELECT 1 FROM public.clan_members
               WHERE clan_id=clan AND user_id=actor AND status='active')
 THEN RAISE EXCEPTION 'DENIED_SOCIAL_MEMBERSHIP_OR_INPUT'; END IF;
 INSERT INTO public.clan_messages(clan_id,author_user_id,body,audience,created_at,updated_at)
 VALUES(clan,actor,content,audience,clock_timestamp(),clock_timestamp()) RETURNING id INTO mid;
 RETURN mid;
END $$;
CREATE FUNCTION c03_social_gateway.direct_open(actor integer, recipient integer)
RETURNS integer LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE cid integer; pair text;
BEGIN
 IF actor=recipient OR NOT EXISTS (SELECT 1 FROM public.users WHERE id=actor) OR
    NOT EXISTS (SELECT 1 FROM public.users WHERE id=recipient)
 THEN RAISE EXCEPTION 'INVALID_DIRECT_TARGET'; END IF;
 pair=least(actor,recipient)::text||':'||greatest(actor,recipient)::text;
 INSERT INTO public.direct_conversations(pair_key,created_at,updated_at)
 VALUES(pair,clock_timestamp(),clock_timestamp()) ON CONFLICT(pair_key) DO NOTHING;
 SELECT id INTO cid FROM public.direct_conversations WHERE pair_key=pair;
 RETURN cid;
END $$;
CREATE FUNCTION c03_social_gateway.direct_add_participant(cid integer, who integer)
RETURNS integer LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
BEGIN
 IF NOT EXISTS (SELECT 1 FROM public.direct_conversations WHERE id=cid) OR
    NOT EXISTS (SELECT 1 FROM public.users WHERE id=who)
 THEN RAISE EXCEPTION 'UNKNOWN_PARTICIPANT'; END IF;
 INSERT INTO public.direct_conversation_participants(conversation_id,user_id,joined_at)
 VALUES(cid,who,clock_timestamp()) ON CONFLICT(conversation_id,user_id) DO NOTHING;
 RETURN cid;
END $$;
CREATE FUNCTION c03_social_gateway.direct_send(cid integer, actor integer, content text)
RETURNS integer LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE mid integer;
BEGIN
 IF length(content)>1000 OR length(btrim(content))=0 OR NOT EXISTS (
    SELECT 1 FROM public.direct_conversation_participants
    WHERE conversation_id=cid AND user_id=actor)
 THEN RAISE EXCEPTION 'DENIED_DIRECT_MEMBERSHIP_OR_INPUT'; END IF;
 INSERT INTO public.direct_messages(conversation_id,sender_user_id,body,created_at)
 VALUES(cid,actor,content,clock_timestamp()) RETURNING id INTO mid;
 RETURN mid;
END $$;
CREATE FUNCTION c03_social_gateway.clear_draft(actor integer, cid integer)
RETURNS integer LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE n integer;
BEGIN
 DELETE FROM public.direct_message_drafts WHERE user_id=actor AND conversation_id=cid;
 GET DIAGNOSTICS n=ROW_COUNT;
 RETURN n;
END $$;
ALTER FUNCTION c03_social_gateway.clan_send(integer,integer,text,text) OWNER TO c03_legacy_owner;
ALTER FUNCTION c03_social_gateway.direct_open(integer,integer) OWNER TO c03_legacy_owner;
ALTER FUNCTION c03_social_gateway.direct_add_participant(integer,integer) OWNER TO c03_legacy_owner;
ALTER FUNCTION c03_social_gateway.direct_send(integer,integer,text) OWNER TO c03_legacy_owner;
ALTER FUNCTION c03_social_gateway.clear_draft(integer,integer) OWNER TO c03_legacy_owner;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA c03_social_gateway FROM PUBLIC;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA c03_social_gateway TO c03_social_writer;
""")
            ok(before==rawacl(),
               "additive gateway installation did not alter five legacy raw ACLs")
            ok(query("SELECT count(*) FROM pg_auth_members WHERE member='c03_social_writer'::regrole")=="0",
               "writer has zero inherited or SET ROLE memberships")
            ok(query("SELECT has_schema_privilege('c03_social_writer','public','CREATE')")=="f",
               "social writer cannot CREATE in public schema")
            ok(query("SELECT has_table_privilege('c03_social_writer','public.clan_messages','INSERT')")=="f",
               "legacy base table DML remains denied")
            ok(query("SELECT has_sequence_privilege('c03_social_writer','public.clan_messages_id_seq','USAGE')")=="f",
               "legacy serial sequence access remains denied")
            ok(query("SELECT has_table_privilege('c03_social_writer','public.direct_message_drafts','DELETE')")=="f",
               "legacy draft table DELETE remains denied")
            ok(query("SELECT has_table_privilege('c03_social_writer','public.financial_test_escrow','INSERT')")=="f",
               "financial table direct access denied")
            ok(query("SELECT has_table_privilege('c03_social_writer','public.users','SELECT')")=="f",
               "private users wallet column read denied")
            ok(query("SELECT c03_social_gateway.clan_send(1,7,'real synthetic','clan')",
                     role="c03_social_writer").isdigit(),
               "allowed clan text inserted through fixed definer gateway")
            query("SELECT c03_social_gateway.clan_send(3,7,'outsider','clan')",
                  role="c03_social_writer",success=False)
            ok(query("SELECT count(*) FROM public.clan_messages")=="1",
               "outsider clan message rejected by gateway")
            cid = query("SELECT c03_social_gateway.direct_open(1,2)",role="c03_social_writer")
            ok(cid.isdigit(), "new direct conversation created without legacy sequence GRANT")
            query(f"SELECT c03_social_gateway.direct_add_participant({cid},1)",
                  role="c03_social_writer")
            query(f"SELECT c03_social_gateway.direct_add_participant({cid},2)",
                  role="c03_social_writer")
            ok(query(f"SELECT c03_social_gateway.direct_send({cid},1,'bounded direct text')",
                     role="c03_social_writer").isdigit(),
               "direct message inserted without legacy table or seq grant")
            query(f"SELECT c03_social_gateway.direct_send({cid},3,'outsider')",
                  role="c03_social_writer",success=False)
            ok(query("SELECT count(*) FROM public.direct_messages")=="1",
               "nonparticipant direct send denied")
            ok(query("SELECT c03_social_gateway.clear_draft(1,44)",role="c03_social_writer")=="1",
               "draft cleared via fixed definer without legacy DELETE grant")
            ok(query("SELECT count(*) FROM public.direct_message_drafts WHERE user_id=2")=="1",
               "unrelated recipient draft preserved")
            ok(before==rawacl(), "legacy five ACLs remain raw-byte identical after writes")
            ok(query("SELECT count(*) FROM public.financial_test_escrow")=="0",
               "no synthetic financial side effects in trigger-free fixture")
            for f in FUNCTIONS:
                query("REVOKE EXECUTE ON FUNCTION c03_social_gateway."+f+
                      " FROM c03_social_writer")
                query("DROP FUNCTION c03_social_gateway."+f)
            query("""REVOKE USAGE ON SCHEMA c03_social_gateway FROM c03_social_writer,c03_legacy_owner;
                     DROP SCHEMA c03_social_gateway RESTRICT;
                     DROP ROLE c03_social_writer;
                     DROP ROLE c03_gateway_owner;""")
            ok(before==rawacl(), "inverse restores exactly five raw NULL legacy ACLs")
            ok(query("SELECT count(*) FROM pg_roles WHERE rolname IN ('c03_social_writer','c03_gateway_owner')")=="0",
               "new gateway and writer roles removed without CASCADE")
            ok(query("SELECT to_regnamespace('c03_social_gateway') IS NULL")=="t",
               "new schema and every new function absent after inverse")
            ok(query("SELECT count(*) FROM public.clan_messages")=="1" and
               query("SELECT count(*) FROM public.direct_messages")=="1",
               "persisted communications preserved after gateway rollback")
            ok(query("SELECT count(*) FROM public.financial_test_escrow")=="0",
               "financial data unchanged across gateway lifecycle")
            print(json.dumps({"status":"PASS","postgres":"16","source_only":True,
              "case_count":len(checks),"checks":checks,"legacy_acl_preimage_sha256":
              hashlib.sha256(before.encode()).hexdigest(),
              "raw_acl_exact":True,"no_tcp":True},sort_keys=True))
        finally:
            if started:
                call([PG / "pg_ctl", "-D", data, "-m", "immediate", "-w", "stop"])

if __name__ == "__main__":
    main()

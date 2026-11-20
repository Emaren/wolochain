#!/usr/bin/env python3
"""Real isolated PG16 acceptance for the NEW fixed-purpose Clan/Direct gateway.

No external DB URL, no existing PGDATA, no live service/role. Source-only CI.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
PG = Path(os.environ.get("PG16_BIN", "/usr/lib/postgresql/16/bin"))
ADMIT = ROOT / "scripts/c03_hd_gateway_v2_restricted_install_candidate.sql"
INVERSE = ROOT / "scripts/c03_hd_gateway_v2_restricted_inverse_candidate.sql"


def run(argv, success=True, **kw):
    p = subprocess.run([str(x) for x in argv], text=True,
                       capture_output=True, timeout=35, **kw)
    if (p.returncode == 0) != success:
        raise AssertionError(f"unexpected exit {p.returncode}: {argv} {p.stderr[-1100:]}")
    return p


def main():
    if os.environ.get("C03_DISPOSABLE_FIXED_GATEWAY_ONLY") != "1":
        raise RuntimeError("C03_FIXED_GATEWAY_EXPLICIT_TEST_OPTIN_REQUIRED")
    if os.geteuid() == 0 or not all((PG / x).is_file() for x in ("initdb", "postgres", "pg_ctl", "psql")):
        raise RuntimeError("C03_NEEDS_UNPRIVILEGED_ACTUAL_PG16")
    assert "16." in run([PG / "postgres", "--version"]).stdout
    assert ADMIT.is_file() and INVERSE.is_file()
    checks = []
    def check(ok, label):
        assert ok, label
        checks.append(label)
    with tempfile.TemporaryDirectory(prefix="c03-fixed-gateway-pg16-") as rootpath:
        root = Path(rootpath)
        data = root / "data"
        sock = root / "socket"
        sock.mkdir(mode=0o700)
        port = 42000 + os.getpid() % 10000
        run([PG / "initdb", "-D", data, "--no-sync", "--auth-local=trust", "--auth-host=reject"])
        up = False
        def sql(query, role=None, success=True):
            args=[PG / "psql", "-X", "-A", "-t", "-v", "ON_ERROR_STOP=1", "-h", sock,
                  "-p", port, "-d", "aoe2hd_db"]
            if role: args.extend(("-U",role))
            return run(args+["-c",query],success=success).stdout.strip()
        def file_sql(source, success=True, db="aoe2hd_db"):
            return run([PG / "psql", "-X", "-A", "-t", "-v", "ON_ERROR_STOP=1",
                        "-h", sock, "-p", port, "-d", db, "-f",source],success=success)
        try:
            run([PG / "pg_ctl", "-D", data, "-o",
                 "-c listen_addresses= -c unix_socket_directories=" + str(sock)
                 + " -c port=" + str(port),
                 "-w", "-l", root / "server.log", "start"])
            up = True
            run([PG / "psql", "-X", "-v", "ON_ERROR_STOP=1",
                 "-h", sock, "-p", port, "-d", "postgres",
                 "-c", "CREATE DATABASE aoe2hd_db"])
            run([PG / "psql", "-X", "-v", "ON_ERROR_STOP=1",
                 "-h", sock, "-p", port, "-d", "postgres",
                 "-c", "CREATE DATABASE aoe2de_db"])
            check(sql("SHOW server_version_num").startswith("16"),
                  "fresh PostgreSQL16 private AF_UNIX HD-only cluster")
            sql("""
CREATE ROLE aoe2hd_user LOGIN NOINHERIT;
CREATE ROLE aoe2war_r25_web_ro NOLOGIN NOINHERIT;
CREATE ROLE aoe2war_web_prod LOGIN NOINHERIT;
CREATE ROLE c03_finance_owner NOLOGIN NOINHERIT;
CREATE ROLE c03_public_probe LOGIN NOINHERIT;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
CREATE TABLE public.users(id serial PRIMARY KEY,uid varchar(100) UNIQUE,is_admin boolean,
 verification_method text,in_game_name text,steam_persona_name text,created_at timestamptz,
 wallet_balance numeric);
CREATE TABLE public.clans(id integer PRIMARY KEY,slug text,status text,chat_audience_policy text);
CREATE TABLE public.clan_members(clan_id integer,user_id integer,status text,role text);
CREATE TABLE public.clan_messages(id serial PRIMARY KEY,clan_id integer,author_user_id integer,
 body varchar(1200),audience varchar(20),created_at timestamp(6),updated_at timestamp(6));
CREATE TABLE public.direct_conversations(id serial PRIMARY KEY,pair_key text UNIQUE,
 created_at timestamptz,updated_at timestamptz);
CREATE TABLE public.direct_conversation_participants(id serial PRIMARY KEY,conversation_id integer,
 user_id integer,joined_at timestamptz,last_read_at timestamptz,typing_updated_at timestamptz,
 UNIQUE(conversation_id,user_id));
CREATE TABLE public.direct_messages(id serial PRIMARY KEY,conversation_id integer,sender_user_id integer,
 body text,reply_to_message_id integer,created_at timestamptz);
CREATE TABLE public.direct_message_drafts(conversation_id integer,user_id integer);
CREATE TABLE public.financial_test_escrow(id serial PRIMARY KEY,amount integer);
CREATE TABLE public.bet_wagers(id serial PRIMARY KEY,user_id integer REFERENCES public.users(id) ON DELETE CASCADE,stake integer);
ALTER TABLE public.users OWNER TO aoe2hd_user;
ALTER TABLE public.clans OWNER TO aoe2hd_user;
ALTER TABLE public.clan_members OWNER TO aoe2hd_user;
ALTER TABLE public.clan_messages OWNER TO aoe2hd_user;
ALTER TABLE public.direct_conversations OWNER TO aoe2hd_user;
ALTER TABLE public.direct_conversation_participants OWNER TO aoe2hd_user;
ALTER TABLE public.direct_messages OWNER TO aoe2hd_user;
ALTER TABLE public.direct_message_drafts OWNER TO aoe2hd_user;
ALTER TABLE public.financial_test_escrow OWNER TO c03_finance_owner;
ALTER TABLE public.bet_wagers OWNER TO aoe2hd_user;
ALTER SEQUENCE public.clan_messages_id_seq OWNER TO aoe2hd_user;
ALTER SEQUENCE public.direct_conversations_id_seq OWNER TO aoe2hd_user;
ALTER SEQUENCE public.direct_conversation_participants_id_seq OWNER TO aoe2hd_user;
ALTER SEQUENCE public.direct_messages_id_seq OWNER TO aoe2hd_user;
SET ROLE aoe2hd_user;
GRANT SELECT ON public.users,public.clans,public.clan_members,public.clan_messages,
 public.direct_conversations,public.direct_conversation_participants,
 public.direct_messages,public.direct_message_drafts TO aoe2war_r25_web_ro;
GRANT SELECT(uid,verification_method) ON public.users TO aoe2war_r25_web_ro;
RESET ROLE;
INSERT INTO public.users(id,uid,is_admin,verification_method,in_game_name,steam_persona_name,created_at)
 VALUES(1,'scribe',false,'steam','Scribe','Scribe',now()),
       (2,'emaren',true,'steam','Emaren','Emaren',now()),
       (3,'outsider',false,'steam','Outsider','Outsider',now()),
       (4,'system',false,'system','Robot','Robot',now());
INSERT INTO public.clans VALUES(7,'alpha','active','public');
INSERT INTO public.clan_members VALUES(7,1,'active','member');
INSERT INTO public.direct_message_drafts VALUES(1,1),(1,2);
""")
            acl = """SELECT c.relname||':'||COALESCE(c.relacl::text,'<NULL>') FROM pg_class c
 WHERE c.relnamespace='public'::regnamespace AND c.relname IN (
 'users','clans','clan_members','clan_messages','direct_conversations',
 'direct_conversation_participants','direct_messages','direct_message_drafts',
 'clan_messages_id_seq','direct_conversations_id_seq',
 'direct_conversation_participants_id_seq','direct_messages_id_seq')
 ORDER BY c.relname"""
            before=sql(acl)
            check(len(before.splitlines())==12 and sum(x.endswith("<NULL>") for x in before.splitlines())==4,
                  "HD preimage exactly 4 raw NULL sequences and 8 explicit table ACLs")
            attacl = """SELECT c.relname||':'||a.attnum::text||':'||
                coalesce(a.attacl::text,'<NULL>')
             FROM pg_class c JOIN pg_attribute a ON a.attrelid=c.oid
             WHERE c.relnamespace='public'::regnamespace
               AND c.relname IN (
                 'users','clans','clan_members','clan_messages',
                 'direct_conversations','direct_conversation_participants',
                 'direct_messages','direct_message_drafts')
               AND a.attnum>0 AND NOT a.attisdropped
             ORDER BY c.relname,a.attnum"""
            before_columns=sql(attacl)
            check(any(not x.endswith("<NULL>") for x in before_columns.splitlines()),
                  "synthetic HD column-level attacl has non-NULL bytes")
            original_raw=hashlib.sha256(before.encode()).hexdigest()
            check(sql("SELECT rolcanlogin::text FROM pg_roles WHERE rolname='aoe2hd_user'")=="true",
                  "fixture replicates real HEL1 original legacy owner LOGIN capability")
            source=ADMIT.read_text()
            check("current_database()<>'aoe2hd_db'" in source and "aoe2hd_user" in source,
                  "source enforces actual HD-only database and owner")
            adapted=source
            assert "CREATE ROLE aoe2war_social_writer" in adapted
            source_path=root/"exact-candidate.sql"
            source_path.write_text(adapted)
            # DE is not source-targeted: even an accidental executor/role leak
            # must be rejected at the FIRST database identity check.
            de_error=file_sql(source_path, success=False, db="aoe2de_db")
            check("C03_HD_ONLY_DATABASE_MISMATCH" in de_error.stderr,
                  "DE gateway installation rejected at exact database identity check")
            # Negative ownership preflight must stop before role is created.
            sql("ALTER TABLE public.clan_messages OWNER TO c03_finance_owner")
            err=file_sql(source_path,success=False)
            check("C03_HD_OBJECT_OWNER_KIND_RAW_ACL_MISMATCH" in err.stderr,
                  "finance-owned social object aborts before role admission")
            check(sql("SELECT count(*) FROM pg_roles WHERE rolname='aoe2war_social_writer'")=="0",
                  "failed owner preflight leaves writer absent")
            sql("ALTER TABLE public.clan_messages OWNER TO aoe2hd_user")
            sql("""CREATE FUNCTION public.c03_attack_trigger() RETURNS trigger
 LANGUAGE plpgsql SECURITY DEFINER AS $$
 BEGIN INSERT INTO public.financial_test_escrow(amount) VALUES(99); RETURN NEW; END $$;
 CREATE TRIGGER c03_attack AFTER INSERT ON public.clan_messages
 FOR EACH ROW EXECUTE FUNCTION public.c03_attack_trigger();""")
            err=file_sql(source_path,success=False)
            check("C03_HD_UNREVIEWED_USER_TRIGGER" in err.stderr,
                  "enabled user trigger aborts before role admission")
            sql("DROP TRIGGER c03_attack ON public.clan_messages; DROP FUNCTION public.c03_attack_trigger()")
            check(sql("SELECT count(*) FROM pg_roles WHERE rolname='aoe2war_social_writer'")=="0",
                  "trigger-negative preflight leaves writer absent")
            file_sql(source_path)
            witness = file_sql(ROOT / "scripts/c03_chat_social_v2_postimage_readonly.sql")
            check("PASS_WE1_SOCIAL_HD_POSTIMAGE" in witness.stdout,
                  "complete corrected postimage catalog, owner, ACL and finance-negative witness passes on installed PG16")
            check(before==sql(acl), "all twelve original table/sequence ACLs unchanged after installation")
            check(before_columns==sql(attacl),
                  "all original column attacl bytes unchanged after installation")
            check(sql("SELECT count(*) FROM pg_auth_members WHERE member='aoe2war_social_writer'::regrole")=="0",
                  "writer no inherited or SET ROLE membership")
            check(sql("SELECT rolcanlogin::text||'|'||rolsuper::text||'|'||rolinherit::text FROM pg_roles WHERE rolname='aoe2war_social_exec_v2'")=="false|false|false",
                  "high-level gateway owned by NOLOGIN NOINHERIT nonsuperuser executor")
            check(sql("SELECT count(*) FROM pg_auth_members WHERE member='aoe2war_social_exec_v2'::regrole")=="0",
                  "narrow executor has no role membership")
            check(sql("SELECT has_table_privilege('aoe2war_social_exec_v2','public.users','DELETE')")=="f",
                  "narrow executor cannot delete user to cascade finance")
            check(sql("SELECT has_table_privilege('aoe2war_social_exec_v2','public.bet_wagers','UPDATE')")=="f",
                  "narrow executor cannot update financial wagers")
            check(sql("SELECT has_sequence_privilege('aoe2war_social_exec_v2','public.clan_messages_id_seq','USAGE')")=="f",
                  "narrow executor cannot directly increment legacy social sequence")
            check(sql("SELECT has_function_privilege('aoe2war_social_writer','aoe2war_social_hd_v2.leaf_append_clan(integer,integer,text,text)','EXECUTE')")=="f",
                  "web writer cannot execute privileged leaf")
            check(sql("SELECT has_table_privilege('aoe2war_social_writer','aoe2war_social_hd_v2.v_direct_messages','SELECT')")=="f",
                  "web writer cannot read unrestricted direct messages")
            check(sql("SELECT count(*) FROM pg_proc p JOIN pg_roles r ON r.oid=p.proowner WHERE p.pronamespace='aoe2war_social_hd_v2'::regnamespace AND p.prosecdef AND r.rolsuper")=="0",
                  "no superuser-owned security-definer gateway functions")
            check(sql("SELECT has_table_privilege('aoe2war_social_writer','public.clan_messages','INSERT')")=="f",
                  "writer no direct social table INSERT")
            check(sql("SELECT has_sequence_privilege('aoe2war_social_writer','public.clan_messages_id_seq','USAGE')")=="f",
                  "writer no original serial sequence USAGE")
            check(sql("SELECT has_table_privilege('aoe2war_social_writer','public.users','SELECT')")=="f",
                  "writer no direct private users/wallet read")
            check(sql("SELECT has_table_privilege('aoe2war_social_writer','public.financial_test_escrow','INSERT')")=="f",
                  "writer no direct finance INSERT")
            check(sql("SELECT has_function_privilege('c03_public_probe','aoe2war_social_hd_v2.clan_text(text,text,text,text)','EXECUTE')")=="f",
                  "PUBLIC cannot execute protected clan gateway")
            check(sql("SELECT has_function_privilege('aoe2war_social_writer','aoe2war_social_hd_v2.clan_text(text,text,text,text)','EXECUTE')")=="t",
                  "writer can execute only reviewed new gateway")
            check(sql("SELECT has_schema_privilege('aoe2war_social_writer','public','CREATE')")=="f",
                  "writer cannot create dynamic public SQL")
            check(sql("SELECT has_function_privilege('aoe2war_social_writer','aoe2war_social_hd_v2.direct_text(text,text,text,integer)','EXECUTE')")=="t",
                  "writer can invoke bounded direct gateway")
            role="aoe2war_social_writer"
            def call_clan(uid,body,audience="clan"):
                return json.loads(sql("SELECT aoe2war_social_hd_v2.clan_text("+
                    ",".join(("'" + uid + "'","'alpha'","'"+body+"'","'"+audience+"'"))+")",role))
            def call_direct(uid,target,body,reply="NULL"):
                return json.loads(sql("SELECT aoe2war_social_hd_v2.direct_text("+
                    ",".join(("'" + uid + "'","'"+target+"'","'"+body+"'",reply))+")",role))
            c1=call_clan("scribe","First Clan hello")
            check(c1["status"]==201 and c1["body"]["messageId"]==1,
                  "clan sent with exact success response contract")
            check(call_clan("scribe","First Clan hello")["body"].get("replayed") is True,
                  "same-message cooldown returns genuine idempotent replay")
            check(call_clan("scribe","Different immediately")["status"]==429,
                  "different-message clan cooldown enforced")
            check(call_clan("outsider","Unauthorized")["status"]==403,
                  "outsider clan membership denied")
            check(call_clan("system","not human")["status"]==401,
                  "system actor rejected")
            d1=call_direct("scribe","emaren","Hello direct")
            check(d1["status"]==201 and d1["body"]["messageId"]==1,
                  "direct text creates pair, participants and message")
            check(call_direct("scribe","emaren","Hello direct")["body"].get("replayed") is True,
                  "uncertain direct acknowledgement deduplicated")
            check(call_direct("scribe","emaren","different")["status"]==429,
                  "direct different-message cooldown enforced")
            check(call_direct("scribe","system","not human")["status"]==403,
                  "system recipient rejected")
            check(call_direct("scribe","scribe","self")["status"]==400,
                  "self direct message rejected")
            time.sleep(1.05)
            check(call_direct("scribe","emaren","reply bad","777")["status"]==400,
                  "cross-conversation reply denied")
            time.sleep(1.05)
            d2=call_direct("scribe","emaren","valid reply","1")
            check(d2["status"]==201 and d2["body"]["messageId"]==2,
                  "valid direct reply and receipt transaction committed")
            check(sql("SELECT count(*) FROM public.direct_messages")=="2",
                  "direct persisted history includes reply")
            check(sql("SELECT count(*) FROM public.direct_message_drafts WHERE user_id=1")=="0" and
                  sql("SELECT count(*) FROM public.direct_message_drafts WHERE user_id=2")=="1",
                  "only author draft cleared; recipient draft untouched")
            check(before==sql(acl), "all twelve original ACLs unchanged after real sends and receipts")
            check(before_columns==sql(attacl),
                  "all original column attacl bytes unchanged after Clan Direct sends")
            check(sql("SELECT count(*) FROM public.financial_test_escrow")=="0",
                  "no synthetic financial writes in owner-verified trigger-free fixture")
            file_sql(INVERSE)
            restored = file_sql(ROOT / "scripts/c03_chat_social_v2_preimage_readonly.sql")
            check("PASS_WE1_SOCIAL_HD_PREIMAGE" in restored.stdout,
                  "actual PostgreSQL16 inverse restores exact Social preimage witness")
            check(before==sql(acl), "inverse exactly restores all twelve raw NULL ACLs")
            check(before_columns==sql(attacl),
                  "inverse restores the byte-exact original column attacl representation")
            check(sql("SELECT count(*) FROM pg_roles WHERE rolname='aoe2war_social_writer'")=="0",
                  "inverse dropped dedicated role without CASCADE")
            check(sql("SELECT to_regnamespace('aoe2war_social_hd_v2') IS NULL")=="t",
                  "inverse removed only new gateway schema and functions")
            check(sql("SELECT count(*) FROM public.clan_messages")=="1" and
                  sql("SELECT count(*) FROM public.direct_messages")=="2",
                  "inverse preserves actual synthetic message history")
            check(sql("SELECT count(*) FROM public.financial_test_escrow")=="0",
                  "finance fixture unchanged through install and inverse")
            print(json.dumps({"status":"PASS","postgres":"16","case_count":len(checks),
              "checks":checks,"real_pg":True,"ephemeral":True,"no_tcp":True,
              "all_legacy_raw_acl_exact":True,"hd_preimage_explicit_8_null_4":True,"initial_acl_sha256":original_raw,
              "not_a_live_financial_witness":True},sort_keys=True))
        finally:
            if up: run([PG / "pg_ctl", "-D", data, "-m", "immediate", "-w", "stop"])

if __name__ == "__main__":
    main()

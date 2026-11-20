#!/usr/bin/env python3
"""Offline PostgreSQL 16 Social/Lobby regression; isolated Unix socket, never HEL1."""
from pathlib import Path
import json, os, re, shutil, subprocess, tempfile
ROOT=Path(__file__).resolve().parents[1]
SQL=ROOT/'scripts/c03_lobby_hd_v1_install_candidate.sql'
BIN=Path(os.environ.get('PG16_BIN','/opt/homebrew/opt/postgresql@16/bin'))
def cmd(*args,env=None):
    cp=subprocess.run(args,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=40)
    if cp.returncode:raise RuntimeError(f'{args[0]} rc={cp.returncode}: {cp.stderr[-1400:]}')
    return cp.stdout.strip()
def main():
    assert SQL.is_file()
    with tempfile.TemporaryDirectory(prefix='aoe2war-lobby-pg16-') as d:
        base=Path(d);sock=base/'socket';db=base/'data';sock.mkdir(mode=0o700)
        cmd(str(BIN/'initdb'),'-D',str(db),'-U','postgres','-A','trust','--no-instructions')
        port='55421'
        options=f"-k {sock} -p {port} -c listen_addresses=''"
        try:
            cmd(str(BIN/'pg_ctl'),'-D',str(db),'-l',str(base/'pg.log'),'-o',options,'-w','start')
            def sql(q,role='postgres',expect_fail=False):
                p=subprocess.run([str(BIN/'psql'),'-h',str(sock),'-p',port,'-U',role,
                     '-d','postgres','-X','-q','-t','-A','-v','ON_ERROR_STOP=1'],
                    input=q,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=18)
                if expect_fail:
                    assert p.returncode!=0, ('EXPECTED_DENIAL',q,p.stdout)
                    return p.stderr.strip()[-250:]
                assert p.returncode==0, (q,p.stderr.strip()[-1000:])
                return p.stdout.strip()
            sql("""
CREATE ROLE aoe2hd_user NOLOGIN;
CREATE ROLE aoe2war_social_writer LOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
CREATE TABLE public.users(id serial PRIMARY KEY,uid varchar(100) UNIQUE NOT NULL,verification_method varchar(32) NOT NULL);
CREATE TABLE public.chat_rooms(id serial PRIMARY KEY,slug varchar(80) UNIQUE NOT NULL,scope varchar(20) NOT NULL);
CREATE TABLE public.chat_messages(id serial PRIMARY KEY,room_id integer NOT NULL,user_id integer NOT NULL,body varchar(500) NOT NULL,created_at timestamp without time zone DEFAULT clock_timestamp());
CREATE TABLE public.chat_message_guest_reactions(id serial PRIMARY KEY,guest_session_id varchar(64));
CREATE TABLE public.bet_wagers(id serial PRIMARY KEY);
ALTER TABLE public.users OWNER TO aoe2hd_user;
ALTER TABLE public.chat_rooms OWNER TO aoe2hd_user;
ALTER TABLE public.chat_messages OWNER TO aoe2hd_user;
ALTER TABLE public.chat_message_guest_reactions OWNER TO aoe2hd_user;
ALTER TABLE public.bet_wagers OWNER TO aoe2hd_user;
INSERT INTO public.users(uid,verification_method) VALUES ('steam-alice','steam'),('steam-bob','steam'),('fake-guest','none');
INSERT INTO public.chat_rooms(slug,scope) VALUES ('main-lobby','lobby'),('other-room','tournament');
INSERT INTO public.chat_messages(room_id,user_id,body) VALUES (1,2,'Old public lobby history must survive');
""")
            acl_sql="""SELECT coalesce(string_agg(c.relname||':'||coalesce(c.relacl::text,'<NULL>')||':'||c.relowner::text,'|' ORDER BY c.relname),'')
 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
 WHERE n.nspname='public' AND c.relname IN ('users','users_id_seq','chat_rooms','chat_rooms_id_seq','chat_messages','chat_messages_id_seq','chat_message_guest_reactions','bet_wagers');"""
            before=sql(acl_sql)
            sql(SQL.read_text())
            after=sql(acl_sql)
            assert before==after,'ORIGINAL_RAW_ACL_OR_OWNER_DRIFT'
            def post(uid,body,key,role='aoe2war_social_writer'):
                # All literal inputs are only synthetic fixture values.
                q="SELECT aoe2war_lobby_hd_v1.post_text("+','.join("'"+v.replace("'","''")+"'" for v in [uid,body,key])+");"
                return json.loads(sql(q,role=role))
            k='a'*32
            first=post('steam-alice','Hello Lobby',k)
            assert first['status']==201 and first['replayed'] is False,first
            repeat=post('steam-alice','Hello Lobby',k)
            assert repeat['status']==201 and repeat['replayed'] is True and repeat['messageId']==first['messageId'],repeat
            collision=post('steam-alice','Different body',k)
            assert collision['status']==409,collision
            cooldown=post('steam-alice','Hello 2','b'*32)
            assert cooldown['status']==429,cooldown
            guest=post('fake-guest','Not permitted','c'*32)
            assert guest['status']==401,guest
            bad_room_write=sql("INSERT INTO public.chat_messages(room_id,user_id,body) VALUES(2,1,'raw denied');",role='aoe2war_social_writer',expect_fail=True)
            private_read=sql("SELECT guest_session_id FROM public.chat_message_guest_reactions;",role='aoe2war_social_writer',expect_fail=True)
            leaf_call=sql("SELECT aoe2war_lobby_hd_v1.leaf_append_lobby(1,1,'bad');",role='aoe2war_social_writer',expect_fail=True)
            raw_grants=sql("""SELECT has_table_privilege('aoe2war_social_writer','public.chat_messages','INSERT'),
has_table_privilege('aoe2war_social_writer','public.chat_message_guest_reactions','SELECT'),
has_function_privilege('aoe2war_social_writer','aoe2war_lobby_hd_v1.post_text(text,text,text)','EXECUTE'),
has_function_privilege('aoe2war_social_writer','aoe2war_lobby_hd_v1.leaf_append_lobby(integer,integer,text)','EXECUTE');""")
            assert raw_grants=='f|f|t|f',raw_grants
            history=sql("SELECT body FROM public.chat_messages WHERE id=1")
            assert history=='Old public lobby history must survive',history
            count=sql("SELECT count(*) FROM public.chat_messages")
            assert count=='2',count
            inverse=(ROOT/'scripts/c03_lobby_hd_v1_inverse_candidate.sql').read_text()
            sql(inverse)
            assert sql("SELECT count(*) FROM public.chat_messages")=='2','INVERSE_DELETED_HISTORY'
            assert sql(acl_sql)==before,'INVERSE_LEGACY_ACL_DRIFT'
            assert sql("SELECT to_regnamespace('aoe2war_lobby_hd_v1') IS NULL")=='t'
            denied_inverse=sql("SELECT aoe2war_lobby_hd_v1.post_text('steam-alice','bad','abababababababababababababababab');",
                               role='aoe2war_social_writer',expect_fail=True)
            sql(SQL.read_text())
            sql("UPDATE public.chat_messages SET created_at=clock_timestamp()-interval '10 seconds'")
            third=post('steam-alice','Post inverse restored','d'*32)
            assert third['status']==201 and third['replayed'] is False,third
            assert sql("SELECT count(*) FROM public.chat_messages")=='3'
            assert sql(acl_sql)==before,'REINSTALL_LEGACY_ACL_DRIFT'
            print(json.dumps({'status':'PASS_ISOLATED_PG16_LOBBY_WRITER_TESTS',
                 'postgres_version':cmd(str(BIN/'postgres'),'--version'),
                 'legacy_acl_unchanged':True,'old_public_history_preserved':True,
                 'writer_insert':first['messageId'],'idempotent_retry':True,
                 'conflicting_nonce_409':True,'cooldown_429':True,
                 'guest_401':True,'raw_insert_denied':bool(bad_room_write),
                 'guest_session_select_denied':bool(private_read),
                 'leaf_execute_denied':bool(leaf_call),
                 'inverse_preserves_legacy_history':True,'fresh_reinstall_pass':True,
                 'financial_authorized':False,'production_executed':False},sort_keys=True))
        finally:
            subprocess.run([str(BIN/'pg_ctl'),'-D',str(db),'-m','immediate','-w','stop'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=15)
if __name__=='__main__':main()

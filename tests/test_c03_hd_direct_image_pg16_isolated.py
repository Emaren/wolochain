#!/usr/bin/env python3
"""Disposable PG16 only; uses existing Social V2 fixture DDL and exact base install."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import select
import uuid
from concurrent.futures import ThreadPoolExecutor

ROOT=Path(__file__).resolve().parents[1]
PG=Path(os.environ.get("PG16_BIN","/usr/lib/postgresql/16/bin"))
INSTALL=ROOT/"scripts/c03_hd_direct_image_install_candidate.sql"
INVERSE=ROOT/"scripts/c03_hd_direct_image_inverse_candidate.sql"
BASE=ROOT/"scripts/c03_hd_gateway_v2_restricted_install_candidate.sql"

def run(*args, success=True):
    p=subprocess.run([str(PG/args[0]),*map(str,args[1:])],capture_output=True,text=True,timeout=30)
    if (p.returncode==0)!=success:
        raise AssertionError(f"{args[0]} expected success={success}: {p.stderr[-1500:]}")
    return p.stdout.strip()

def main():
    assert os.environ.get("C03_DISPOSABLE_FIXED_GATEWAY_ONLY")=="1" and os.geteuid()!=0
    assert "16." in run("postgres","--version")
    passed=[]
    def check(ok,label):
        assert ok,label
        passed.append(label)
        print("PASS",label,flush=True)
    # Reuse the already source-qualified fixture setup, extending only media columns.
    prior=(ROOT/"scripts/c03_hd_gateway_v2_physical_rehearsal.py").read_text()
    fixture=prior.split('sql("""\nCREATE ROLE aoe2hd_user',1)[1].split('""")',1)[0]
    fixture="CREATE ROLE aoe2hd_user"+fixture
    with tempfile.TemporaryDirectory(prefix="dm-media-pg16-") as tmp:
        root=Path(tmp); data=root/"data"; sock=root/"socket"; sock.mkdir(mode=0o700)
        port=42000+os.getpid()%10000
        run("initdb","-D",data,"--auth-local=trust","--auth-host=reject")
        run("pg_ctl","-D",data,"-o",f"-h '' -k {sock} -p {port}","-w","-l",root/"log","start")
        try:
            def sql(q,role=None,db="aoe2hd_db",success=True):
                args=["psql","-X","-qAt","-v","ON_ERROR_STOP=1","-h",sock,"-p",port,"-d",db]
                if role: args+=["-U",role]
                return run(*args,"-c",q,success=success)
            def file(p,db="aoe2hd_db",success=True):
                return run("psql","-X","-qAt","-v","ON_ERROR_STOP=1","-h",sock,"-p",port,"-d",db,"-f",p,success=success)
            sql("CREATE DATABASE aoe2hd_db",db="postgres")
            sql("CREATE DATABASE aoe2de_db",db="postgres")
            sql(fixture)
            sql("ALTER TABLE public.direct_messages ADD attachment_kind varchar(20), ADD attachment_name varchar(255), ADD attachment_mime_type varchar(120), ADD attachment_data_url text, ADD shared_lobby_message_id integer, ADD delivered_at timestamp(6)")
            file(BASE)
            # Existing public ACLs/owners, column ACLs and role membership fingerprint.
            fingerprint="""SELECT md5(string_agg(x,'|' ORDER BY x)) FROM (
             SELECT c.oid::text||':'||c.relowner||':'||coalesce(c.relacl::text,'NULL') x FROM pg_class c WHERE relnamespace='public'::regnamespace
             UNION ALL SELECT attrelid::text||':'||attnum||':'||coalesce(attacl::text,'NULL') FROM pg_attribute WHERE attrelid IN(SELECT oid FROM pg_class WHERE relnamespace='public'::regnamespace)
             UNION ALL SELECT row_to_json(r)::text FROM pg_roles r
             UNION ALL SELECT row_to_json(m)::text FROM pg_auth_members m
             UNION ALL SELECT row_to_json(n)::text FROM pg_namespace n WHERE n.nspname IN('public','aoe2war_social_hd_v2')) s"""
            before=sql(fingerprint)
            before_text=sql("SELECT md5(pg_get_functiondef('aoe2war_social_hd_v2.direct_text(text,text,text,integer)'::regprocedure))")
            file(INSTALL,db="aoe2de_db",success=False)
            check(sql("SELECT to_regnamespace('aoe2war_social_hd_v2') IS NULL",db="aoe2de_db")=="t","DE install denied")
            file(INSTALL)
            check(sql(fingerprint)==before,"public raw relation/column ACL, role/membership and schema fingerprint unchanged")
            file(INVERSE)
            check(sql("SELECT md5(pg_get_functiondef('aoe2war_social_hd_v2.direct_text(text,text,text,integer)'::regprocedure))")==before_text,"unused inverse exact original text body")
            check(sql(fingerprint)==before and sql("SELECT to_regclass('aoe2war_social_hd_v2.image_request_keys') IS NULL")=="t","unused exact inverse")
            file(INSTALL)
            # Fresh connections as actual low-authority LOGIN roles.
            writer="aoe2war_social_writer"
            def call(actor="scribe",target="emaren",caption="",reply=None,key="a"*32,digest="b"*64,ref=None,name="image.png",mime="image/png",size=123,rollback=False,success=True,query_only=False):
                if ref is None: ref="file:v1:dm-"+str(uuid.uuid4())+".png"
                def lit(v):
                    if v is None: return "NULL"
                    if isinstance(v,int): return str(v)
                    return "'"+v.replace("'","''")+"'"
                query="SELECT aoe2war_social_hd_v2.direct_image("+",".join(map(lit,[actor,target,caption,reply,key,digest,ref,name,mime,size]))+")"
                if query_only: return query
                if rollback: query="BEGIN ISOLATION LEVEL SERIALIZABLE;"+query+";ROLLBACK"
                result=sql(query,writer,success=success)
                return json.loads(result) if success else None
            def expect(result,status,label):
                check(result["status"]==status,label)
            expect(call(actor="missing"),401,"unknown sender denied")
            expect(call(actor="system"),401,"system sender denied")
            expect(call(target="system"),403,"system target denied")
            expect(call(target="scribe"),400,"self denied")
            expect(call(target="missing"),404,"unknown target denied")
            expect(call(ref="file:v1:../../etc/passwd"),400,"path injection denied")
            expect(call(size=10000001),400,"oversized metadata denied")
            expect(call(mime="image/jpeg"),400,"MIME/ref mismatch denied")
            expect(call(reply=999),400,"foreign reply denied before DML")
            check(sql("SELECT count(*) FROM public.direct_messages")=="0","denials leave no messages")
            expect(call(key="c"*32,rollback=True),201,"transaction rollback path")
            check(sql("SELECT count(*) FROM public.direct_messages")=="0" and sql("SELECT count(*) FROM aoe2war_social_hd_v2.image_request_keys")=="0","atomic rollback message and replay row")
            first_ref="file:v1:dm-"+str(uuid.uuid4())+".png"
            first=call(ref=first_ref)
            expect(first,201,"image-only accepted")
            mid=first["body"]["messageId"]
            check(first["body"]["replayed"] is False,"new decision")
            second=call()
            check(second["body"]["messageId"]==mid and second["body"]["replayed"] is True,"stable idempotent retry with different file ref")
            expect(call(digest="d"*64),409,"changed hash conflicts")
            expect(call(caption="different"),409,"same hash different caption conflicts")
            expect(call(target="outsider"),409,"different recipient same key conflicts")
            second=call(actor="emaren",target="scribe",caption="caption",reply=mid,key="a"*32)
            expect(second,201,"recipient reverse send same key isolated by actor")
            check(sql("SELECT count(*) FROM public.direct_messages WHERE attachment_kind='image'")=="2","two actual image rows")
            check(sql(f"SELECT count(*) FROM public.direct_messages WHERE id={mid} AND sender_user_id=1 AND body='' AND attachment_data_url='{first_ref}' AND attachment_name='image.png' AND attachment_mime_type='image/png'")=="1","actual sender and original attachment metadata")
            check(sql(f"SELECT count(*) FROM public.direct_messages WHERE sender_user_id=2 AND body='caption' AND reply_to_message_id={mid}")=="1","actual caption and reply persistence")
            call(key="f"*32,ref=first_ref,success=False)
            check(sql("SELECT count(*) FROM public.direct_messages")=="2" and sql("SELECT count(*) FROM aoe2war_social_hd_v2.image_request_keys")=="2","late ledger uniqueness failure rolls back entire message")
            # Two independent actual LOGIN connections with same key; READ COMMITTED
            # verifies serialized replay. WE3 uses SERIALIZABLE and must retry 40001.
            with ThreadPoolExecutor(max_workers=2) as pool:
                jobs=[pool.submit(call,key="1"*32,caption="concurrent") for _ in range(2)]
                pair=[j.result(timeout=20) for j in jobs]
            check(all(x["status"]==201 for x in pair) and pair[0]["body"]["messageId"]==pair[1]["body"]["messageId"] and sorted(x["body"]["replayed"] for x in pair)==[False,True],"concurrent same-key one insert one replay")
            check(sql("SELECT count(*) FROM public.direct_messages")=="3","concurrency created exactly one additional message")
            # Match WE3's SERIALIZABLE transaction: make the second connection
            # wait on the first actor lock with its earlier snapshot, then commit.
            args=[str(PG/"psql"),"-X","-qAt","-v","ON_ERROR_STOP=1","-v","VERBOSITY=verbose","-h",str(sock),"-p",str(port),"-d","aoe2hd_db","-U",writer]
            first_proc=subprocess.Popen(args,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,bufsize=1)
            second_proc=None
            try:
                first_proc.stdin.write("BEGIN ISOLATION LEVEL SERIALIZABLE;"+call(key="2"*32,caption="serial",query_only=True)+";\n")
                first_proc.stdin.flush()
                assert select.select([first_proc.stdout],[],[],5)[0],"first serializable result timed out"
                serial_first=json.loads(first_proc.stdout.readline())
                assert serial_first["status"]==201 and not serial_first["body"]["replayed"]
                second_proc=subprocess.Popen(args+["-c","BEGIN ISOLATION LEVEL SERIALIZABLE;"+call(key="2"*32,caption="serial",query_only=True)+";COMMIT"],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
                deadline=time.monotonic()+5
                waiting=False
                while time.monotonic()<deadline:
                    if int(sql("SELECT count(*) FROM pg_stat_activity WHERE usename='aoe2war_social_writer' AND wait_event_type='Lock' AND wait_event='advisory'")):
                        waiting=True;break
                    time.sleep(.05)
                assert waiting,"second writer did not reach advisory lock"
                first_proc.stdin.write("COMMIT;\n\\q\n");first_proc.stdin.flush()
                assert first_proc.wait(timeout=5)==0,first_proc.stderr.read()
                out,err=second_proc.communicate(timeout=10)
                check(second_proc.returncode!=0 and "40001" in err,"overlapping SERIALIZABLE snapshot fails with retryable 40001")
                retry=call(key="2"*32,caption="serial")
                check(retry["status"]==201 and retry["body"]["replayed"] and retry["body"]["messageId"]==serial_first["body"]["messageId"],"retry after serialization conflict returns original message")
            finally:
                for proc in (first_proc,second_proc):
                    if proc is not None and proc.poll() is None:
                        proc.kill();proc.wait(timeout=5)
            check(sql("SELECT count(*) FROM public.direct_messages")=="4","serializable overlap produced one message")
            check(sql("SELECT count(*) FROM aoe2war_social_hd_v2.image_request_keys")=="4","one ledger row per actual send")
            # Mirror WE3 route participant predicate; this is not DB row-level security.
            for who,want in [("scribe","1"),("emaren","1"),("outsider","0")]:
                q=f"SELECT count(*) FROM public.direct_messages m JOIN public.direct_conversation_participants p ON p.conversation_id=m.conversation_id JOIN public.users u ON u.id=p.user_id WHERE m.id={mid} AND u.uid='{who}' AND m.attachment_data_url IS NOT NULL"
                check(sql(q)==want,"attachment predicate "+who)
            # Corrupt pair must not expand membership or disclose existing replay.
            sql("INSERT INTO public.direct_conversation_participants(conversation_id,user_id,joined_at) SELECT id,3,now() FROM public.direct_conversations WHERE pair_key='1:2'")
            expect(call(),403,"unexpected third participant blocks replay")
            expect(call(key="e"*32),403,"unexpected third participant blocks new send")
            sql("DELETE FROM public.direct_conversation_participants WHERE user_id=3")
            sql("SELECT * FROM public.direct_messages",writer,success=False)
            sql("SELECT * FROM aoe2war_social_hd_v2.image_request_keys",writer,success=False)
            sql("SELECT aoe2war_social_hd_v2.leaf_send_direct_image(1,1,2,'',NULL,'x','x','x')",writer,success=False)
            sql("DELETE FROM public.users WHERE id=1",writer,success=False)
            sql("INSERT INTO public.bet_wagers(user_id,stake) VALUES(1,1)",writer,success=False)
            sql("SELECT * FROM public.financial_test_escrow",writer,success=False)
            sql("SELECT aoe2war_social_hd_v2.direct_image(NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL)","c03_public_probe",success=False)
            sql("SELECT aoe2war_social_hd_v2.direct_image(NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL)",writer,db="aoe2de_db",success=False)
            check(True,"writer raw/leaf/financial/public/DE denial")
            check(sql(fingerprint)==before,"public ACL and roles unchanged after sends")
            file(INVERSE,success=False)
            check(sql("SELECT count(*) FROM public.direct_messages")=="4","used inverse denied, messages preserved")
            def text_send(actor,target,body,reply=None):
                return json.loads(sql(f"SELECT aoe2war_social_hd_v2.direct_text('{actor}','{target}','{body}',{reply if reply is not None else 'NULL'})",writer))
            def ack(actor,target,ids,rollback=False):
                query=f"SELECT aoe2war_social_hd_v2.direct_delivered('{actor}','{target}',ARRAY[{','.join(map(str,ids))}]::integer[])"
                if rollback: query="BEGIN;"+query+";ROLLBACK"
                return json.loads(sql(query,writer))
            mixed=call(key="3"*32,caption="same caption",reply=mid)
            im=mixed["body"]["messageId"]
            expect(text_send("scribe","emaren","same caption",mid),429,"image caption is cooldown, never text replay")
            sql(f"UPDATE public.direct_messages SET created_at=clock_timestamp()-interval '5 seconds' WHERE sender_user_id=1")
            tx=text_send("scribe","emaren","same caption",mid)
            expect(tx,201,"same caption text after cooldown is a distinct message")
            ti=tx["body"]["messageId"]
            check(ti!=im and sql(f"SELECT attachment_kind IS NULL FROM public.direct_messages WHERE id={ti}")=="t","actual text row separate from image")
            check(text_send("scribe","emaren","same caption",mid)["body"]["messageId"]==ti,"text-only recent retry returns text ID")
            expect(ack("outsider","scribe",[im]),403,"outsider cannot acknowledge")
            expect(ack("scribe","emaren",[im]),403,"sender cannot acknowledge own delivery")
            expect(ack("emaren","scribe",[im,999999]),403,"mixed unauthorized batch denied")
            check(sql(f"SELECT delivered_at IS NULL FROM public.direct_messages WHERE id={im}")=="t","mixed batch no partial update")
            expect(ack("emaren","scribe",[im,ti],rollback=True),200,"delivery transaction rollback")
            check(sql(f"SELECT count(*) FROM public.direct_messages WHERE id IN({im},{ti}) AND delivered_at IS NOT NULL")=="0","delivery rollback leaves timestamps null")
            check(ack("emaren","scribe",[im,ti])["body"]["updatedCount"]==2,"recipient acknowledges exact text and image IDs")
            stamps=sql(f"SELECT id,delivered_at FROM public.direct_messages WHERE id IN({im},{ti}) ORDER BY id")
            check(ack("emaren","scribe",[im,ti])["body"]["updatedCount"]==0 and sql(f"SELECT id,delivered_at FROM public.direct_messages WHERE id IN({im},{ti}) ORDER BY id")==stamps,"delivery retry preserves first timestamp")
            expect(ack("emaren","scribe",[im,im]),400,"duplicate receipt IDs denied")
            expect(ack("emaren","scribe",list(range(1,52))),400,"oversize batch denied")
            sql("SELECT aoe2war_social_hd_v2.leaf_ack_direct_delivery(1,2,ARRAY[1])",writer,success=False)
            sql("SELECT aoe2war_social_hd_v2.direct_delivered('scribe','emaren',ARRAY[1])","c03_public_probe",success=False)
            sql("SELECT aoe2war_social_hd_v2.direct_delivered('scribe','emaren',ARRAY[1])",writer,db="aoe2de_db",success=False)
            check(sql(fingerprint)==before,"delivery and mixed sends leave public ACL and roles unchanged")
            print(json.dumps({"checks":len(passed),"install_sha256":hashlib.sha256(INSTALL.read_bytes()).hexdigest(),"inverse_sha256":hashlib.sha256(INVERSE.read_bytes()).hexdigest()}),flush=True)
        finally:
            run("pg_ctl","-D",data,"-m","fast","-w","stop")
    print("FIXTURE_STOPPED_AND_REMOVED")
if __name__=="__main__":
    main()

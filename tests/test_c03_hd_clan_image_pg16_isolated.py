"""Disposable native PostgreSQL 16 test; never connect to production."""
import concurrent.futures
import hashlib
import json
import os
import pathlib
import shutil
import subprocess as s
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
BIN = pathlib.Path(os.environ.get("PG16_BIN", "/opt/homebrew/opt/postgresql@16/bin"))
INSTALL = ROOT / "scripts/c03_hd_clan_image_v1_install_candidate.sql"
INVERSE = ROOT / "scripts/c03_hd_clan_image_v1_inverse_candidate.sql"
FIXTURE = """
CREATE ROLE aoe2hd_user LOGIN; CREATE ROLE aoe2war_social_writer LOGIN NOINHERIT;
CREATE ROLE aoe2war_web_prod LOGIN NOINHERIT;
CREATE SCHEMA aoe2war_social_hd_v2;
CREATE FUNCTION aoe2war_social_hd_v2.clan_text(text,text,text,text) RETURNS jsonb LANGUAGE sql AS 'SELECT NULL::jsonb';
CREATE TABLE users(id serial primary key,uid text unique,verification_method text);
CREATE TABLE clans(id serial primary key,slug text unique,status text,chat_audience_policy text);
CREATE TABLE clan_members(id serial primary key,user_id integer REFERENCES users(id),clan_id integer REFERENCES clans(id),status text,UNIQUE(user_id,clan_id));
CREATE TABLE clan_messages(id serial primary key,clan_id integer REFERENCES clans(id),author_user_id integer REFERENCES users(id),body varchar(1200) NOT NULL,audience varchar(20),created_at timestamp,updated_at timestamp);
CREATE TABLE clan_message_attachments(id serial primary key,message_id integer REFERENCES clan_messages(id),kind varchar(20),name varchar(255),mime_type varchar(120),storage_ref varchar(500),size_bytes integer,created_at timestamp);
CREATE TABLE financial_test(id serial primary key,user_id integer REFERENCES users(id) ON DELETE CASCADE);
ALTER TABLE users OWNER TO aoe2hd_user;ALTER TABLE clans OWNER TO aoe2hd_user;
ALTER TABLE clan_members OWNER TO aoe2hd_user;ALTER TABLE clan_messages OWNER TO aoe2hd_user;ALTER TABLE clan_message_attachments OWNER TO aoe2hd_user;
INSERT INTO users(uid,verification_method) VALUES('alice','steam'),('bob','steam'),('eve','steam'),('bot','system');
INSERT INTO clans(slug,status,chat_audience_policy) VALUES('alpha','active','clan'),('beta','active','public');
INSERT INTO clan_members(user_id,clan_id,status) VALUES(1,1,'active'),(2,1,'active'),(3,2,'active'),(4,1,'active');
"""
def main():
    assert " 16." in s.check_output([str(BIN/"postgres"),"--version"],text=True)
    with tempfile.TemporaryDirectory(prefix="ci-",dir="/tmp") as tmp:
        p=pathlib.Path(tmp); sock=p/"s";sock.mkdir(mode=0o700)
        env={k:v for k,v in os.environ.items() if not k.startswith("PG")}
        s.run([str(BIN/"initdb"),"-D",str(p/"d"),"-A","trust","--no-locale"],check=True,stdout=s.DEVNULL,env=env)
        s.run([str(BIN/"pg_ctl"),"-D",str(p/"d"),"-l",str(p/"log"),"-o",f"-h '' -k {sock} -p 55479","-w","start"],check=True,stdout=s.DEVNULL,env=env)
        count=0
        try:
            def cmd(db):
                return [str(BIN/"psql"),"-X","-qAt","-v","ON_ERROR_STOP=1","-h",str(sock),"-p","55479","-d",db]
            def run(sql,db="aoe2hd_db",ok=True):
                if isinstance(sql,str):sql=sql.encode()
                q=s.run(cmd(db),input=sql,capture_output=True,env=env,timeout=15)
                if (q.returncode==0)!=ok:raise RuntimeError(q.stderr.decode()[:2000])
                return q.stdout.decode().strip()
            def check(label,value):
                nonlocal count
                assert value,label
                count+=1; print("PASS",label,flush=True)
            run("CREATE DATABASE aoe2hd_db;","postgres")
            run(FIXTURE)
            snap="SELECT md5(string_agg(oid::text||':'||coalesce(relacl::text,'NULL')||':'||relowner::text,',' ORDER BY oid)) FROM pg_class WHERE relnamespace='public'::regnamespace;"
            pre=run(snap);install=INSTALL.read_bytes();inverse=INVERSE.read_bytes()
            run(install);check("install raw public ACL unchanged",run(snap)==pre)
            run(inverse);check("unused inverse",run("SELECT to_regnamespace('aoe2war_clan_image_hd_v1') IS NULL;")=="t" and run(snap)==pre)
            run(install)
            def post(uid="alice",slug="alpha",key="a",digest="b",ref="c",name="a.png",mime="image/png",size=20):
                return json.loads(run(f"SET ROLE aoe2war_social_writer; SELECT aoe2war_clan_image_hd_v1.post_image('{uid}','{slug}','{key*32}','{digest*64}','file:v1:clan-{ref*32}.png','{name}','{mime}',{size});"))
            a=post();check("member image insert",a["status"]==201 and not a["replayed"])
            b=post(ref="d");check("same key replay",b["status"]==201 and b["replayed"] and b["messageId"]==a["messageId"])
            check("changed digest conflict",post(digest="d")["status"]==409)
            check("nonmember denied",post(uid="eve")["status"]==403)
            check("system actor denied",post(uid="bot")["status"]==403)
            check("cross-clan post denied",post(slug="beta")["status"]==403)
            check("shared cooldown",post(key="e",ref="f")["status"]==429)
            check("invalid mime",post(mime="image/svg+xml")["status"]==400)
            check("invalid size",post(size=10000001)["status"]==400)
            aid=a["attachmentId"]
            def read(uid,slug):return run(f"SET ROLE aoe2war_social_writer; SELECT aoe2war_clan_image_hd_v1.read_image('{uid}','{slug}',{aid});")
            check("second member read",json.loads(read("bob","alpha"))["sizeBytes"]==20)
            check("nonmember read denied",read("eve","alpha")=="")
            check("cross-clan read denied",read("alice","beta")=="")
            run("UPDATE clan_members SET status='inactive' WHERE user_id=2;")
            check("revoked member read denied",read("bob","alpha")=="")
            for label,sql in [
                ("writer ledger direct deny","SET ROLE aoe2war_social_writer; SELECT * FROM aoe2war_clan_image_hd_v1.request_keys;"),
                ("writer leaf deny","SET ROLE aoe2war_social_writer; SELECT * FROM aoe2war_clan_image_hd_v1.leaf_scope('alice','alpha');"),
                ("writer finance deny","SET ROLE aoe2war_social_writer; SELECT * FROM public.financial_test;"),
                ("web role direct deny","SET ROLE aoe2war_web_prod; SELECT aoe2war_clan_image_hd_v1.read_image('alice','alpha',1);")]:
                run(sql,ok=False);check(label,True)
            check("exact one message and attachment",run("SELECT count(*) FROM clan_messages;SELECT count(*) FROM clan_message_attachments;")=="1\n1")
            run(inverse,ok=False);check("used inverse refuses",run("SELECT count(*) FROM clan_messages;")=="1")
            check("original public raw ACL unchanged",run(snap)==pre)
            # Fresh actor, genuinely concurrent sessions and distinct provisional object refs.
            run("UPDATE clan_members SET status='active' WHERE user_id=2;")
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
                f=pool.submit(post,uid="bob",key="1",ref="2")
                g=pool.submit(post,uid="bob",key="1",ref="3")
                rows=[f.result(),g.result()]
            check("concurrent same key one insert one replay",all(x["status"]==201 for x in rows) and rows[0]["messageId"]==rows[1]["messageId"] and sum(x["replayed"] for x in rows)==1)
            check("concurrent exact row counts",run("SELECT count(*) FROM clan_messages;SELECT count(*) FROM clan_message_attachments;")=="2\n2")
            # Hold the actual membership row lock until transaction completion.
            proc=s.Popen(cmd("aoe2hd_db"),stdin=s.PIPE,stdout=s.PIPE,stderr=s.PIPE,text=True,env=env)
            try:
                proc.stdin.write(f"BEGIN; SET ROLE aoe2war_social_writer; SELECT aoe2war_clan_image_hd_v1.read_image('bob','alpha',{aid});\n");proc.stdin.flush()
                check("active member read inside transaction",json.loads(proc.stdout.readline())["sizeBytes"]==20)
                run("SET lock_timeout='100ms'; UPDATE clan_members SET status='inactive' WHERE user_id=2;",ok=False)
                check("membership revocation blocked until read transaction ends",True)
                proc.stdin.write("COMMIT;\\q\n");proc.stdin.flush()
                proc.wait(timeout=5);assert proc.returncode==0
            finally:
                if proc.poll() is None:proc.kill();proc.wait()
            run("UPDATE clan_members SET status='inactive' WHERE user_id=2;")
            check("subsequent read after revocation denied",read("bob","alpha")=="")
            check("subsequent replay after revocation denied",post(uid="bob",key="1",ref="2")["status"]==403)
            print("TOTAL",count,"INSTALL_SHA",hashlib.sha256(install).hexdigest(),"INVERSE_SHA",hashlib.sha256(inverse).hexdigest())
        finally:
            s.run([str(BIN/"pg_ctl"),"-D",str(p/"d"),"-m","immediate","-w","stop"],check=True,stdout=s.DEVNULL,env=env)
if __name__ == "__main__":
    main()

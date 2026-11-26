import os,pathlib,subprocess,tempfile,json
root=pathlib.Path(__file__).resolve().parent
pg=pathlib.Path("/opt/homebrew/opt/postgresql@16/bin")
assert os.geteuid()==650
env={k:v for k,v in os.environ.items() if not k.upper().startswith("PG")}
def run(*args,check=True):
 p=subprocess.run([str(x) for x in args],capture_output=True,text=True,timeout=40,env=env)
 if check and p.returncode:raise RuntimeError(p.stderr[-3000:])
 return p
with tempfile.TemporaryDirectory(prefix="clan-reader-",dir="/tmp") as tmp:
 t=pathlib.Path(tmp);sock=t/"s";sock.mkdir(mode=0o700);data=t/"data";port=45000+os.getpid()%10000
 run(pg/"initdb","-D",data,"--auth-local=trust","--auth-host=reject")
 started=False
 try:
  run(pg/"pg_ctl","-D",data,"-o",f"-h '' -k {sock} -p {port}","-l",t/"log","-w","start");started=True
  def psql(sql,role=None,db="aoe2hd_db",check=True):
   args=[pg/"psql","-X","-qAt","-v","ON_ERROR_STOP=1","-h",sock,"-p",port,"-d",db]
   if role:args+=["-U",role]
   return run(*args,"-c",sql,check=check)
  def file(name,db="aoe2hd_db",check=True):return run(pg/"psql","-X","-qAt","-v","ON_ERROR_STOP=1","-h",sock,"-p",port,"-d",db,"-f",root/name,check=check)
  file("fixture.sql","postgres")
  snap="SELECT jsonb_agg(jsonb_build_array(oid,relacl,relowner) ORDER BY oid) FROM pg_class WHERE relnamespace='public'::regnamespace"
  pre=psql(snap).stdout
  def ok(label,b):
   assert b,label
   print("PASS",label,flush=True)
  ok("DE/wrong database rejected",file("install.sql","postgres",False).returncode!=0)
  file("install.sql")
  w="aoe2war_social_writer"
  def read(actor="alice",slug="alpha",before=None,focus=None):
   args=f"'{actor}','{slug}',{before if before is not None else 'NULL'},{focus if focus is not None else 'NULL'}"
   raw=psql("SELECT aoe2war_clan_read_hd_v1.read_hall("+args+")",w).stdout.strip()
   return json.loads(raw) if raw else None
  h=read()
  ok("active member snapshot",h["viewer"]["uid"]=="alice" and h["clan"]["slug"]=="alpha")
  ok("80 rows and overflow",len(h["messages"])==80 and h["hasMore"])
  ok("ascending order",all(x["id"]<y["id"] for x,y in zip(h["messages"],h["messages"][1:])))
  ok("wrong audience and other clan absent",all(m["id"] not in (83,84) for m in h["messages"]))
  ok("registered format metadata only",next(m for m in h["messages"] if m["id"]==85)["attachments"]==[{"id":1,"name":"x.png","mimeType":"image/png","sizeBytes":123}])
  ok("legacy explicit unsupported",next(m for m in h["messages"] if m["id"]==86)["unsupportedAttachment"])
  ok("no file reference", "file:v1:" not in json.dumps(h) and "data:image" not in json.dumps(h))
  ok("older cursor bounded",len(read(before=h["beforeMessageId"])["messages"])==4)
  ok("focus exact member message",read(focus=85)["messages"][0]["id"]==85)
  ok("foreign focus denied",read(focus=83) is None)
  ok("foreign cursor denied",read(before=83) is None)
  ok("invalid dual cursor denied",read(before=1,focus=2) is None)
  ok("admin outsider denied",read("eve") is None)
  ok("system actor denied",read("bot") is None)
  ok("other clan membership denied",read(slug="beta") is None)
  ok("other active member admitted",read("bob")["viewer"]["uid"]=="bob")
  psql("UPDATE clan_members SET status='inactive' WHERE user_id=2")
  ok("revocation denies subsequent read",read("bob") is None)
  ok("web function denied",psql("SELECT aoe2war_clan_read_hd_v1.read_hall('alice','alpha',NULL,NULL)","aoe2war_web_prod",check=False).returncode!=0)
  ok("raw writer users denied",psql("SELECT * FROM public.users",w,check=False).returncode!=0)
  ok("raw writer clan messages denied",psql("SELECT * FROM public.clan_messages",w,check=False).returncode!=0)
  ok("financial sentinel denied",psql("SELECT * FROM public.finance_sentinel",w,check=False).returncode!=0)
  ok("public ACL unchanged",psql(snap).stdout==pre)
  ok("read only no message mutations",psql("SELECT count(*) FROM clan_messages").stdout.strip()=="86")
  file("inverse.sql")
  ok("inverse removes only capability",psql("SELECT to_regnamespace('aoe2war_clan_read_hd_v1') IS NULL").stdout.strip()=="t" and psql(snap).stdout==pre)
  print("CLAN_READER_REAL_PG16_PASS",flush=True)
 finally:
  if started:run(pg/"pg_ctl","-D",data,"-m","fast","-w","stop")
print("ISOLATED_PG16_STOPPED_REMOVED")

import hashlib,json,os,pathlib,subprocess,tempfile
root=pathlib.Path(__file__).resolve().parent
pg=pathlib.Path("/opt/homebrew/opt/postgresql@16/bin")
assert os.geteuid()==650
def run(*args,check=True):
 p=subprocess.run([str(x) for x in args],capture_output=True,text=True,timeout=40)
 if check and p.returncode: raise RuntimeError(p.stderr[-2500:])
 return p
with tempfile.TemporaryDirectory(prefix="direct-reader-",dir="/tmp") as tmp:
 t=pathlib.Path(tmp); sock=t/"s"; sock.mkdir(mode=0o700); data=t/"data"; port=45000+os.getpid()%10000
 run(pg/"initdb","-D",data,"--auth-local=trust","--auth-host=reject")
 started=False
 try:
  run(pg/"pg_ctl","-D",data,"-o",f"-h '' -k {sock} -p {port}","-l",t/"log","-w","start"); started=True
  def psql(sql,role=None,db="aoe2hd_db",check=True):
   args=[pg/"psql","-X","-qAt","-v","ON_ERROR_STOP=1","-h",sock,"-p",port,"-d",db]
   if role: args+=["-U",role]
   return run(*args,"-c",sql,check=check)
  def file(name,db="aoe2hd_db",check=True):
   return run(pg/"psql","-X","-qAt","-v","ON_ERROR_STOP=1","-h",sock,"-p",port,"-d",db,"-f",root/name,check=check)
  file("fixture.sql","postgres")
  before=psql("SELECT jsonb_agg(jsonb_build_array(oid,relacl) ORDER BY oid) FROM pg_class WHERE relnamespace='public'::regnamespace").stdout
  assert file("install.sql","postgres",False).returncode!=0
  file("install.sql")
  writer="aoe2war_social_writer"; web="aoe2war_web_prod"
  def call(actor,op,target=None,before=None,query=None,message=None,role=writer):
   def lit(x): return "NULL" if x is None else str(x) if isinstance(x,int) else "'"+x.replace("'","''")+"'"
   s="SELECT aoe2war_direct_read_hd_v1.read_direct("+",".join(map(lit,(actor,op,target,before,query,message)))+")"
   raw=psql(s,role).stdout.strip()
   return json.loads(raw) if raw else None
  def ok(name,b):
   assert b,name
   print("PASS",name,flush=True)
  ok("writer raw users denied",psql("SELECT * FROM users",writer,check=False).returncode!=0)
  ok("writer raw messages denied",psql("SELECT * FROM direct_messages",writer,check=False).returncode!=0)
  ok("writer financial sentinel denied",psql("SELECT * FROM financial_sentinel",writer,check=False).returncode!=0)
  ok("web RPC denied",psql("SELECT aoe2war_direct_read_hd_v1.read_direct('alice','summary',NULL,NULL,NULL,NULL)",web,check=False).returncode!=0)
  ok("public raw ACL identical",before==psql("SELECT jsonb_agg(jsonb_build_array(oid,relacl) ORDER BY oid) FROM pg_class WHERE relnamespace='public'::regnamespace").stdout)
  ok("actor summary only canonical pair", [x["targetUid"] for x in call("alice","summary")["summary"]["threads"]]==["bob"])
  ok("admin outsider does not see pair",call("outsider","history","alice")["messages"]==[] and call("outsider","history","alice")["conversationId"] is None)
  ok("corrupt three-member pair rejected",call("alice","history","extra") is None)
  hist=call("alice","history","bob")
  ok("bounded history",len(hist["messages"])==80 and hist["hasMore"] and hist["beforeMessageId"]==13)
  ok("corrupt sender excluded",all(x["senderUid"] in ("alice","bob") for x in hist["messages"]))
  ok("no storage ref in history", "storageRef" not in json.dumps(hist) and "file:v1:" not in json.dumps(hist))
  img=next(x for x in hist["messages"] if x["messageId"]==91)
  ok("cross-pair reply excluded",img["replyToMessageId"] is None)
  ok("restricted image metadata",img["attachment"]["mimeType"]=="image/png")
  ok("legacy attachment explicitly unsupported",next(x for x in hist["messages"] if x["messageId"]==92)["unsupportedAttachment"])
  ok("paging older nonoverlapping", [x["messageId"] for x in call("alice","history","bob",hist["beforeMessageId"])["messages"]]==list(range(1,13)))
  ok("sync exact bounded",len(call("bob","sync","alice")["rows"])==80)
  ok("search literal participant bound", [x["messageId"] for x in call("bob","search","alice",query="needle")["results"]]==[91])
  ok("search wildcard not wildcard",call("bob","search","alice",query="%%")["results"]==[])
  ok("sender and recipient attachment",all(call(a,"attachment",message=91)["mimeType"]=="image/png" for a,b in [("alice","bob"),("bob","alice")]))
  ok("unrelated attachment denied",call("outsider","attachment",message=91) is None)
  ok("legacy data URL denied",call("alice","attachment",message=92) is None)
  ok("attachment target injection rejected",call("alice","attachment","bob",message=91) is None)
  ok("empty new thread safe",call("alice","history","dave")["counterpart"]["uid"]=="dave" and call("alice","history","dave")["messages"]==[])
  ok("timestamps timezone explicit",hist["messages"][0]["createdAt"].endswith("+00:00"))
  ok("invalid operation combinations rejected",call("alice","sync","bob",before=2) is None)
  ok("no GET writes",psql("SELECT count(*) FROM direct_messages").stdout.strip()=="95")
  file("inverse.sql")
  ok("inverse removes only capability",psql("SELECT to_regnamespace('aoe2war_direct_read_hd_v1') IS NULL").stdout.strip()=="t" and before==psql("SELECT jsonb_agg(jsonb_build_array(oid,relacl) ORDER BY oid) FROM pg_class WHERE relnamespace='public'::regnamespace").stdout)
 finally:
  if started: run(pg/"pg_ctl","-D",data,"-m","fast","-w","stop")
for p in ("install.sql","inverse.sql","fixture.sql","test.py"):
 print(hashlib.sha256((root/p).read_bytes()).hexdigest(),p)
print("ISOLATED_PG16_STOPPED_REMOVED",flush=True)

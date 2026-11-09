#!/usr/bin/env python3
"""C03 physical preconnected legacy-writer test on an APFS clone of restored HD.
Never connect to HEL1, public TCP, funded services or an existing PG cluster.
Result is always nonfunded HOLD even when all isolated assertions pass.
"""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,os,platform,re,shlex,stat,subprocess,sys,time

C07=Path.home()/".wolo-owner-authority/c07-source-pinned-aoe2de_db-20261109"
ORIGINAL=C07/"pgdata"
ORIGINAL_RECEIPT=C07/"c07-unquiesced-physical-restore-receipt.json"
RECEIPT_SHA="df21fa2e67319e606a530af501c5b108831178c27fb98c79b31e02bb166a5bb7"
ROOT=Path.home()/".wolo-owner-authority/c03-intel-preconn-de-v2-20261109"
TOOLS=Path.home()/".local/aoe2war-pg16-16.15/bin"
PORT="54438"
DB="c07_de_isolated"
OLD="c03_preconnected_legacy_de"
NEW="c03_finance_nologin_de"
TARGET="trophy_payouts"
EXTRA=("user_gifts",)
NAME=r"(wolo|bet|wager|settle|claim|escrow|refund|reward|stake|treasury|wallet|founder|bonus|payout|transfer)"
SEM=r"(amount.*wolo|wolo.*amount|tx_hash|transaction_hash|recipient_address|owner_address|escrow|payment|payout|withdraw|deposit|balance|stake|reward)"
class Hold(Exception):pass
def need(c,reason):
 if not c:raise Hold(reason)
def call(argv,timeout=60,**kw):
 return subprocess.run([str(x) for x in argv],capture_output=True,text=True,timeout=timeout,**kw)
def result(argv,timeout=60):
 r=call(argv,timeout)
 need(r.returncode==0,"SUBPROCESS_FAILED_"+str(argv[0])+"_"+r.stderr[-180:])
 return r.stdout.strip()
def sha(data):return hashlib.sha256(data).hexdigest()
def private(path,mode=0o600):
 st=path.lstat()
 need(st.st_uid==os.getuid() and st.st_nlink==1 and
      stat.S_IMODE(st.st_mode)==mode and stat.S_ISREG(st.st_mode),
      "PRIVATE_FILE_OR_MODE_INVALID_"+path.name)
def sql(db,query,socket,actor=None,expected_success=True):
 args=[TOOLS/"psql","-X","-qAt","-v","ON_ERROR_STOP=1",
       "-h",socket,"-p",PORT,"-U",actor or os.getenv("USER"),"-d",db,"-c",query]
 r=call(args,timeout=55)
 if expected_success:need(r.returncode==0,"ISOLATED_SQL_REJECTED_"+r.stderr[-170:])
 return r
def fixed_ident(name):
 need(re.fullmatch(r"[a-z_][a-z0-9_]{0,62}",name) is not None,"UNSAFE_PG_IDENT")
 return '"'+name+'"'
def action():
 need(sys.platform=="darwin" and platform.machine()=="x86_64" and os.geteuid()!=0,
      "INTEL_ONLY_UNPRIVILEGED")
 need(not ROOT.exists() and not ROOT.is_symlink(),"SINGLE_SHOT_NO_OVERWRITE")
 private(ORIGINAL_RECEIPT)
 need(sha(ORIGINAL_RECEIPT.read_bytes())==RECEIPT_SHA,"REAL_C07_RECOVERY_SHA_DRIFT")
 need((ORIGINAL/"PG_VERSION").read_text()=="16\n" and not (ORIGINAL/"postmaster.pid").exists(),
      "RESTORED_SOURCE_MUST_BE_STOPPED")
 ctl=result([TOOLS/"pg_controldata",ORIGINAL],timeout=15)
 need("Database cluster state:               shut down" in ctl,
      "RESTORED_SOURCE_NOT_CLEANLY_STOPPED")
 need((TOOLS/"psql").is_file() and (TOOLS/"pg_ctl").is_file(),"PG16_MISSING")
 ROOT.mkdir(mode=0o700)
 work=ROOT/"pgdata"
 print("C03_CLONING_STOPPED_C07_DE_ORIGINAL_APFS_COW",flush=True)
 result(["cp","-c","-R",ORIGINAL,work],timeout=200)
 need((work/"PG_VERSION").read_text()=="16\n" and
      not (work/"postmaster.pid").exists(),"COW_CLONE_INCOMPLETE")
 sock=ROOT/"s";sock.mkdir(mode=0o700)
 need(len(str(sock/(".s.PGSQL."+PORT)).encode())<=103,"UNIX_SOCKET_PATH_TOO_LONG")
 log=ROOT/"postgres.log"
 opts="-c listen_addresses='' -c unix_socket_directories="+shlex.quote(str(sock))
 opts+=" -c unix_socket_permissions=0700 -c fsync=off -p "+PORT
 started=False;session=None
 try:
  result([TOOLS/"pg_ctl","-D",work,"-o",opts,"-l",log,"-w","start"],timeout=80)
  started=True
  b=str(sock)
  need(sql("postgres","SELECT datname FROM pg_database WHERE datname='"+DB+"'",b).stdout.strip()==DB,
       "EXPECTED_ACTUAL_HD_RESTORE_DB_MISSING")
  count=int(sql(DB,"SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relkind IN ('r','p')",b).stdout.strip())
  need(count==52,"REAL_DE_TABLES_NOT_52")
  sql(DB,"CREATE ROLE "+OLD+" LOGIN; CREATE ROLE "+NEW+" NOLOGIN;",b)
  sql(DB,"GRANT CONNECT ON DATABASE "+fixed_ident(DB)+" TO "+OLD+
       "; GRANT USAGE ON SCHEMA public TO "+OLD,b)
  pred="(c.relname ~* '"+NAME+"' OR EXISTS (SELECT 1 FROM pg_attribute a WHERE a.attrelid=c.oid AND a.attnum>0 AND NOT a.attisdropped AND a.attname ~* '"+SEM+"') OR c.relname IN ("+",".join("'"+x+"'" for x in EXTRA)+"))"
  tables=sql(DB,"SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relkind IN ('r','p') AND "+pred+" ORDER BY c.relname",b).stdout.splitlines()
  need(len(tables)==21 and len(set(tables))==21 and TARGET in tables,
       "FINANCE_21_CANDIDATE_SCOPE_DRIFT")
  for t in tables:fixed_ident(t)
  # Recreate old PG owner on ALL protected tables; old owner can DML before migration.
  batch="BEGIN;\n"+"".join("ALTER TABLE public."+fixed_ident(t)+" OWNER TO "+OLD+";\n" for t in tables)+"COMMIT;"
  sql(DB,batch,b)
  sql(DB,"GRANT ALL ON ALL TABLES IN SCHEMA public TO "+OLD,b)
  yes=sql(DB,"SELECT has_table_privilege('"+OLD+"','public."+TARGET+"','INSERT,UPDATE,DELETE,TRUNCATE')",b).stdout.strip()
  need(yes=="t","OLD_OWNER_BEFORE_MIGRATION_NOT_WRITABLE")
  argv=[str(TOOLS/"psql"),"-X","-qAt","-v","ON_ERROR_STOP=1","-h",b,"-p",PORT,"-U",OLD,"-d",DB]
  session=subprocess.Popen(argv,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,bufsize=1)
  def send(cmd,marker):
   need(session.poll() is None and session.stdin is not None and session.stdout is not None,
        "PRECONNECTED_BACKEND_GONE")
   session.stdin.write(cmd+"\nSELECT '"+marker+"';\n");session.stdin.flush()
   for _ in range(10):
    line=session.stdout.readline()
    need(line!="","PRECONNECTED_SESSION_EOF")
    if line.strip()==marker:return
   raise Hold("PRECONNECTED_SQL_MARKER_LOST")
  send("SELECT pg_backend_pid();","C03_PRECONNECTED_READY")
  send("DELETE FROM public."+fixed_ident(TARGET)+" WHERE false;",
       "C03_OWNER_DML_BEFORE_MIGRATION_COMPLETED")
  # Existing backend remains alive throughout ALTER/REVOKE, not a new login.
  ddl="BEGIN;\n"
  for t in tables:
   ident="public."+fixed_ident(t)
   ddl+="ALTER TABLE "+ident+" OWNER TO "+NEW+";\n"
   ddl+="REVOKE ALL ON "+ident+" FROM "+OLD+", PUBLIC;\n"
   ddl+="GRANT SELECT ON "+ident+" TO "+OLD+";\n"
  ddl+="COMMIT;"
  sql(DB,ddl,b,expected_success=True)
  neg=sql(DB,"SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relname IN ("+",".join("'"+x+"'" for x in tables)+") AND (pg_get_userbyid(c.relowner)!='"+NEW+"' OR has_table_privilege('"+OLD+"',c.oid,'INSERT,UPDATE,DELETE,TRUNCATE'))",b).stdout.strip()
  need(neg=="0","C03_21_OWNER_OR_GRANT_NOT_FENCED")
  session.stdin.write("\\set ON_ERROR_STOP off\n");session.stdin.flush()
  send("DELETE FROM public."+fixed_ident(TARGET)+" WHERE false;",
       "C03_PRECONNECTED_POST_MIGRATION_DENIAL_OBSERVED")
  send("SELECT count(*) FROM public."+fixed_ident(TARGET)+" WHERE false;",
       "C03_PRECONNECTED_PROTECTED_SELECT_STILL_WORKS")
  session.stdin.close()
  session.wait(timeout=12)
  errors=session.stderr.read() if session.stderr else ""
  need(session.returncode==0 and errors.count("permission denied for table "+TARGET)==1,
       "PRECONNECTED_DML_DENIAL_NOT_EXACT")
  fresh=sql(DB,"DELETE FROM public."+fixed_ident(TARGET)+" WHERE false",b,actor=OLD,expected_success=False)
  need(fresh.returncode!=0 and ("permission denied" in fresh.stderr),
       "FRESH_RECONNECT_DML_DENIAL_NOT_PROVEN")
  # Nonfinancial table DML remains granted: this is not a blanket DROP LOGIN.
  auth=sql(DB,"SELECT has_table_privilege('"+OLD+"','public.users','UPDATE')",b).stdout.strip()
  need(auth=="t","LEGACY_NONFINANCE_USERS_UPDATE_LOST")
  report={"schema":"wolo.c03.real-de-recovered-preconnected-owner-migration-nonfunded.v1",
    "utc":datetime.now(timezone.utc).isoformat(),"source":str(ORIGINAL),
    "c07_restored_receipt_sha256":RECEIPT_SHA,
    "de_restored_public_table_count":52,
    "protected_finance_table_count":len(tables),
    "preconnected_old_owner_before_migration_dml_allowed":True,
    "old_owner_moved_to_nologin_finance_owner_on_protected_tables":True,
    "preconnected_old_owner_after_migration_dml_denied":True,
    "fresh_reconnected_old_owner_after_migration_dml_denied":True,
    "preconnected_protected_select_still_allowed":True,
    "nonfinance_legacy_users_update_grant_preserved":True,
    "mutations_only_in_disposable_intel_apfs_clone":True,
    "source_pgdata_unmodified":True,
    "production_hd_de_postgres_mutated":False,
    "production_c03_fence_complete":False,
    "authenticated_steam_rollback_verified":False,
    "c03_formally_closed":False,
    "funded_activation_authorized":False}
  buf=(json.dumps(report,sort_keys=True,indent=2)+"\n").encode()
  f=ROOT/"c03-real-de-preconnected-dml-denial.json"
  fd=os.open(f,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600)
  with os.fdopen(fd,"wb") as out:out.write(buf);out.flush();os.fsync(out.fileno())
  print("PASS_C03_INTEL_REAL_RESTORED_DE_21_FINANCE_TABLES_PRECONNECTED_DML_DENIED",flush=True)
  print("PASS_C03_FRESH_RECONNECT_DENIED_AND_LEGACY_USERS_UPDATE_PRESERVED",flush=True)
  print("C03_ROOT_PRIVATE_RECEIPT_SHA256",sha(buf),flush=True)
  print("HOLD_C03_LIVE_WRITER_GRAPH_STEAM_ACCEPTANCE_AND_C06_C07_ATOMIC_BOUNDARY",flush=True)
 finally:
  if session and session.poll() is None:
   try:session.kill();session.wait(timeout=8)
   except Exception:pass
  if started:
   stopped=call([TOOLS/"pg_ctl","-D",work,"-m","fast","-w","stop"],timeout=65)
   need(stopped.returncode==0,"ISOLATED_REHEARSAL_POSTGRES_STOP_FAILED")
  need(not (ORIGINAL/"postmaster.pid").exists(),"ORIGINAL_C07_DATABASE_UNEXPECTEDLY_STARTED")
if __name__=="__main__":
 try:action()
 except (Hold,ValueError,OSError,subprocess.SubprocessError,KeyError,TypeError) as e:
  print("HOLD_C03_ISOLATED_PRECONNECTED_REHEARSAL",str(e)[:250],flush=True)
  sys.exit(3)

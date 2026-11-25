#!/usr/bin/env python3
"""C03 physical preconnected legacy-writer test on an APFS clone of restored HD.
Never connect to HEL1, public TCP, funded services or an existing PG cluster.
Result is always nonfunded HOLD even when all isolated assertions pass.
"""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,os,platform,re,shlex,stat,subprocess,sys,time

C07=Path.home()/".wolo-owner-authority/c07-source-pinned-aoe2hd_db-20261109"
ORIGINAL=C07/"pgdata"
ORIGINAL_RECEIPT=C07/"c07-unquiesced-physical-restore-receipt.json"
RECEIPT_SHA="7a8d495b4259c5316f0f38ff060667d6b81f1243f77e1656daf2765da3603305"
ROOT=Path.home()/".wolo-owner-authority/c03-intel-fullpublic-hd-sequences-v4-20261109"
TOOLS=Path.home()/".local/aoe2war-pg16-16.15/bin"
PORT="54441"
DB="c07_hd_isolated"
OLD="c03_preconnected_legacy_hd"
NEW="c03_finance_nologin_hd"
TARGET="pending_wolo_claims"
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
 print("C03_CLONING_STOPPED_C07_HD_ORIGINAL_APFS_COW",flush=True)
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
       "EXPECTED_ACTUAL_RESTORE_DB_MISSING")
  count=int(sql(DB,"SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relkind IN ('r','p')",b).stdout.strip())
  need(count==190,"REAL_HD_TABLES_NOT_190")
  sql(DB,"CREATE ROLE "+OLD+" LOGIN; CREATE ROLE "+NEW+" NOLOGIN;",b)
  sql(DB,"GRANT CONNECT ON DATABASE "+fixed_ident(DB)+" TO "+OLD+
       "; GRANT USAGE ON SCHEMA public TO "+OLD,b)
  pred="(c.relname ~* '"+NAME+"' OR EXISTS (SELECT 1 FROM pg_attribute a WHERE a.attrelid=c.oid AND a.attnum>0 AND NOT a.attisdropped AND a.attname ~* '"+SEM+"') OR c.relname IN ("+",".join("'"+x+"'" for x in EXTRA)+"))"
  tables=sql(DB,"SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relkind IN ('r','p') ORDER BY c.relname",b).stdout.splitlines()
  need(len(tables)==190 and len(set(tables))==190 and TARGET in tables and "users" in tables,
       "FULL_PUBLIC_190_TABLE_SCOPE_DRIFT")
  seqs=sql(DB,"SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relkind='S' ORDER BY c.relname",b).stdout.splitlines()
  need(len(seqs)==180 and len(set(seqs))==180 and "users_id_seq" in seqs,"FULL_PUBLIC_180_SEQUENCE_SCOPE_DRIFT")
  for seq in seqs:fixed_ident(seq)
  for t in tables:fixed_ident(t)
  # Recreate old PG owner on ALL protected tables; old owner can DML before migration.
  batch="BEGIN;\n"+"".join("ALTER TABLE public."+fixed_ident(t)+" OWNER TO "+OLD+";\n" for t in tables)+"COMMIT;"
  sql(DB,batch,b)
  sql(DB,"BEGIN;\n"+"".join("ALTER SEQUENCE public."+fixed_ident(q)+" OWNER TO "+OLD+";\n" for q in seqs)+"COMMIT;",b)
  sql(DB,"GRANT ALL ON ALL TABLES IN SCHEMA public TO "+OLD,b)
  sql(DB,"GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO "+OLD,b)
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
  send("UPDATE public.users SET last_seen=last_seen WHERE false;",
       "C03_USERS_DML_BEFORE_MIGRATION_COMPLETED")
  send("SELECT nextval('public.users_id_seq');",
       "C03_SEQUENCE_NEXTVAL_BEFORE_MIGRATION_COMPLETED")
  # Existing backend remains alive throughout ALTER/REVOKE, not a new login.
  ddl="BEGIN;\n"
  for t in tables:
   ident="public."+fixed_ident(t)
   ddl+="ALTER TABLE "+ident+" OWNER TO "+NEW+";\n"
   ddl+="REVOKE ALL ON "+ident+" FROM "+OLD+", PUBLIC;\n"
   ddl+="GRANT SELECT ON "+ident+" TO "+OLD+";\n"
  for q in seqs:
   ident="public."+fixed_ident(q)
   ddl+="ALTER SEQUENCE "+ident+" OWNER TO "+NEW+";\n"
   ddl+="REVOKE ALL ON SEQUENCE "+ident+" FROM "+OLD+", PUBLIC;\n"
  ddl+="COMMIT;"
  sql(DB,ddl,b,expected_success=True)
  neg=sql(DB,"SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relname IN ("+",".join("'"+x+"'" for x in tables)+") AND (pg_get_userbyid(c.relowner)!='"+NEW+"' OR has_table_privilege('"+OLD+"',c.oid,'INSERT,UPDATE,DELETE,TRUNCATE'))",b).stdout.strip()
  need(neg=="0","C03_ALL_190_TABLE_OWNER_OR_GRANT_NOT_FENCED")
  seqneg=sql(DB,"SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relkind='S' AND (pg_get_userbyid(c.relowner)!='"+NEW+"' OR has_sequence_privilege('"+OLD+"',c.oid,'UPDATE') OR has_sequence_privilege('"+OLD+"',c.oid,'USAGE'))",b).stdout.strip()
  need(seqneg=="0","C03_ALL_180_SEQUENCE_OWNER_OR_GRANT_NOT_FENCED")
  session.stdin.write("\\set ON_ERROR_STOP off\n");session.stdin.flush()
  send("DELETE FROM public."+fixed_ident(TARGET)+" WHERE false;",
       "C03_PRECONNECTED_POST_MIGRATION_DENIAL_OBSERVED")
  send("UPDATE public.users SET last_seen=last_seen WHERE false;",
       "C03_PRECONNECTED_USERS_DML_DENIAL_OBSERVED")
  send("SELECT nextval('public.users_id_seq');",
       "C03_PRECONNECTED_SEQUENCE_NEXTVAL_DENIAL_OBSERVED")
  send("SELECT count(*) FROM public."+fixed_ident(TARGET)+" WHERE false;",
       "C03_PRECONNECTED_PROTECTED_SELECT_STILL_WORKS")
  session.stdin.close()
  session.wait(timeout=12)
  errors=session.stderr.read() if session.stderr else ""
  need(session.returncode==0 and errors.count("permission denied for table "+TARGET)==1 and errors.count("permission denied for table users")==1 and errors.count("permission denied for sequence users_id_seq")==1,
       "PRECONNECTED_TABLE_USERS_SEQUENCE_DENIAL_NOT_EXACT")
  fresh=sql(DB,"DELETE FROM public."+fixed_ident(TARGET)+" WHERE false",b,actor=OLD,expected_success=False)
  need(fresh.returncode!=0 and ("permission denied" in fresh.stderr),
       "FRESH_RECONNECT_DML_DENIAL_NOT_PROVEN")
  # Whole-public default-deny rehearsal; NOT approved as a production App policy.
  auth=sql(DB,"SELECT has_table_privilege('"+OLD+"','public.users','UPDATE')",b).stdout.strip()
  need(auth=="f","LEGACY_USERS_DML_NOT_FENCED")
  fresh_user=sql(DB,"UPDATE public.users SET last_seen=last_seen WHERE false",b,actor=OLD,expected_success=False)
  need(fresh_user.returncode!=0 and "permission denied" in fresh_user.stderr,"FRESH_USERS_DML_DENIAL_NOT_PROVEN")
  fresh_seq=sql(DB,"SELECT nextval('public.users_id_seq')",b,actor=OLD,expected_success=False)
  need(fresh_seq.returncode!=0 and "permission denied" in fresh_seq.stderr,"FRESH_SEQ_NEXTVAL_DENIAL_NOT_PROVEN")
  report={"schema":"wolo.c03.real-hd-recovered-preconnected-owner-migration-nonfunded.v1",
    "utc":datetime.now(timezone.utc).isoformat(),"source":str(ORIGINAL),
    "c07_restored_receipt_sha256":RECEIPT_SHA,
    "hd_restored_public_table_count":190,
    "full_public_table_count":len(tables),
    "full_public_sequence_count":len(seqs),
    "all_public_sequences_old_role_update_and_usage_denied":True,
    "preconnected_users_dml_and_nextval_denied":True,
    "preconnected_old_owner_before_migration_dml_allowed":True,
    "old_owner_moved_to_nologin_finance_owner_on_protected_tables":True,
    "preconnected_old_owner_after_migration_dml_denied":True,
    "fresh_reconnected_old_owner_after_migration_dml_denied":True,
    "preconnected_protected_select_still_allowed":True,
    "legacy_users_update_grant_preserved":False,
    "requires_scoped_app_auth_review_before_live_use":True,
    "mutations_only_in_disposable_intel_apfs_clone":True,
    "source_pgdata_unmodified":True,
    "production_hd_de_postgres_mutated":False,
    "production_c03_fence_complete":False,
    "authenticated_steam_rollback_verified":False,
    "c03_formally_closed":False,
    "funded_activation_authorized":False}
  buf=(json.dumps(report,sort_keys=True,indent=2)+"\n").encode()
  f=ROOT/"c03-fullpublic-hd-preconnected-table-sequence-denial.json"
  fd=os.open(f,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600)
  with os.fdopen(fd,"wb") as out:out.write(buf);out.flush();os.fsync(out.fileno())
  print("PASS_C03_INTEL_REAL_RESTORED_HD_190_TABLES_180_SEQUENCES_PRECONNECTED_DENIAL",flush=True)
  print("PASS_C03_FRESH_RECONNECT_USERS_SEQUENCE_DENIED_APP_AUTH_HANDOFF_REQUIRED",flush=True)
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

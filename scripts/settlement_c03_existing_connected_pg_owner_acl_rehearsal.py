#!/usr/bin/env python3
"""Disposable Intel PG16 proof of already-connected AND future session owner ACL.

All changes are to ephemeral, private, socket-only test DB. Does NOT contact
HEL1, finance DBs, the WOLO validator or any hosted application service.
"""
from __future__ import annotations
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import platform
import select
import shlex
import stat
import subprocess
import sys
import tempfile
import time

HOME=Path.home()
ROOT=HOME/".wolo-owner-authority/offhost-db-rehearsal-20261107"
RESULT=ROOT/"c03-preconnected-and-reconnected-owner-acl-denial-20261107.json"
BIN=HOME/".local/aoe2war-pg16-16.15/bin"
PORT="54407"

def need(v,reason):
 if not v:raise RuntimeError(reason)

def cmd(args,seconds=30,check=True):
 p=subprocess.run(list(map(str,args)),capture_output=True,text=True,timeout=seconds)
 if check:need(p.returncode==0,"CMD_FAILURE_"+str(args[0])+"_"+p.stderr[-180:])
 return p

def session_sql(p,stmt,label):
 marker="C03_"+label+"_"
 p.stdin.write((stmt.rstrip()+chr(10)+chr(92)+"echo "+marker+":SQLSTATE"+chr(10)).encode())
 p.stdin.flush()
 deadline=time.monotonic()+12
 output=[]
 buf=getattr(p,"_carry",b"")
 while time.monotonic()<deadline:
  if b"\n" not in buf:
   ready,_,_=select.select([p.stdout.fileno()],[],[],min(1,max(.1,deadline-time.monotonic())))
   need(p.poll() is None,"EXISTING_BACKEND_DISCONNECTED_"+label)
   if not ready:continue
   buf+=os.read(p.stdout.fileno(),4096)
   need(len(buf)<131072,"EXCESSIVE_PG_OUTPUT")
   continue
  line,buf=buf.split(b"\n",1)
  line=line.decode("utf-8","replace").strip()
  if line.startswith(marker):
   code=line[len(marker):]
   need(code.isalnum() and len(code)==5,"PG_SQLSTATE_MISSING_"+label+"_"+line)
   p._carry=buf
   return code,output
  output.append(line)
 raise RuntimeError("SESSION_QUERY_TIMEOUT_"+label)

def main():
 need(sys.platform=="darwin" and platform.machine()=="x86_64" and os.geteuid()!=0,
      "INTEL_NONROOT_REQUIRED")
 s=ROOT.stat()
 need(stat.S_ISDIR(s.st_mode) and s.st_uid==os.getuid()
      and stat.S_IMODE(s.st_mode)==0o700,"PRIVATE_OWNER_ROOT")
 need(not RESULT.exists() and not RESULT.is_symlink(),"RECEIPT_REPLAY_DENIED")
 for name in ("postgres","initdb","pg_ctl","psql"):
  need((BIN/name).is_file() and os.access(BIN/name,os.X_OK),
       "POSTGRES_16_BINARY_MISSING")
 need("16." in cmd([BIN/"psql","--version"]).stdout,"PG16_REQUIRED")
 username=os.getenv("USER")
 need(username and username.isidentifier(),"LOCAL_USER_INVALID")
 os.umask(0o077)
 with tempfile.TemporaryDirectory(prefix="c03-owner-session-sock-",dir="/tmp") as sock:
  need(len((sock+"/.s.PGSQL."+PORT).encode())<104,"PG_SOCK_TOO_LONG")
  with tempfile.TemporaryDirectory(prefix="c03-session-db-",dir=ROOT) as td:
   d=Path(td);data=d/"data";log=d/"postgres.log"
   cmd([BIN/"initdb","-A","trust","-U",username,"-D",data],seconds=75)
   started=False;session=None
   def sql(database,stmt,actor=None,check=True):
    return cmd([BIN/"psql","-X","-qAt","-v","ON_ERROR_STOP=1",
     "-h",sock,"-p",PORT,"-U",actor or username,"-d",database,"-c",stmt],
     seconds=15,check=check)
   try:
    opts="-c listen_addresses='' -c unix_socket_directories="+shlex.quote(sock)
    opts+=" -c unix_socket_permissions=0700 -c fsync=off -p "+PORT
    cmd([BIN/"pg_ctl","-D",data,"-o",opts,"-l",log,"-w","start"],seconds=65)
    started=True
    sql("postgres","CREATE ROLE c03_legacy LOGIN")
    sql("postgres","CREATE ROLE c03_neutral NOLOGIN")
    sql("postgres","CREATE DATABASE c03_owner_acl_test TEMPLATE template0")
    db="c03_owner_acl_test"
    sql(db,"CREATE TABLE public.finance (id integer primary key)")
    sql(db,"CREATE TABLE public.users (id integer primary key)")
    sql(db,"ALTER TABLE public.finance OWNER TO c03_legacy")
    sql(db,"ALTER TABLE public.users OWNER TO c03_legacy")
    sql(db,"GRANT USAGE ON SCHEMA public TO c03_legacy")
    session=subprocess.Popen([str(BIN/"psql"),"-X","-qAt",
        "-P","pager=off","-v","ON_ERROR_STOP=off",
        "-h",sock,"-p",PORT,"-U","c03_legacy","-d",db],
        stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
        text=False,bufsize=0)
    before_pid=session_sql(session,"SELECT pg_backend_pid();","PID_BEFORE")
    pid=before_pid[1][-1]
    need(before_pid[0]=="00000" and pid.isdecimal(),"BACKEND_PID_BEFORE_MISSING")
    initial=session_sql(session,"UPDATE public.finance SET id=id WHERE false;",
        "FINANCE_BEFORE")
    print("BEFORE_OWNER_DML_STATE",initial[0],flush=True)
    print("BEFORE_OWNER_EFFECTIVE_UPDATE",sql(db,
     "SELECT has_table_privilege('c03_legacy','public.finance','UPDATE')").stdout.strip(),flush=True)
    need(initial[0]=="00000","LEGACY_PREMIGRATION_OWNER_MUST_WRITE_"+initial[0])
    need(session_sql(session,"UPDATE public.users SET id=id WHERE false;",
        "USERS_BEFORE")[0]=="00000","LEGACY_USERS_PREMIGRATION")
    # Exact same existing backend stays alive while root model changes owner.
    sql(db,"ALTER TABLE public.finance OWNER TO c03_neutral")
    sql(db,"GRANT SELECT ON public.finance TO c03_legacy")
    after_pid=session_sql(session,"SELECT pg_backend_pid();","PID_AFTER")
    need(after_pid[0]=="00000" and after_pid[1][-1]==pid,
        "EXISTING_PG_SESSION_REPLACED")
    rc=session_sql(session,"UPDATE public.finance SET id=id WHERE false;",
        "FINANCE_FENCED")[0]
    need(rc=="42501","EXISTING_BACKEND_FINANCIAL_DML_NOT_DENIED_"+rc)
    rc=session_sql(session,"INSERT INTO public.finance SELECT * FROM public.finance WHERE false;",
        "FINANCE_INSERT_FENCED")[0]
    need(rc=="42501","EXISTING_BACKEND_INSERT_NOT_DENIED_"+rc)
    need(session_sql(session,"SELECT 1 FROM public.finance LIMIT 0;",
        "FINANCE_SELECT_AFTER")[0]=="00000","PROTECTED_FINANCE_SELECT_LOST")
    need(session_sql(session,"UPDATE public.users SET id=id WHERE false;",
        "USERS_AFTER")[0]=="00000","SAME_BACKEND_NONFINANCE_WRITE_LOST")
    reconnect=sql(db,"UPDATE public.finance SET id=id WHERE false",
        actor="c03_legacy",check=False)
    need(reconnect.returncode!=0 and "permission denied" in reconnect.stderr.lower(),
        "NEW_CONNECTION_FINANCIAL_DML_NOT_DENIED")
    rollback=sql(db,"ALTER TABLE public.finance OWNER TO c03_legacy")
    need(rollback.returncode==0,"ROLLBACK_OWNER_FAILED")
    pid_restored=session_sql(session,"SELECT pg_backend_pid();","PID_RESTORED")
    need(pid_restored[1][-1]==pid,"BACKEND_CHANGE_DURING_ROLLBACK")
    need(session_sql(session,"UPDATE public.finance SET id=id WHERE false;",
        "FINANCE_RESTORED")[0]=="00000","SAME_BACKEND_ROLLBACK_NOT_PROVEN")
    need(sql(db,"SELECT count(*) FROM public.finance").stdout.strip()=="0" and
         sql(db,"SELECT count(*) FROM public.users").stdout.strip()=="0",
         "ZERO_ROW_TEST_MUTATED_DATA")
    result={
     "schema":"aoe2war.c03.preconnected-future-session-pg16-owner-change.v1",
     "status":"PASS_ISOLATED_EXISTING_AND_FUTURE_BACKEND_PRIVILEGE_INVALIDATION",
     "timestamp_utc":dt.datetime.now(dt.timezone.utc).isoformat(),
     "pg16_actual_socket_only":True,
     "same_backend_pid_before_during_after":True,
     "finance_owner_switch_to_neutral_nologin":True,
     "existing_connection_finance_update_denied_sqlstate": "42501",
     "existing_connection_finance_insert_denied_sqlstate": "42501",
     "new_connection_finance_update_denied":True,
     "existing_connection_nonfinance_update_preserved":True,
     "existing_connection_finance_select_preserved":True,
     "existing_connection_after_rollback_finance_update_restored":True,
     "table_row_counts_remained_zero":True,
     "isolated_offhost_only":True,
     "not_full_hdde_data":True,
     "live_c03_finance_writer_fenced":False,
     "full_app_scope_classified":False,
     "coordinated_c06_backup_captured":False,
     "formal_c03_c06_c07_accepted":False,
     "funded_release_authorized":False
    }
    raw=(json.dumps(result,sort_keys=True,indent=2)+chr(10)).encode()
    fd=os.open(RESULT,os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_WRONLY,0o600)
    with os.fdopen(fd,"wb") as f:
     f.write(raw);f.flush();os.fsync(f.fileno())
    print(result["status"],flush=True)
    print("OFFHOST_RECEIPT_SHA256",hashlib.sha256(raw).hexdigest(),flush=True)
    return 0
   finally:
    if session:
     try:session.stdin.close();session.terminate();session.communicate(timeout=3)
     except:session.kill();session.wait(timeout=6)
    if started:
     stop=cmd([BIN/"pg_ctl","-D",data,"-m","immediate","-w","stop"],seconds=40)
     need(stop.returncode==0,"EPHEMERAL_PG_STOP_FAILED")

if __name__=="__main__":
 try:sys.exit(main())
 except Exception as e:
  print("HOLD_ISOLATED_C03_EXISTING_SESSION_OWNER_TEST",type(e).__name__,str(e)[:220])
  sys.exit(3)

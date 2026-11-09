#!/usr/bin/env python3
"""C07 exact ciphertext isolated Intel PG16 restore rehearsal, NEVER financial acceptance.

This program runs only on the FileVault-enabled Intel recovery Mac as its
unprivileged owner. No HEL1/network/wallet/chain mutation, no plaintext archive,
no production PostgreSQL socket, and no claim that a nonquiesced snapshot is
atomic or a valid funded financial release.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import stat
import subprocess
import sys
import tempfile

SCHEMA="wolo.c07.source-pinned-real-intel-pg16-unquiesced-recovery-hold.v1"
HOME=Path.home()
AGE=Path("/usr/local/bin/age")
PG=HOME/".local/aoe2war-pg16-16.15/bin"
KEY=HOME/".wolo-owner-authority/c06-filevault-recovery/c06-recovery-ed25519"
PUB=HOME/".wolo-owner-authority/c06-filevault-recovery/c06-recovery-ed25519.pub"
OWNER_PUB_FP="SHA256:+YyBnbY17VinY0oAjBsILxabobSl95slW+E8R2VPN1c"
PINS={
 "aoe2de_db":{
  "cipher":HOME/".wolo-owner-authority/c06-direct-stream-20261109/unfenced-aoe2de_db.dump.age",
  "sha":"6d7b63d94e1e9fcbea07cadc482e1c8914eb90ceb7b31ade19efcd8a580aa4bc",
  "bytes":349608,"tables":52,"sequences":50,"port":"54512"
 },
 "aoe2hd_db":{
  "cipher":HOME/".wolo-owner-authority/c06-hel1-local-age-offhost-20261109/aoe2hd_db-UNQUIESCED-20261109.pgcustom.age",
  "sha":"b011a0a7949199a8b124650f9d16e3280264cca70380a789438fbe4221e504a4",
  "bytes":872018705,"tables":190,"sequences":180,"port":"54513"
 }
}
class Hold(ValueError):pass
def need(cond,reason):
 if not cond:raise Hold(reason)
def sha(path):
 h=hashlib.sha256()
 with path.open("rb") as stream:
  for block in iter(lambda:stream.read(1048576),b""):h.update(block)
 return h.hexdigest()
def private(path,mode,*,maxbytes=None):
 need(path.is_absolute() and path.is_file() and not path.is_symlink(),
      "OWNER_PRIVATE_FILE_NOT_REGULAR")
 st=path.lstat()
 need(st.st_uid==os.geteuid() and st.st_nlink==1
      and stat.S_IMODE(st.st_mode)==mode,"OWNER_FILE_IDENTITY_OR_MODE")
 if maxbytes is not None:
  need(0<st.st_size<=maxbytes,"OWNER_PRIVATE_FILE_SIZE")
 return st
def run(args,*,timeout=25,**kwargs):
 proc=subprocess.run([str(x) for x in args],capture_output=True,
                     timeout=timeout,**kwargs)
 need(proc.returncode==0,"ISOLATED_SUBPROCESS_FAILED")
 return proc.stdout.decode("utf-8","replace").strip()
def preflight(db):
 need(sys.platform=="darwin" and platform.machine()=="x86_64"
      and os.getuid()==os.geteuid()!=0,"INTEL_NONROOT_ONLY")
 need(db in PINS,"NOT_A_PINNED_DATABASE")
 need(run(["fdesetup","status"],timeout=12)=="FileVault is On.",
      "INTEL_FILEVAULT_REQUIRED")
 private(KEY,0o600,maxbytes=4096)
 private(PUB,0o400,maxbytes=512)
 need(OWNER_PUB_FP in run(["ssh-keygen","-lf",PUB,"-E","sha256"]),
      "RECOVERY_PUBLIC_FINGERPRINT_CHANGED")
 for b in ("initdb","pg_ctl","createdb","pg_restore","psql"):
  need((PG/b).is_file() and os.access(PG/b,os.X_OK),"POSTGRES16_TOOL_MISSING")
 need("16." in run([PG/"pg_restore","--version"]),
      "RECOVERY_POSTGRES_VERSION_CHANGED")
 need(AGE.is_file() and os.access(AGE,os.X_OK),"AGE_CIPHER_BINARY_MISSING")
 root=HOME/".wolo-owner-authority"
 st=root.lstat()
 need(st.st_uid==os.geteuid() and stat.S_IMODE(st.st_mode)==0o700,
      "OWNER_AUTHORITY_DIRECTORY_UNSAFE")
 pin=PINS[db]
 st=private(pin["cipher"],0o600,maxbytes=12*(1<<30))
 need(st.st_size==pin["bytes"] and sha(pin["cipher"])==pin["sha"],
      "PINNED_CIPHERTEXT_SHA_OR_SIZE_MISMATCH")
 with pin["cipher"].open("rb") as f:
  need(f.read(32).startswith(b"age-encryption.org/v1\n"),
       "INVALID_AGE_CIPHER_HEADER")
 return pin
def restore(db):
 pin=preflight(db)
 root=HOME/".wolo-owner-authority"/("c07-source-pinned-"+db+"-20261109")
 need(not root.exists() and not root.is_symlink(),
      "RESTORE_ALREADY_EXISTS_NO_REPLAY")
 root.mkdir(mode=0o700)
 need(stat.S_IMODE(root.stat().st_mode)==0o700,"RESTORE_ROOT_UNSAFE")
 start=datetime.now(timezone.utc).isoformat()
 port=pin["port"]
 data=root/"pgdata"
 with tempfile.TemporaryDirectory(prefix="aoe2war-c07-socket-",dir="/tmp") as socket:
  dbname="c07_"+("hd" if db=="aoe2hd_db" else "de")+"_isolated"
  run([PG/"initdb","-A","trust","-U",os.getenv("USER","tonyblum"),
       "-D",data],timeout=180)
  started=False
  try:
   opts="-c listen_addresses='' -c unix_socket_directories="+socket
   opts+=" -c unix_socket_permissions=0700 -p "+port
   run([PG/"pg_ctl","-D",data,"-o",opts,
        "-l",root/"postgres.log","-w","start"],timeout=90)
   started=True
   run([PG/"createdb","-h",socket,"-p",port,"-U",os.getenv("USER","tonyblum"),
        "-T","template0",dbname],timeout=45)
   decrypt=subprocess.Popen([str(AGE),"-d","-i",str(KEY),str(pin["cipher"])],
             stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
   try:
    imported=subprocess.run([str(PG/"pg_restore"),"--exit-on-error",
        "--no-owner","--no-acl","--no-comments",
        "-h",socket,"-p",port,"-U",os.getenv("USER","tonyblum"),
        "-d",dbname],stdin=decrypt.stdout,stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,timeout=7200)
    decrypt.stdout.close()
    dec_rc=decrypt.wait(timeout=45)
   except BaseException:
    decrypt.kill()
    decrypt.wait(timeout=15)
    raise
   need(imported.returncode==0 and dec_rc==0,
        "AGE_AUTH_OR_PG16_FULL_DATA_RESTORE_FAILED")
   sql="""SELECT 'PUBLIC_TABLES',count(*) FROM pg_class c JOIN pg_namespace n
    ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relkind='r'
    UNION ALL SELECT 'PUBLIC_SEQUENCES',count(*) FROM pg_class c
    JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public'
    AND c.relkind='S'
    UNION ALL SELECT 'TCP_DISABLED',CASE WHEN current_setting(
     'listen_addresses')='' THEN 1 ELSE 0 END;"""
   catalog=run([PG/"psql","-X","-qAt","-v","ON_ERROR_STOP=1",
     "-h",socket,"-p",port,"-U",os.getenv("USER","tonyblum"),
     "-d",dbname,"-c",sql],timeout=50)
   lines=set(catalog.splitlines())
   need("PUBLIC_TABLES|"+str(pin["tables"]) in lines
        and "PUBLIC_SEQUENCES|"+str(pin["sequences"]) in lines
        and "TCP_DISABLED|1" in lines,
        "RESTORED_TABLE_SEQUENCE_OR_TCP_MISMATCH")
  finally:
   if started:
    run([PG/"pg_ctl","-D",data,"-m","fast","-w","stop"],timeout=80)
  need("PUBLIC_TABLES|"+str(pin["tables"]) in lines,"AFTER_STOP_CATALOG")
  result={
   "schema":SCHEMA,"status":"PASS_ACTUAL_PINNED_DB_RECOVERED_HOLD_FINANCIAL_RELEASE",
   "database":db,"verified_utc":datetime.now(timezone.utc).isoformat(),
   "started_utc":start,"source_sha256":sha(Path(__file__).resolve()),
   "cipher_sha256":pin["sha"],"cipher_bytes":pin["bytes"],
   "recovered_public_tables":pin["tables"],
   "recovered_public_sequences":pin["sequences"],
   "isolated_no_tcp":True,"isolated_pg16_stopped":True,
   "m1_owner_private_key_used":False,"intel_filevault_key_used_locally":True,
   "production_db_modified":False,"financial_writer_freeze_proven":False,
   "same_snapshot_bank_journal_wal_captured":False,
   "c06_gate_closed":False,"c07_gate_closed":False,
   "funded_canary_authorized":False}
  b=(json.dumps(result,sort_keys=True,indent=2)+"\n").encode()
  path=root/"c07-unquiesced-physical-restore-receipt.json"
  fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
  with os.fdopen(fd,"wb") as f:f.write(b);f.flush();os.fsync(f.fileno())
  print("PASS_C07_ACTUAL_NONFUNDED_INTEL_PG16_RESTORE",db,
        pin["tables"],pin["sequences"])
  print("SOURCE_SHA256",result["source_sha256"])
  print("ROOT_PRIVATE_RECEIPT_SHA256",hashlib.sha256(b).hexdigest())
  print("HOLD_C07_NOT_COORDINATED_FINANCIAL_SNAPSHOT")

def main():
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument("--mode",choices=("inspect","restore"),required=True)
 parser.add_argument("--db",choices=tuple(PINS),required=True)
 v=parser.parse_args()
 try:
  pin=preflight(v.db)
  if v.mode=="inspect":
   print("PASS_C07_INTEL_PUBLIC_PINNED_CIPHER_INSPECT_NOT_FORMAL")
   return 3
  restore(v.db)
  return 0
 except (Hold,OSError,ValueError,subprocess.SubprocessError) as exc:
  print("HOLD_C07_INTEL_SOURCE_PINNED_RESTORE_FAILED",
        str(exc) if isinstance(exc,Hold) else "PRIVATE_RECOVERY_UNAVAILABLE")
  return 3
if __name__=="__main__":sys.exit(main())

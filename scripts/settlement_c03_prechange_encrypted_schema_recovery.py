#!/usr/bin/env python3
"""C03 exact owner-only encrypted PRE-MIGRATION PostgreSQL schema/role capture.

Pre-change rollback insurance, NOT C06: no data rows, WAL, joint height,
transaction journal, signed maintenance fence or financial release.
NO PostgreSQL WRITE, shell interpolation of user data, wallet or chain RPC.
Plain SQL streams from HEL1 to local age encryption through SSH, never disk.
Two separately verified owner recovery recipients; ciphertext is uploaded
over strict pinned Intel SSH, receipt SHA checked, and M1 temp is deleted.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import base64
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shlex
import stat
import subprocess
import sys
import tempfile

SCHEMA="wolo.c03.dual-recipient-encrypted-schema-rollback-preflight.v1"
INTEL_FP="SHA256:bU10Y1SlXTa8YCm5lphUYsMrxMSdP8D0VIQJ0C2zeEg"
M1_RECOVERY_FP="SHA256:MfpOL/mXaiHhlPqSaB8ClcVSAUONefzrj2qtPHlsRyU"
INTEL_RECOVERY_FP="SHA256:I2ho/SRV9RhQFtUSY3qBEC9Gsr0YsPvbr7t8do18G0I"
M1_RECOVERY_PUB=Path.home()/".wolo-owner-authority/recovery-keys/c01-m1-recovery-ed25519.pub"
AGE=Path.home()/".local/bin/age"
BASE=Path.home()/".wolo-owner-authority/c03-prechange-schema-20261108"
FINAL="schema-prechange-encrypted-receipt.json"
EXISTING_GLOBALS_CIPHER_SHA="26d31d0b3a77980823dbab65f413a87df1d51b003e3b843e3fab012f54b6e022"
EXISTING_GLOBALS_CIPHER_BYTES=2443
REMOTE_BASE=".wolo-owner-authority/c03-prechange-schema-20261108"
MAX_ENCRYPTED=128<<20
COMMANDS={
    "globals": "/usr/bin/sudo -u postgres /usr/lib/postgresql/16/bin/pg_dumpall --globals-only --no-role-passwords",
    "hd": "/usr/bin/sudo -u postgres /usr/lib/postgresql/16/bin/pg_dump --schema-only --dbname=aoe2hd_db",
    "de": "/usr/bin/sudo -u postgres /usr/lib/postgresql/16/bin/pg_dump --schema-only --dbname=aoe2de_db",
}
REMOTE_WRITE=r"""
from pathlib import Path
import hashlib,os,stat,sys
label=sys.argv[1]
if label not in ("globals","hd","de"):sys.exit(21)
root=Path.home()/".wolo-owner-authority"/"c03-prechange-schema-20261108"
if root.is_symlink():sys.exit(22)
root.mkdir(mode=0o700,parents=True,exist_ok=True)
st=root.lstat()
if not stat.S_ISDIR(st.st_mode) or st.st_uid!=os.geteuid() or stat.S_IMODE(st.st_mode)!=0o700:sys.exit(23)
path=root/("prechange-"+label+".sql.age")
if path.exists() or path.is_symlink():sys.exit(24)
fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600)
h=hashlib.sha256()
count=0
try:
 while True:
  piece=sys.stdin.buffer.read(131072)
  if not piece:break
  count+=len(piece)
  if count>134217728:raise ValueError("ENCRYPTED_FILE_TOO_LARGE")
  h.update(piece)
  cursor=memoryview(piece)
  while len(cursor):
   n=os.write(fd,cursor)
   if n<=0:raise OSError("WRITE_FAILED")
   cursor=cursor[n:]
 if count<128:raise ValueError("INCOMPLETE_CIPHERTEXT")
 os.fsync(fd)
finally:
 os.close(fd)
if not count or count>134217728:
 path.unlink(missing_ok=True)
 sys.exit(25)
print(h.hexdigest()+" "+str(count))
"""
REMOTE_READ=r"""
from pathlib import Path
import hashlib,os,stat,sys
label=sys.argv[1]
if label not in ("globals","hd","de"):sys.exit(31)
p=Path.home()/".wolo-owner-authority"/"c03-prechange-schema-20261108"/("prechange-"+label+".sql.age")
if p.is_symlink():sys.exit(32)
s=p.stat()
if not stat.S_ISREG(s.st_mode) or s.st_uid!=os.geteuid() or stat.S_IMODE(s.st_mode)!=0o600 or s.st_size>134217728:sys.exit(33)
h=hashlib.sha256()
with p.open("rb") as f:
 while True:
  chunk=f.read(131072)
  if not chunk:break
  h.update(chunk)
print(h.hexdigest()+" "+str(s.st_size))
"""

class Hold(RuntimeError):
    pass

def need(ok,reason):
    if not ok:raise Hold(reason)

def digest(raw):return hashlib.sha256(raw).hexdigest()

def ssh_hel1(command,*,input=None,timeout=15):
    return subprocess.run(["/usr/bin/ssh","-o","BatchMode=yes",
        "-o","ConnectTimeout=7","root@hel1",command],input=input,
        capture_output=True,timeout=timeout)

def fingerprint(raw):
    try:
        bits=raw.decode("ascii").strip().split()
        need(len(bits) in (2,3) and bits[0]=="ssh-ed25519","UNEXPECTED_SSH_ED25519_RECIPIENT")
        blob=base64.b64decode(bits[1],validate=True)
        need(40<=len(blob)<=4096 and blob[4:15]==b"ssh-ed25519","INVALID_ED25519_SSH_BLOB")
    except (UnicodeError,ValueError,base64.binascii.Error) as e:
        raise Hold("SSH_PUBLIC_KEY_PARSE_FAILED") from e
    return "SHA256:"+base64.b64encode(hashlib.sha256(blob).digest()).decode().rstrip("=")

def prepare():
    need(sys.platform=="darwin" and platform.machine()=="arm64"
         and os.geteuid()!=0,"M1_OWNER_NONROOT_REQUIRED")
    need(AGE.is_file() and os.access(AGE,os.X_OK),"AGE_BINARY_UNAVAILABLE")
    pub=M1_RECOVERY_PUB.read_bytes()
    need(fingerprint(pub)==M1_RECOVERY_FP,"M1_RECOVERY_IDENTITY_DRIFT")
    scanned=ssh_hel1("/usr/bin/ssh-keyscan -T 5 -t ed25519 -p 22996 127.0.0.1")
    need(scanned.returncode==0,"INTEL_REVERSE_HOST_SCAN_FAILED")
    lines=[line for line in scanned.stdout.splitlines() if line and not line.startswith(b"#")]
    need(len(lines)==1 and len(lines[0].split())==3,"INTEL_REVERSE_HOST_KEY_AMBIGUITY")
    parts=lines[0].split()
    need(parts[1]==b"ssh-ed25519","INTEL_REVERSE_HOSTKEY_ALGORITHM")
    got="SHA256:"+base64.b64encode(hashlib.sha256(base64.b64decode(parts[2])).digest()).decode().rstrip("=")
    need(got==INTEL_FP,"INTEL_REVERSE_HOST_IDENTITY_DRIFT")
    return pub,scanned.stdout

def intel(known,command,*,input=None,timeout=20):
    proxy="/usr/bin/ssh -o BatchMode=yes -o ConnectTimeout=7 root@hel1 -W 127.0.0.1:22996"
    return subprocess.run(["/usr/bin/ssh","-o","BatchMode=yes","-o","ConnectTimeout=7",
      "-o","ConnectionAttempts=1","-o","StrictHostKeyChecking=yes",
      "-o","UserKnownHostsFile="+str(known),"-o","ProxyCommand="+proxy,
      "-p","22996","tonyblum@127.0.0.1",command],
      input=input,capture_output=True,timeout=timeout)

def intel_py(known,code,argument=None,*,payload=None,timeout=25):
    c="python3 -c "+shlex.quote(code)
    if argument is not None:c+=" "+shlex.quote(argument)
    return intel(known,c,input=payload,timeout=timeout)

def evidence_context(tmp,pub,scan):
    known=tmp/"intel-known-hosts";known.write_bytes(scan);known.chmod(0o600)
    test=intel(known,'cat "$HOME/.wolo-owner-authority/recovery-keys/c01-offhost-recovery-ed25519.pub"')
    need(test.returncode==0,"OFFHOST_RECOVERY_RECIPIENT_UNAVAILABLE")
    need(fingerprint(test.stdout)==INTEL_RECOVERY_FP,"OFFHOST_RECOVERY_RECIPIENT_DRIFT")
    recipient=tmp/"offhost-recovery.pub"
    recipient.write_bytes(test.stdout);recipient.chmod(0o600)
    return known,recipient

def age_encrypt_stream(temporary,recipient,label):
    output=temporary/("prechange-"+label+".sql.age")
    producer=subprocess.Popen(["/usr/bin/ssh","-o","BatchMode=yes",
          "-o","ConnectTimeout=7","root@hel1",COMMANDS[label]],
          stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    need(producer.stdout is not None,"SCHEMA_READ_PIPE_MISSING")
    try:
        encrypt=subprocess.run([str(AGE),"-R",str(M1_RECOVERY_PUB),
                 "-R",str(recipient),"-o",str(output)],stdin=producer.stdout,
                 stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=120)
        producer.stdout.close()
        rc=producer.wait(timeout=15)
    except BaseException:
        producer.kill()
        producer.wait(timeout=4)
        raise
    need(encrypt.returncode==0 and rc==0,"PG_DUMP_OR_AGE_STREAM_FAILED")
    need(output.is_file() and 128<output.stat().st_size<=MAX_ENCRYPTED,
         "BOUNDED_ENCRYPTED_SCHEMA_SIZE")
    with output.open("rb") as f:
        first=f.read(64)
        f.seek(0)
        cipher_hash=hashlib.file_digest(f,"sha256").hexdigest()
    need(first.startswith(b"age-encryption.org/v1\n"),"NOT_AGE_CIPHERTEXT")
    return output,cipher_hash

def parse_verified_transfer(raw,label,expected,length):
    lines=raw.decode("ascii").strip().splitlines()
    need(len(lines)==1 and re.fullmatch(r"[a-f0-9]{64} [1-9][0-9]*",lines[0]) is not None,
         "OFFHOST_SHA_RECEIPT_MALFORMED")
    h,s=lines[0].split()
    need(h==expected and int(s)==length,
         "OFFHOST_CIPHERTEXT_SHA_OR_LENGTH_DRIFT")
    return {"encrypted_sha256":h,"encrypted_bytes":int(s),
            "target":REMOTE_BASE+"/prechange-"+label+".sql.age"}

def capture(known,recipient,tmp,*,resume_globs=False):
    results={}
    if resume_globs:
        inspected=intel_py(known,REMOTE_READ,"globals",timeout=15)
        need(inspected.returncode==0,"EXISTING_GLOBALS_READBACK_UNAVAILABLE")
        results["globals"]=parse_verified_transfer(
            inspected.stdout,"globals",EXISTING_GLOBALS_CIPHER_SHA,
            EXISTING_GLOBALS_CIPHER_BYTES)
    for label in (("hd","de") if resume_globs else ("globals","hd","de")):
        output,h=age_encrypt_stream(tmp,recipient,label)
        with output.open("rb") as data:
            payload=data.read()
        need(len(payload)<=MAX_ENCRYPTED and digest(payload)==h,"ENCRYPTED_LOCAL_HASH_RACE")
        upload=intel_py(known,REMOTE_WRITE,label,payload=payload,timeout=55)
        need(upload.returncode==0,"INTEL_CIPHERTEXT_UPLOAD_FAILED_"+label)
        receipt=parse_verified_transfer(upload.stdout,label,h,len(payload))
        inspected=intel_py(known,REMOTE_READ,label,timeout=15)
        need(inspected.returncode==0,"INTEL_RETENTION_READBACK_UNAVAILABLE_"+label)
        parse_verified_transfer(inspected.stdout,label,h,len(payload))
        results[label]=receipt
        output.unlink()
    return results

def write_receipt(source_sha,results):
    BASE.mkdir(mode=0o700,parents=True,exist_ok=True)
    st=BASE.lstat()
    need(stat.S_ISDIR(st.st_mode) and st.st_uid==os.geteuid()
         and stat.S_IMODE(st.st_mode)==0o700 and not BASE.is_symlink(),
         "LOCAL_RECEIPT_DIRECTORY_UNSAFE")
    receipt={
        "schema":SCHEMA,"utc":datetime.now(timezone.utc).isoformat(),
        "status":"PASS_C03_PRECHANGE_OFFHOST_ENCRYPTED_ROLLBACK_SCHEMA_ONLY",
        "source_sha256":source_sha,
        "dual_recipient_public_identity_verified":True,
        "intel_host_ssh_identity_pinned":True,
        "three_schema_and_global_captures_retained_on_intel":results,
        "hd_de_full_row_data_included":False,
        "joint_database_snapshot_atomic":False,
        "wal_and_settlement_journals_included":False,
        "offhost_decryption_and_restore_tested":False,
        "c03_all_writers_fenced":False,
        "c06_full_quiesced_backup_captured":False,
        "c07_same_capture_recovery_proven":False,
        "financial_release_authorized":False,
        "production_database_mutated":False,
    }
    path=BASE/FINAL
    need(not path.exists() and not path.is_symlink(),"PRIVATE_RECEIPT_ALREADY_EXISTS")
    data=(json.dumps(receipt,sort_keys=True,indent=2)+"\n").encode()
    fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,"wb") as f:f.write(data);f.flush();os.fsync(f.fileno())
    need(stat.S_IMODE(path.stat().st_mode)==0o600,"RECEIPT_MODE_DRIFT")
    return digest(data)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode",choices=("inspect","capture","resume-globals"),default="inspect")
    args=parser.parse_args()
    try:
        source_sha=digest(Path(__file__).read_bytes())
        pub,scan=prepare()
        with tempfile.TemporaryDirectory(prefix="c03-schema-owner-only-",
                                         dir=Path.home()/".wolo-owner-authority") as t:
            tmp=Path(t);tmp.chmod(0o700)
            known,recipient=evidence_context(tmp,pub,scan)
            if args.mode=="inspect":
                print(json.dumps({
                    "schema":SCHEMA,"status":"HOLD_READY_FOR_OWNER_C03_SCHEMA_PRECAPTURE",
                    "owner_recovery_recipient_verified":True,
                    "offhost_recovery_recipient_verified":True,
                    "intel_reverse_ssh_host_pinned":True,
                    "source_sha256":source_sha,
                    "financial_release_authorized":False,
                    "production_database_mutated":False},sort_keys=True))
                return 3
            need(not (BASE/FINAL).exists(),"CAPTURE_NOT_REPLAYABLE")
            result=capture(known,recipient,tmp,
                           resume_globs=args.mode=="resume-globals")
            receipt_sha=write_receipt(source_sha,result)
        print(json.dumps({"schema":SCHEMA,
            "status":"PASS_C03_PRECHANGE_OFFHOST_ENCRYPTED_ROLLBACK_SCHEMA_ONLY",
            "source_sha256":source_sha,
            "private_receipt_sha256":receipt_sha,
            "target_count":len(result),
            "financial_release_authorized":False,
            "production_database_mutated":False,
            "full_c06_backup":False},sort_keys=True))
        return 0
    except (Hold,OSError,subprocess.SubprocessError,UnicodeError,ValueError) as exc:
        print(json.dumps({"schema":SCHEMA,"status":"HOLD_C03_SCHEMA_PRECHANGE_NOT_COMPLETE",
                          "reason":str(exc) if isinstance(exc,Hold) else "TRANSIT_OR_SOURCE_UNAVAILABLE",
                          "financial_release_authorized":False,
                          "production_database_mutated":False},sort_keys=True))
        return 2

if __name__=="__main__":
    sys.exit(main())

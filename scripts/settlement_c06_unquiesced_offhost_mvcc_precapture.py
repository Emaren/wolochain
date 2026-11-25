#!/usr/bin/env python3
"""C06 preparatory LIVE-MVCC (UNQUIESCED) HD/DE encrypted off-host dump.

This is NOT a C06/C07 release proof. Both PostgreSQL databases may be
written during export; there is NO cross-database atomicity or WAL/journal
snapshot. It proves a recoverable transport candidate, NOT quiescence.

One fixed database per invocation, low I/O/CPU priority on HEL1, remote Pg16
pg_dump -Fc -Z3, plaintext bytes only in SSH->age pipe on owner M1,
ciphertext only on owner0700 temporary M1 disk, then independently hash-
confirmed offhost Intel0600 retention via pinned SSH. No private key read,
payment, database mutation, service/role change, wallet/chain RPC, or signer.
"""
from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import resource
import shlex
import stat
import subprocess
import sys
import tempfile

SCHEMA="wolo.c06.unquiesced-mvcc-dual-public-key-offhost-precapture-hold.v1"
HOST_FP="SHA256:bU10Y1SlXTa8YCm5lphUYsMrxMSdP8D0VIQJ0C2zeEg"
M1_FP="SHA256:MfpOL/mXaiHhlPqSaB8ClcVSAUONefzrj2qtPHlsRyU"
INTEL_FP="SHA256:I2ho/SRV9RhQFtUSY3qBEC9Gsr0YsPvbr7t8do18G0I"
M1_PUB=Path.home()/".wolo-owner-authority/recovery-keys/c01-m1-recovery-ed25519.pub"
AGE=Path.home()/".local/bin/age"
BASE=Path.home()/".wolo-owner-authority/c06-unquiesced-mvcc-precapture-20261108"
REMOTE_BASE=".wolo-owner-authority/c06-unquiesced-mvcc-precapture-20261108"
DBS=("aoe2de_db","aoe2hd_db")
MAX_CIPHER=12*(1<<30)
M1_FREE_FLOOR=16*(1<<30)
INTEL_FREE_FLOOR=20*(1<<30)
PG="/usr/lib/postgresql/16/bin/pg_dump"
# Fixed commands and DB identities. No caller-supplied shell interpolation.
DUMP={
  db:("/usr/sbin/runuser -u postgres -- /usr/bin/nice -n 15 "
      "/usr/bin/ionice -c3 "+PG+" -F c -Z 3 "
      "--lock-wait-timeout=5000 -d "+db)
  for db in DBS
}

REMOTE_WRITE=r"""
import sys,os,hashlib,stat
from pathlib import Path
label,expected_sha,expected_size=sys.argv[1],sys.argv[2],int(sys.argv[3])
if label not in ("aoe2de_db","aoe2hd_db"):sys.exit(21)
if len(expected_sha)!=64 or any(c not in "0123456789abcdef" for c in expected_sha):sys.exit(22)
if expected_size<128 or expected_size>12884901888:sys.exit(23)
root=Path.home()/".wolo-owner-authority"/"c06-unquiesced-mvcc-precapture-20261108"
if root.is_symlink():sys.exit(24)
root.mkdir(mode=0o700,parents=True,exist_ok=True)
s=root.lstat()
if not stat.S_ISDIR(s.st_mode) or stat.S_IMODE(s.st_mode)!=0o700 or s.st_uid!=os.geteuid():sys.exit(25)
final=root/("unfenced-"+label+".dump.age")
tmp=root/("unfenced-"+label+".dump.age.part")
if final.exists() or final.is_symlink() or tmp.exists() or tmp.is_symlink():sys.exit(26)
f=os.open(tmp,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
h=hashlib.sha256();total=0;prefix=b"";accepted=False
try:
 with os.fdopen(f,"wb") as stream:
  while True:
   b=sys.stdin.buffer.read(131072)
   if not b:break
   total+=len(b)
   if total>expected_size:raise ValueError("CIPHER_STREAM_OVERFLOW")
   if len(prefix)<64:prefix=(prefix+b)[:64]
   h.update(b);stream.write(b)
  stream.flush();os.fsync(stream.fileno())
 if total!=expected_size or h.hexdigest()!=expected_sha:raise ValueError("REMOTE_CIPHER_DIGEST_DRIFT")
 if not prefix.startswith(b"age-encryption.org/v1\n"):raise ValueError("NOT_AGE_ENCRYPTION")
 tmp.rename(final)
 os.chmod(final,0o600)
 accepted=True
 print(h.hexdigest()+" "+str(total))
finally:
 if not accepted:
  try:tmp.unlink()
  except OSError:pass
"""
REMOTE_READ=r"""
import sys,os,hashlib,stat
from pathlib import Path
label=sys.argv[1]
if label not in ("aoe2de_db","aoe2hd_db"):sys.exit(31)
root=Path.home()/".wolo-owner-authority"/"c06-unquiesced-mvcc-precapture-20261108"
p=root/("unfenced-"+label+".dump.age")
if p.is_symlink() or root.is_symlink():sys.exit(32)
s=p.stat()
if not stat.S_ISREG(s.st_mode) or s.st_uid!=os.geteuid() or stat.S_IMODE(s.st_mode)!=0o600 or s.st_size>12884901888:sys.exit(33)
h=hashlib.sha256()
with p.open("rb") as f:
 while True:
  b=f.read(131072)
  if not b:break
  h.update(b)
print(h.hexdigest()+" "+str(s.st_size))
"""
REMOTE_CAPACITY=r"""
from pathlib import Path
import os,stat
home=Path.home()
space=os.statvfs(str(home))
print(space.f_bavail*space.f_frsize)
"""

class Hold(ValueError):pass

def require(ok,reason):
    if not ok:raise Hold(reason)

def sha(b):return hashlib.sha256(b).hexdigest()

def fingerprint(raw):
    try:
        a=raw.decode("ascii").strip().split()
        require(len(a) in (2,3) and a[0]=="ssh-ed25519","UNRECOGNIZED_RECOVERY_KEY_TYPE")
        blob=base64.b64decode(a[1],validate=True)
        require(len(blob)>=47 and blob[4:15]==b"ssh-ed25519","NOT_ED25519_BLOB")
    except (UnicodeError,ValueError,base64.binascii.Error) as e:
        raise Hold("RECOVERY_PUBLIC_KEY_MALFORMED") from e
    return "SHA256:"+base64.b64encode(hashlib.sha256(blob).digest()).decode().rstrip("=")

def hel1(command,*,timeout=14):
    return subprocess.run(["ssh","-o","BatchMode=yes","-o","ConnectTimeout=7",
                           "root@hel1",command],capture_output=True,timeout=timeout)

def prep():
    require(sys.platform=="darwin" and platform.machine()=="arm64"
            and os.geteuid()==os.getuid()!=0,"UNAUTHORIZED_M1_OWNER_HOST")
    require(AGE.is_file() and os.access(AGE,os.X_OK),"AGE_BINARY_UNAVAILABLE")
    require(M1_PUB.is_file() and fingerprint(M1_PUB.read_bytes())==M1_FP,
            "M1_RECOVERY_IDENTITY_DRIFT")
    require(BASE.parent.is_dir() and stat.S_IMODE(BASE.parent.stat().st_mode)==0o700,
            "M1_OWNER_PRIVATE_BASE_UNSAFE")
    scan=hel1("ssh-keyscan -T 5 -t ed25519 -p 22996 127.0.0.1",timeout=12)
    require(scan.returncode==0,"OFFHOST_SSH_HOST_SCAN_FAILED")
    lines=[v for v in scan.stdout.splitlines() if v and not v.startswith(b"#")]
    require(len(lines)==1 and len(lines[0].split())==3,
            "AMBIGUOUS_OFFHOST_HOST_KEY")
    fields=lines[0].split()
    require(fields[1]==b"ssh-ed25519","OFFHOST_HOST_KEY_ALGORITHM")
    host="SHA256:"+base64.b64encode(
        hashlib.sha256(base64.b64decode(fields[2])).digest()).decode().rstrip("=")
    require(host==HOST_FP,"OFFHOST_HOST_KEY_DRIFT")
    return scan.stdout

def intel(known,cmd,*,stdin=None,timeout=25):
    proxy="ssh -o BatchMode=yes -o ConnectTimeout=7 hel1 -W 127.0.0.1:22996"
    base=["ssh","-T","-o","BatchMode=yes","-o","ConnectTimeout=7",
          "-o","ConnectionAttempts=1","-o","StrictHostKeyChecking=yes",
          "-o","UserKnownHostsFile="+str(known),"-o","ProxyCommand="+proxy,
          "-p","22996","tonyblum@127.0.0.1",cmd]
    return subprocess.run(base,stdin=stdin,capture_output=True,timeout=timeout)

def intel_py(known,code,*args,stdin=None,timeout=25):
    cmd="python3 -c "+shlex.quote(code)
    for a in args:cmd+=" "+shlex.quote(str(a))
    return intel(known,cmd,stdin=stdin,timeout=timeout)

def prepare_intel(work,scan):
    known=work/"known_hosts"
    known.write_bytes(scan);known.chmod(0o600)
    r=intel(known,'cat "$HOME/.wolo-owner-authority/recovery-keys/c01-offhost-recovery-ed25519.pub"',timeout=15)
    require(r.returncode==0 and fingerprint(r.stdout)==INTEL_FP,
            "INTEL_RECOVERY_IDENTITY_DRIFT")
    pub=work/"intel-recovery.pub"
    pub.write_bytes(r.stdout);pub.chmod(0o600)
    capacity=intel_py(known,REMOTE_CAPACITY,timeout=15)
    require(capacity.returncode==0 and re.fullmatch(rb"[0-9]+\n?",capacity.stdout) is not None
            and int(capacity.stdout)>=INTEL_FREE_FLOOR,
            "INTEL_OFFHOST_STORAGE_INSUFFICIENT")
    return known,pub

def m1_free():
    st=os.statvfs(str(Path.home()))
    return st.f_bavail*st.f_frsize

def encrypt_live_db(db,work,offhost):
    require(db in DBS,"DATABASE_NOT_ALLOWLISTED")
    require(m1_free()>=M1_FREE_FLOOR,"M1_STORAGE_FLOOR_NOT_MET")
    tmp=work/("unfenced-"+db+".dump.age")
    # Age receives only streaming compressed PostgreSQL dump bytes; never a
    # plaintext temporary file. RLIMIT_FSIZE caps a runaway stdout stream.
    proc=subprocess.Popen(["ssh","-T","-o","BatchMode=yes",
        "-o","ConnectTimeout=7","root@hel1",DUMP[db]],
        stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    require(proc.stdout is not None,"PG_DUMP_PIPE_UNAVAILABLE")
    def limit():
        resource.setrlimit(resource.RLIMIT_FSIZE,(MAX_CIPHER,MAX_CIPHER))
    try:
        enc=subprocess.run([str(AGE),"-R",str(M1_PUB),"-R",str(offhost),
                "-o",str(tmp)],stdin=proc.stdout,capture_output=True,
                timeout=1500,preexec_fn=limit)
        proc.stdout.close()
        exit_code=proc.wait(timeout=15)
    except BaseException:
        proc.kill()
        proc.wait(timeout=6)
        raise
    require(enc.returncode==0 and exit_code==0,"PG_DUMP_AGE_STREAM_FAILED")
    require(tmp.is_file() and not tmp.is_symlink()
            and tmp.stat().st_size>=128 and tmp.stat().st_size<=MAX_CIPHER,
            "ENCRYPTED_DUMP_SIZE_OUT_OF_BOUNDS")
    with tmp.open("rb") as f:
        require(f.read(32).startswith(b"age-encryption.org/v1\n"),
                "ENCRYPTED_DUMP_NOT_AGE_V1")
        f.seek(0)
        h=hashlib.sha256()
        while True:
            b=f.read(1<<20)
            if not b:break
            h.update(b)
    return tmp,h.hexdigest()

def verify_sha_line(data,expected,size):
    try:
        rows=data.decode("ascii").strip().splitlines()
    except UnicodeError:
        raise Hold("OFFHOST_CIPHERTEXT_RECEIPT_NONASCII") from None
    require(len(rows)==1 and re.fullmatch(r"[a-f0-9]{64} [1-9][0-9]*",rows[0]) is not None,
            "OFFHOST_CIPHERTEXT_RECEIPT_MALFORMED")
    got,length=rows[0].split()
    require(got==expected and int(length)==size,"OFFHOST_SHA_OR_SIZE_MISMATCH")

def upload_and_verify(known,db,encrypted,expected):
    size=encrypted.stat().st_size
    require(size<=MAX_CIPHER,"OFFHOST_ENCRYPTED_FILE_TOO_LARGE")
    with encrypted.open("rb") as src:
        delivered=intel_py(known,REMOTE_WRITE,db,expected,str(size),
                           stdin=src,timeout=1800)
    require(delivered.returncode==0,"OFFHOST_CIPHERTEXT_STORE_FAILED")
    verify_sha_line(delivered.stdout,expected,size)
    checked=intel_py(known,REMOTE_READ,db,timeout=120)
    require(checked.returncode==0,"OFFHOST_CIPHERTEXT_READBACK_FAILED")
    verify_sha_line(checked.stdout,expected,size)
    return {"ciphertext_sha256":expected,"ciphertext_bytes":size,
            "offhost_path":REMOTE_BASE+"/unfenced-"+db+".dump.age"}

def persist_receipt(db,source_sha,observation):
    require(db in DBS,"NONALLOWLISTED_DATABASE")
    BASE.mkdir(mode=0o700,exist_ok=True)
    s=BASE.lstat()
    require(stat.S_ISDIR(s.st_mode) and not BASE.is_symlink()
            and s.st_uid==os.geteuid() and stat.S_IMODE(s.st_mode)==0o700,
            "PRIVATE_RECEIPT_DIRECTORY_UNSAFE")
    target=BASE/("unfenced-"+db+"-capture-receipt.json")
    require(not target.exists() and not target.is_symlink(),
            "CAPTURE_RECEIPT_ALREADY_EXISTS")
    obj={
        "schema":SCHEMA,"captured_utc":datetime.now(timezone.utc).isoformat(),
        "status":"PASS_UNQUIESCED_MVCC_OFFHOST_DUMP_HOLD_FINANCIAL_RELEASE",
        "database":db,
        "source_sha256":source_sha,
        "export_command":"fixed_postgresql16_pg_dump_Fc_Z3_low_priority",
        "m1_private_recovery_public_fingerprint":M1_FP,
        "intel_private_recovery_public_fingerprint":INTEL_FP,
        "intel_pinned_ssh_host_fingerprint":HOST_FP,
        **observation,
        "production_database_mutated":False,
        "global_writer_fence_proven":False,
        "cross_database_atomic_snapshot":False,
        "full_wal_and_settlement_journals_captured":False,
        "decryption_restoration_verified":False,
        "c06_formal_backup_gate_closed":False,
        "c07_formal_recovery_gate_closed":False,
        "custody_financial_release_authorized":False,
        "c09_funded_signature_supplied":False,
    }
    content=(json.dumps(obj,sort_keys=True,indent=2)+"\n").encode()
    fd=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,"wb") as f:
        f.write(content);f.flush();os.fsync(f.fileno())
    return sha(content)

def run(db,mode):
    source=sha(Path(__file__).read_bytes())
    scan=prep()
    with tempfile.TemporaryDirectory(prefix="wolo-c06-unfenced-owner-",
       dir=str(BASE.parent)) as name:
        work=Path(name);work.chmod(0o700)
        known,offhost=prepare_intel(work,scan)
        if mode=="inspect":
            return {"schema":SCHEMA,"status":"HOLD_C06_UNQUIESCED_OFFHOST_CAPTURE_READY",
                "source_sha256":source,"intel_two_recovery_recipients_verified":True,
                "offhost_space_floor_verified":True,"production_database_mutated":False,
                "financial_release_authorized":False}
        require(db in DBS,"DATABASE_NOT_ALLOWLISTED")
        require(not (BASE/("unfenced-"+db+"-capture-receipt.json")).exists(),
                "CAPTURE_ALREADY_COMPLETE")
        artifact,hash_value=encrypt_live_db(db,work,offhost)
        observed=upload_and_verify(known,db,artifact,hash_value)
        artifact.unlink()
        receipt_hash=persist_receipt(db,source,observed)
        return {"schema":SCHEMA,"status":"PASS_UNQUIESCED_MVCC_OFFHOST_CAPTURE_HOLD",
                "database":db,"source_sha256":source,
                "owner_private_receipt_sha256":receipt_hash,
                "offhost_ciphertext_sha256":observed["ciphertext_sha256"],
                "offhost_ciphertext_bytes":observed["ciphertext_bytes"],
                "financial_release_authorized":False,
                "c06_formal_backup_gate_closed":False}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode",choices=("inspect","capture"),default="inspect")
    parser.add_argument("--db",choices=DBS)
    args=parser.parse_args()
    try:
        report=run(args.db,args.mode)
    except (Hold,OSError,subprocess.SubprocessError,UnicodeError,ValueError) as e:
        print(json.dumps({"schema":SCHEMA,
            "status":"HOLD_C06_UNQUIESCED_OFFHOST_PRECAPTURE_FAILED",
            "reason":str(e) if isinstance(e,Hold) else "PRIVATE_TRANSIT_OR_SOURCE_UNAVAILABLE",
            "financial_release_authorized":False,"production_database_mutated":False},
            sort_keys=True))
        return 2
    print(json.dumps(report,sort_keys=True))
    return 3 if args.mode=="inspect" else 0

if __name__=="__main__":sys.exit(main())

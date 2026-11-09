#!/usr/bin/env python3
"""Nonfunded C06 streaming precapture, never formal C06/C07 or a writer freeze.
Streams pg_dump custom from HEL1 through age on M1 to pinned Intel offhost.
Only public encryption identities read; no private keys touched.
"""
from __future__ import annotations
import argparse, base64, datetime, hashlib, json, os, pathlib, re, shlex, stat, subprocess, sys, time
HOME = pathlib.Path.home()
BASE = HOME / '.wolo-owner-authority/c06-full-precapture-20261108'
M1_PUB = HOME / '.wolo-owner-authority/recovery-keys/c01-m1-recovery-ed25519.pub'
INTEL_PUB = BASE / 'intel-c06-filevault-recovery.pub'
KNOWN = HOME / '.wolo-owner-authority/c08-intel-approved-ssh-host-20261108'
AGE = HOME / '.local/bin/age'
REMOTE_ROOT='.wolo-owner-authority/c06-direct-stream-20261109'
M1_FP='SHA256:MfpOL/mXaiHhlPqSaB8ClcVSAUONefzrj2qtPHlsRyU'
INTEL_FP='SHA256:+YyBnbY17VinY0oAjBsILxabobSl95slW+E8R2VPN1c'
KNOWN_SHA='2f2c5a5efadea9486ec0beb4188ffb5dbfd6b5c8d0767886cabc481a6ecad7cf'
DBS=('aoe2de_db','aoe2hd_db')
MAX_CIPHER=12*(1<<30)
DUMP={db:'/usr/sbin/runuser -u postgres -- /usr/bin/nice -n 15 /usr/bin/ionice -c3 /usr/lib/postgresql/16/bin/pg_dump -F c -Z 3 --lock-wait-timeout=5000 -d '+db for db in DBS}
RECV=r'''
import sys,os,stat,hashlib
from pathlib import Path
name=sys.argv[1]
if name not in ('aoe2de_db','aoe2hd_db'):sys.exit(21)
root=Path.home()/'.wolo-owner-authority/c06-direct-stream-20261109'
if root.is_symlink():sys.exit(22)
root.mkdir(mode=0o700,parents=True,exist_ok=True)
s=root.lstat()
if not stat.S_ISDIR(s.st_mode) or stat.S_IMODE(s.st_mode)!=0o700 or s.st_uid!=os.geteuid():sys.exit(23)
part=root/('unfenced-'+name+'.dump.age.part')
final=root/('unfenced-'+name+'.dump.age')
if final.exists() or part.exists() or final.is_symlink() or part.is_symlink():sys.exit(24)
fd=os.open(part,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600)
h=hashlib.sha256();total=0;head=b''
with os.fdopen(fd,'wb') as f:
 while True:
  b=sys.stdin.buffer.read(131072)
  if not b:break
  total+=len(b)
  if total>12*(1<<30):sys.exit(25)
  if len(head)<32:head=(head+b)[:32]
  f.write(b);h.update(b)
 f.flush();os.fsync(f.fileno())
if total<128 or not head.startswith(b'age-encryption.org/v1\n'):sys.exit(26)
print(h.hexdigest(),total,flush=True)
'''
VERIFY=r'''
import sys,hashlib,os,stat
from pathlib import Path
name,expected_sha,expected_len,phase=sys.argv[1:5]
if name not in ('aoe2de_db','aoe2hd_db') or phase not in ('stage','finalize','readback'):sys.exit(31)
root=Path.home()/'.wolo-owner-authority/c06-direct-stream-20261109'
part=root/('unfenced-'+name+'.dump.age.part')
final=root/('unfenced-'+name+'.dump.age')
p=final if phase=='readback' else part
if not p.exists() or p.is_symlink():sys.exit(32)
s=p.stat()
if not stat.S_ISREG(s.st_mode) or s.st_uid!=os.geteuid() or stat.S_IMODE(s.st_mode)!=0o600:sys.exit(33)
h=hashlib.sha256();total=0
with p.open('rb') as f:
 while True:
  b=f.read(1<<20)
  if not b:break
  total+=len(b);h.update(b)
if str(total)!=expected_len or h.hexdigest()!=expected_sha:sys.exit(34)
if phase=='finalize':
 if final.exists() or final.is_symlink():sys.exit(35)
 part.rename(final)
print('PASS_REMOTE_CIPHER_'+phase.upper(),h.hexdigest(),total)
'''
CAPACITY=r'''
import os,stat
from pathlib import Path
h=Path.home();root=h/'.wolo-owner-authority'
if root.is_symlink() or not root.is_dir() or stat.S_IMODE(root.stat().st_mode)!=0o700:sys.exit(32)
s=os.statvfs(str(h));print(s.f_bavail*s.f_frsize)
'''
class Hold(Exception):pass
def need(ok,why):
 if not ok:raise Hold(why)
def pubfp(path):
 parts=path.read_text().strip().split()
 need(len(parts)>=2 and parts[0]=='ssh-ed25519','INVALID_ED25519_PUB')
 raw=base64.b64decode(parts[1],validate=True)
 need(raw[4:15]==b'ssh-ed25519','ED25519_BLOB_INVALID')
 return 'SHA256:'+base64.b64encode(hashlib.sha256(raw).digest()).decode().rstrip('=')
def intel_cmd(code,*args):
 proxy='ssh -o BatchMode=yes -o ConnectTimeout=7 root@hel1 -W 127.0.0.1:22996'
 return ['ssh','-T','-o','BatchMode=yes','-o','ConnectTimeout=8','-o','StrictHostKeyChecking=yes','-o','UserKnownHostsFile='+str(KNOWN),'-o','ProxyCommand='+proxy,'-p','22996','tonyblum@127.0.0.1', 'python3 -c '+shlex.quote(code)+' '+' '.join(shlex.quote(str(a)) for a in args)]
def check(cmd,timeout=35):
 return subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=timeout)
def prepare():
 need(sys.platform=='darwin' and os.geteuid()!=0,'M1_OWNER_HOST_REQUIRED')
 need(AGE.is_file() and os.access(AGE,os.X_OK),'AGE_NOT_AVAILABLE')
 need(KNOWN.is_file() and hashlib.sha256(KNOWN.read_bytes()).hexdigest()==KNOWN_SHA,'INTEL_SSH_KNOWN_HOST_DRIFT')
 need(M1_PUB.is_file() and pubfp(M1_PUB)==M1_FP,'M1_OWNER_RECIPIENT_DRIFT')
 need(INTEL_PUB.is_file() and pubfp(INTEL_PUB)==INTEL_FP,'INTEL_OFFHOST_RECIPIENT_DRIFT')
 r=check(intel_cmd(CAPACITY),timeout=35)
 need(r.returncode==0 and r.stdout.strip().isdigit() and int(r.stdout)>20*(1<<30),'INTEL_DISK_CAPACITY_UNVERIFIED')
 for db in DBS:
  n=check(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=7','root@hel1','/usr/lib/postgresql/16/bin/pg_dump --version'],timeout=15)
  need(n.returncode==0 and b'16.' in n.stdout,'HEL1_PG16_NOT_VERIFIED')
  break
 return int(r.stdout)
def capture(db):
 cap=prepare()
 need(db in DBS,'DATABASE_NOT_ALLOWLISTED')
 source=check(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=7','root@hel1','date -u +%FT%TZ'],timeout=15)
 need(source.returncode==0,'HEL1_CLOCK_UNAVAILABLE')
 start=time.monotonic()
 # All plaintext dump bytes exist only in the anonymous OS pipe.
 pg=subprocess.Popen(['ssh','-T','-o','BatchMode=yes','-o','ConnectTimeout=7','root@hel1',DUMP[db]],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
 need(pg.stdout is not None,'DUMP_PIPE_MISSING')
 age=subprocess.Popen([str(AGE),'-R',str(M1_PUB),'-R',str(INTEL_PUB)],stdin=pg.stdout,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
 pg.stdout.close()
 need(age.stdout is not None,'AGE_PIPE_MISSING')
 receive=subprocess.Popen(intel_cmd(RECV,db),stdin=age.stdout,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
 age.stdout.close()
 print('START_C06_UNQUIESCED_DIRECT_STREAM',db,'no_local_dump',flush=True)
 try:
  rout,rerr=receive.communicate(timeout=1800)
  arc=age.wait(timeout=20)
  prc=pg.wait(timeout=20)
  ageerr=age.stderr.read(4096) if age.stderr else b''
  pgerr=pg.stderr.read(4096) if pg.stderr else b''
 except BaseException:
  for p in (receive,age,pg):
   if p.poll() is None:p.kill()
  raise
 need(receive.returncode==0 and arc==0 and prc==0,'DUMP_AGE_OFFHOST_PIPE_FAILED rc=%s/%s/%s pg=%s age=%s host=%s'%(prc,arc,receive.returncode,pgerr[:80],ageerr[:80],rerr[:80]))
 words=rout.decode('ascii').strip().split()
 need(len(words)==2 and re.fullmatch('[a-f0-9]{64}',words[0]) and words[1].isdigit() and 128<=int(words[1])<=MAX_CIPHER,'REMOTE_STREAM_SHA_MALFORMED')
 digest,length=words
 for phase in ('stage','finalize','readback'):
  rr=check(intel_cmd(VERIFY,db,digest,length,phase),timeout=180)
  need(rr.returncode==0 and ('PASS_REMOTE_CIPHER_'+phase.upper()).encode() in rr.stdout and digest.encode() in rr.stdout,'INTEL_CIPHER_READBACK_OR_FINALIZATION_FAILED_'+phase)
  print('PASS_REMOTE_CIPHER',phase,digest,length,flush=True)
 obj={'schema':'wolo.c06.direct-dual-pub-unquiesced-source-capture.v1','status':'PASS_UNQUIESCED_PRECAPTURE_ONLY','db':db,'capture_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'source_sha256':hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest(),'ciphertext_sha256':digest,'ciphertext_bytes':int(length),'offhost_path':REMOTE_ROOT+'/unfenced-'+db+'.dump.age','owner_m1_recipient_fingerprint':M1_FP,'offhost_filevault_recipient_fingerprint':INTEL_FP,'offhost_ssh_known_hosts_sha256':KNOWN_SHA,'intel_capacity_preflight':cap,'duration_seconds':round(time.monotonic()-start,2),'production_db_mutated':False,'writer_freeze_proven':False,'cross_db_atomic':False,'journal_boundary_captured':False,'restored':False,'c06_closed':False,'c07_closed':False,'funded_authorized':False}
 BASE.mkdir(mode=0o700,exist_ok=True)
 out=BASE/('c06-direct-unquiesced-'+db+'-receipt-v1.json')
 need(not out.exists(),'C06_LOCAL_RECEIPT_ALREADY_EXISTS')
 fd=os.open(out,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
 with os.fdopen(fd,'wb') as f:
  b=(json.dumps(obj,indent=2,sort_keys=True)+'\n').encode();f.write(b);f.flush();os.fsync(f.fileno())
 print('PASS_OFFHOST_UNQUIESCED_PRECAPTURE_READBACK',db,'RECEIPT_SHA256',hashlib.sha256(b).hexdigest(),flush=True)
def main():
 a=argparse.ArgumentParser(description=__doc__);a.add_argument('--mode',choices=('inspect','capture'),default='inspect');a.add_argument('--db',choices=DBS);v=a.parse_args()
 try:
  cap=prepare()
  if v.mode=='inspect':print('PASS_C06_PUBLIC_ONLY_DIRECT_STREAM_PRECHECK offhost_available_bytes',cap,'NOT_GATE_CLOSED');return 0
  need(v.db in DBS,'DATABASE_SELECTION_REQUIRED')
  capture(v.db);return 0
 except (Hold,OSError,UnicodeError,ValueError,subprocess.TimeoutExpired,subprocess.SubprocessError) as e:
  print('HOLD_C06_DIRECT_STREAM',str(e)[:220],flush=True);return 3
if __name__=='__main__':sys.exit(main())

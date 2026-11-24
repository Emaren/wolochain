#!/usr/bin/env python3
"""Owner-present, exact-byte HD/DE catalog capture only. No SQL admission."""
import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import stat
import subprocess
import sys
import tempfile

ROOT=Path('/home/tony/we1-hd-direct-media-preimage-v3-20261124')
PINS={
    'c03_hd_direct_media_catalog_witness.sql':'d1a0b2158b48da9d10f140fe67dd6fe454c44956d511787e5f26f71c344b59a4',
    'c03_social_writer_catalog_readonly.sql':'a25b85c8f5f1cb95d6e320029d6ff5267cd7fd9fd6180b9c34e777f15f1aa8e7',
}
DBS=('aoe2hd_db','aoe2de_db')
PREFIX=b"BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY; SET LOCAL search_path=pg_catalog,pg_temp; SET LOCAL statement_timeout='5s'; SET LOCAL lock_timeout='350ms';\n"
SUFFIX=b";\nROLLBACK;\n"
class Hold(RuntimeError):pass
def need(ok,why):
    if not ok:raise Hold(why)
def digest(raw):return hashlib.sha256(raw).hexdigest()
def identity(s):return (s.st_dev,s.st_ino,s.st_mode,s.st_uid,s.st_nlink,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
def load_sources(root=ROOT):
    # Retain the actual validated bytes, never reopen either pathname for SQL.
    d=os.open(root,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC)
    try:
        ds=os.fstat(d)
        need(ds.st_uid==os.getuid() and stat.S_IMODE(ds.st_mode)==0o700,'STAGE_OWNER_OR_MODE')
        data={}
        for name,expected in PINS.items():
            fd=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|os.O_CLOEXEC,dir_fd=d)
            try:
                a=os.fstat(fd)
                need(stat.S_ISREG(a.st_mode) and a.st_uid==os.getuid() and a.st_nlink==1 and stat.S_IMODE(a.st_mode)==0o600 and 0<a.st_size<=131072,'SQL_SOURCE_FILE_UNTRUSTED')
                chunks=[];remaining=a.st_size
                while remaining:
                    chunk=os.read(fd,remaining)
                    need(bool(chunk),'SQL_SOURCE_SHORT_READ');chunks.append(chunk);remaining-=len(chunk)
                raw=b''.join(chunks)
                need(not os.read(fd,1) and identity(a)==identity(os.fstat(fd))==identity(os.stat(name,dir_fd=d,follow_symlinks=False)),'SQL_SOURCE_RACE')
                need(digest(raw)==expected,'SQL_SOURCE_HASH_MISMATCH')
                data[name]=raw
            finally:os.close(fd)
        need((ds.st_dev,ds.st_ino)==(os.lstat(root).st_dev,os.lstat(root).st_ino),'STAGE_IDENTITY_DRIFT')
        return data
    finally:os.close(d)
def sql_inputs(data):
    need(set(data)==set(PINS) and all(type(data[k]) is bytes and digest(data[k])==v for k,v in PINS.items()),'VALIDATED_SQL_BYTES_REQUIRED')
    return (PREFIX+data['c03_hd_direct_media_catalog_witness.sql']+SUFFIX,data['c03_social_writer_catalog_readonly.sql'])
def run_psql(db,raw,out):
    need(db in DBS,'DATABASE_SCOPE')
    argv=['/usr/bin/sudo','-n','-u','postgres','/usr/bin/psql','-X','-w','-qAt','-v','ON_ERROR_STOP=1','-h','/var/run/postgresql','-p','5432','-U','postgres','-d',db]
    # Do not carry libpq connection overrides or use startup files.
    env={'PATH':'/usr/bin:/bin','LANG':'C','HOME':str(Path.home()),'TERM':os.environ.get('TERM','dumb')}
    fd=os.open(out,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW|os.O_CLOEXEC,0o600)
    with os.fdopen(fd,'wb') as f:
        r=subprocess.run(argv,input=raw,stdout=f,stderr=subprocess.PIPE,env=env,timeout=30)
        f.flush();os.fsync(f.fileno())
        need(r.returncode==0 and 0<os.fstat(f.fileno()).st_size<=4*1024*1024,'READ_ONLY_CAPTURE_FAILED')
def write_once(path,raw):
    fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW|os.O_CLOEXEC,0o600)
    with os.fdopen(fd,'wb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
def capture(out,data,runner=run_psql):
    witness,audit=sql_inputs(data)
    for db in DBS:
        w=out/(db+'.witness.incomplete');a=out/(db+'.private-audit.incomplete')
        runner(db,witness,w)
        x=json.loads(w.read_bytes())
        need(x['database']==db and str(x['pg_version']).startswith('16') and x['enabled_event_triggers']==0 and x['hba_parse_errors']==0,'CATALOG_WITNESS_HOLD')
        w.rename(out/(db+'.witness.json'))
        runner(db,audit,a)
        need(any(line.startswith(b'FINAL_NONAUTHORIZATION|') for line in a.read_bytes().splitlines()),'AUDIT_INCOMPLETE')
        a.rename(out/(db+'.private-audit.txt'))
def main():
    os.umask(0o077)
    need(pwd.getpwuid(os.getuid()).pw_name=='tony' and os.getuid()!=0 and sys.stdin.isatty() and sys.stdout.isatty(),'OWNER_TERMINAL_REQUIRED')
    data=load_sources()
    print('Read-only HD/DE catalogs only. No player rows, DDL, grants, service changes or financial authority.')
    need(input('Type READ-ONLY-HD-DIRECT-MEDIA to authorize catalog capture: ')=='READ-ONLY-HD-DIRECT-MEDIA','OWNER_CONSENT_REQUIRED')
    # Only the real owner terminal authenticates. No credential is captured.
    subprocess.run(['/usr/bin/sudo','-v'],check=True,timeout=120)
    out=Path(tempfile.mkdtemp(prefix='capture-',dir=ROOT))
    capture(out,data)
    host=Path('/etc/machine-id').read_bytes().strip()
    need(re.fullmatch(b'[0-9a-f]{32}',host),'MACHINE_ID_INVALID')
    write_once(out/'host-id.sha256',(digest(host)+'\n').encode())
    h=subprocess.run(['/usr/bin/sudo','-n','-u','postgres','/usr/bin/sha256sum','/etc/postgresql/16/main/pg_hba.conf'],check=True,capture_output=True,timeout=10).stdout.split()[0]
    need(re.fullmatch(b'[0-9a-f]{64}',h),'HBA_HASH_INVALID')
    write_once(out/'hba.sha256',h+b'\n')
    # Private manifest includes the exact validated input pins, not later path reads.
    write_once(out/'source-pins.json',json.dumps({k:digest(v) for k,v in data.items()},sort_keys=True).encode()+b'\n')
    rows=[digest(p.read_bytes())+'  '+p.name for p in sorted(out.iterdir())]
    write_once(out/'capture-manifest.sha256',('\n'.join(rows)+'\n').encode())
    fd=os.open(out,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:os.fsync(fd)
    finally:os.close(fd)
    print('READ_ONLY_CAPTURE_COMPLETE_NOT_ADMISSION='+str(out))
    for db in DBS:print((out/(db+'.witness.json')).read_text().strip())
if __name__=='__main__':
    try:main()
    except (Hold,OSError,ValueError,KeyError,subprocess.SubprocessError) as e:
        print('HOLD_READ_ONLY_CAPTURE: '+str(e)[:120],file=sys.stderr);sys.exit(3)

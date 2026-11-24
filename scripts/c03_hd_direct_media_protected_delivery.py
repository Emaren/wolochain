#!/usr/bin/env python3
"""Fixed WE2 native admission candidate for #260, not a sudo grant.

Only invoke from an independently admitted protected root entrypoint.
This helper never installs itself, executes media SQL, or changes roles,
HBA, services, financial producers or credentials. All failures hold.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import stat
import subprocess
import sys
import types
from urllib.parse import urlsplit, unquote_to_bytes

STAGE = Path('/home/tony/we1-media-root-review-b9a8579')
ROOT = Path('/etc/aoe2war-chat-media-hd-v1')
CODE = Path('/usr/local/libexec/aoe2war-chat-media-hd-v1')
STATE = Path('/var/lib/aoe2war-chat-media-hd-v1')
APP = Path('/var/www/AoE2HDBets/app-prodn')
UNIT = 'aoe2-wolo-transfer-heartbeat.service'
UNIT_PATH = Path('/etc/systemd/system') / UNIT
WRAPPER = Path('/usr/local/sbin/aoe2-wolo-transfer-heartbeat.sh')
EXECUTOR = 'c03_hd_direct_media_native_executor.py'
PUBLIC = 'owner-p256-public-x963.bin'
CANDIDATE = 'review.CANDIDATE-NOT-ADMITTED.json'
SQL_SOURCE = '3e4c50452541805742f31bd743117b0863582f60'
PACKAGE = {
    EXECUTOR: 'f91685bbc1976ce679196221a5ad8d907907e03197413eaa5e4140bdfa86a39d',
    'c03_hd_direct_image_install_candidate.sql': 'db4c80451f9bb627598105b826c45d9ee115fd462a56d08aebf5deb79ad0723c',
    'c03_hd_direct_image_inverse_candidate.sql': '2298690e5c1c412cdd73d232c9469ee7e268c191fbaa0816e9f6340fde138baf',
    'c03_hd_direct_media_catalog_witness.sql': 'd1a0b2158b48da9d10f140fe67dd6fe454c44956d511787e5f26f71c344b59a4',
    PUBLIC: 'dfd1b967fa1fbe6daf62a09143a880c8753a94d756a6fbfea0d32c8e5ee980c2',
    CANDIDATE: '4b49653c4b5261960027f91c0175111b082024972f3cec26d0946deaac7b6458',
}
SOURCE_PINS = {
    UNIT_PATH: '56e1fe523209a4f3bad72a494f7e448a1be29b4264c08b216b8ed30c032812cd',
    WRAPPER: '0e53ced04d3bc725df6eafec6cf987043da42057e91432e382dfc3f51d11f190',
    APP / 'scripts/backfill-wolo-mainnet-transfers.mjs': '968f2f673f5fdfce5b8bbbfcf5bfd298451f4aee069eb372fd98139535648430',
    APP / 'lib/woloMainnetTransfers.ts': '5ee644b6d20499946a5d90f82f1dda8878651b92eb760cfe83e8c720d22b8983',
}
ENV_PATHS = (Path('/etc/aoe2hdbets/aoe2hdbets-web.env'), APP / '.env', APP / '.env.local')
ROLES = {'postgres', 'aoe2hd_user', 'aoe2war_web_prod', 'aoe2war_social_writer', 'aoe2de_user'}
DBS = {'aoe2hd_db', 'aoe2de_db'}
HEX = re.compile(r'[0-9a-f]{64}\Z')
BASE_ENV = {'PATH': '/usr/bin:/bin', 'LANG': 'C', 'HOME': '/nonexistent'}
class Hold(RuntimeError):
    pass

def need(ok, reason):
    if not ok:
        raise Hold(reason)

def sha(data):
    return hashlib.sha256(data).hexdigest()

def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode()

def open_dir(path, owners=(0,)):
    need(path.is_absolute(), 'ABSOLUTE_DIRECTORY_REQUIRED')
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        for part in path.parts[1:]:
            need(part not in ('.', '..'), 'DIRECTORY_COMPONENT')
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=fd)
            os.close(fd)
            fd = child
            s = os.fstat(fd)
            need(s.st_uid in owners and not s.st_mode & 0o022, 'UNSAFE_DIRECTORY')
        return fd
    except BaseException:
        os.close(fd)
        raise

def read_at(fd, name, owners, limit=262144, mode=None, optional=False):
    try:
        f = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=fd)
    except FileNotFoundError:
        if optional:
            return None
        raise Hold('REQUIRED_FILE_ABSENT')
    try:
        a = os.fstat(f)
        need(stat.S_ISREG(a.st_mode) and a.st_uid in owners and a.st_nlink == 1
             and not a.st_mode & 0o022 and 0 < a.st_size <= limit, 'UNSAFE_FILE')
        if mode is not None:
            need(stat.S_IMODE(a.st_mode) == mode, 'FILE_MODE_DRIFT')
        raw = bytearray()
        while len(raw) < a.st_size:
            part = os.read(f, a.st_size - len(raw))
            need(part, 'SHORT_READ')
            raw.extend(part)
        b = os.fstat(f)
        need((a.st_dev,a.st_ino,a.st_size,a.st_mtime_ns,a.st_ctime_ns)
             == (b.st_dev,b.st_ino,b.st_size,b.st_mtime_ns,b.st_ctime_ns), 'FILE_RACE')
        return bytes(raw)
    finally:
        os.close(f)

def read_fixed(path, owners=(0,), limit=262144, mode=None, optional=False):
    fd = open_dir(path.parent, owners=(0,1000))
    try:
        return read_at(fd,path.name,owners,limit,mode,optional)
    finally:
        os.close(fd)

def stage_read(names):
    fd = open_dir(STAGE, owners=(0,1000))
    try:
        s = os.fstat(fd)
        need(s.st_uid == 1000 and stat.S_IMODE(s.st_mode) == 0o700, 'STAGE_DIR_DRIFT')
        return {n:read_at(fd,n,(1000,),mode=0o600) for n in names}
    finally:
        os.close(fd)

def new_dir(path):
    fd = open_dir(path.parent)
    try:
        os.mkdir(path.name, 0o700, dir_fd=fd)
        os.fsync(fd)
    finally:
        os.close(fd)

def write_once(path, data):
    d = open_dir(path.parent)
    try:
        fd = os.open(path.name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC,0o600,dir_fd=d)
        with os.fdopen(fd,'wb') as f:
            f.write(data); f.flush(); os.fsync(f.fileno())
        os.fsync(d)
        need(read_at(d,path.name,(0,),mode=0o600)==data,'ROOT_POSTIMAGE_DRIFT')
    finally:
        os.close(d)

def review_pins(data):
    need(set(data)==set(PACKAGE) and all(sha(data[n])==h for n,h in PACKAGE.items()), 'PACKAGE_PIN_DRIFT')
    q = json.loads(data[CANDIDATE])
    need(canonical(q)==data[CANDIDATE].strip(), 'REVIEW_NOT_CANONICAL')
    need(set(q)=={'schema','source_commit','executor_sha256','file_sha256','host_id_sha256','hba_sha256','owner_public_sha256'}, 'REVIEW_FIELDS')
    need(q['schema']=='wolo.we1.hd-direct-media-root-review.v1' and q['source_commit']==SQL_SOURCE
         and q['executor_sha256']==PACKAGE[EXECUTOR] and q['owner_public_sha256']==PACKAGE[PUBLIC]
         and q['file_sha256']=={'install':PACKAGE['c03_hd_direct_image_install_candidate.sql'],
                                'inverse':PACKAGE['c03_hd_direct_image_inverse_candidate.sql'],
                                'witness':PACKAGE['c03_hd_direct_media_catalog_witness.sql']}, 'REVIEW_PIN_DRIFT')
    pub = data[PUBLIC]
    need(len(pub)==65 and pub[0]==4,'PUBLIC_KEY_SHAPE')
    host = read_fixed(Path('/etc/machine-id'),limit=256).strip()
    hba = read_fixed(Path('/etc/postgresql/16/main/pg_hba.conf'),owners=(pwd.getpwnam('postgres').pw_uid,),limit=65535)
    need(re.fullmatch(b'[0-9a-f]{32}',host) and sha(host)==q['host_id_sha256'] and sha(hba)==q['hba_sha256'], 'NATIVE_PIN_DRIFT')
    return q

def deliver_trust():
    # Root-delivery only; no SQL, service changes, signer operation or maintenance clock.
    data = stage_read(PACKAGE)
    review_pins(data)
    for target in (ROOT,CODE,STATE):
        need(not os.path.lexists(target),'ROOT_TARGET_EXISTS_HOLD')
    # Any interrupted partial delivery is an explicit HOLD, never overwritten.
    for target in (STATE,ROOT,CODE):
        new_dir(target)
    for n in PACKAGE:
        if n.endswith(('.py','.sql')):
            write_once(CODE/n,data[n])
    write_once(ROOT/PUBLIC,data[PUBLIC])
    write_once(ROOT/'review.json',data[CANDIDATE])
    receipt={'status':'ROOT_TRUST_DELIVERED_NO_SQL','sql_source':SQL_SOURCE,
             'package_sha256':PACKAGE,'financial_authorized':False}
    write_once(ROOT/'root-trust-delivery-receipt.json',canonical(receipt)+b'\n')
    return {'status':receipt['status'],'receipt_sha256':sha(canonical(receipt)+b'\n')}

def selected_url(blobs):
    # Exact reviewed shell precedence: grep -hE ^DATABASE_URL=, tail -1,
    # cut at first '=', strip one double quote from either edge, normalize scheme.
    hits=[]
    for b in blobs:
        if b is None:
            continue
        need(b'\x00' not in b,'ENV_BINARY_HOLD')
        hits.extend(line[len(b'DATABASE_URL='):] for line in b.split(b'\n') if line.startswith(b'DATABASE_URL='))
    need(hits,'NO_CONFIGURED_DSN')
    v=hits[-1]
    if v.startswith(b'"'): v=v[1:]
    if v.endswith(b'"'): v=v[:-1]
    return v.replace(b'postgresql+asyncpg:',b'postgresql:',1)

def decode_component(v):
    need(v is not None and not re.search(r'%(?![0-9A-Fa-f]{2})',v),'URI_ENCODING_HOLD')
    out=unquote_to_bytes(v).decode('utf-8','strict')
    need(out and not any(ord(c)<32 or ord(c)==127 for c in out),'URI_COMPONENT_HOLD')
    return out

def connection_fields(raw):
    # Intentionally refuse ambiguous/nonlocal/node-pg option cases instead of
    # pretending libpq is equivalent. No URL/credential is returned to stdout.
    need(all(33<=c<=126 for c in raw),'URI_ASCII_HOLD')
    u=urlsplit(raw.decode('ascii'))
    need(u.scheme in ('postgresql','postgres') and u.hostname=='127.0.0.1'
         and u.port==5432 and not u.fragment and u.path.count('/')==1
         and u.query in ('','schema=public','sslmode=disable','schema=public&sslmode=disable','sslmode=disable&schema=public'),
         'URI_SCOPE_OR_OPTIONS_HOLD')
    role,db=decode_component(u.username),decode_component(u.path[1:])
    need(role in ROLES and db in DBS,'UNRECOGNIZED_ROLE_OR_DB')
    password=decode_component(u.password)
    return role,db,password

def verify_heartbeat_source():
    for p,digest in SOURCE_PINS.items():
        need(sha(read_fixed(p,owners=(0,1000),limit=1048576))==digest,'HEARTBEAT_SOURCE_DRIFT')
    keys=('FragmentPath','DropInPaths','NeedDaemonReload','User','Group','WorkingDirectory','RootDirectory','RootImage','DynamicUser','PrivateUsers','ProtectHome','SupplementaryGroups')
    r=subprocess.run(['/usr/bin/systemctl','show',UNIT,*['--property='+k for k in keys]],
                     env=BASE_ENV,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=5,check=False)
    need(r.returncode==0,'UNIT_QUERY_HOLD')
    actual=dict(line.split('=',1) for line in r.stdout.decode('utf-8').splitlines())
    expected={'FragmentPath':str(UNIT_PATH),'DropInPaths':'','NeedDaemonReload':'no',
              'User':'','Group':'','WorkingDirectory':str(APP),'RootDirectory':'','RootImage':'',
              'DynamicUser':'no','PrivateUsers':'no','ProtectHome':'no','SupplementaryGroups':''}
    need(actual==expected,'LOADED_UNIT_DRIFT')

ROLE_QUERY = """BEGIN READ ONLY;
SELECT current_user,session_user,current_database(),
CASE WHEN EXISTS (
 SELECT 1 FROM pg_roles r WHERE (rolsuper OR rolcreaterole OR rolcreatedb OR rolreplication OR rolbypassrls)
 AND pg_has_role(r.oid,'MEMBER'))
 OR EXISTS (SELECT 1 FROM pg_database d WHERE d.datname=current_database() AND pg_has_role(d.datdba,'MEMBER'))
 OR EXISTS (SELECT 1 FROM pg_namespace n WHERE n.nspname='public' AND
 (pg_has_role(n.nspowner,'MEMBER') OR has_schema_privilege(n.oid,'CREATE')))
 OR EXISTS (SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
 WHERE n.nspname='public' AND pg_has_role(c.relowner,'MEMBER'))
 OR has_database_privilege(current_database(),'CREATE')
 THEN 'owner_capable' ELSE 'not_observed' END;
ROLLBACK;
"""

def attest_role():
    verify_heartbeat_source()
    blobs=[read_fixed(p,owners=(0,) if i==0 else (0,1000),mode=0o600,optional=(i!=0))
           for i,p in enumerate(ENV_PATHS)]
    role,db,password=connection_fields(selected_url(blobs))
    env={**BASE_ENV,'PGPASSWORD':password,'PGPASSFILE':'/dev/null','PGCONNECT_TIMEOUT':'3',
         'PGSSLMODE':'disable','PGOPTIONS':'-c default_transaction_read_only=on -c statement_timeout=3000 -c lock_timeout=350'}
    r=subprocess.run(['/usr/bin/psql','-X','-qAt','-w','-v','ON_ERROR_STOP=1','-h','127.0.0.1','-p','5432','-U',role,'-d',db],
                     input=ROLE_QUERY.encode(),env=env,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=7,check=False)
    # Recheck the exact config bytes and source after the bounded query; no secret digest output.
    verify_heartbeat_source()
    need(blobs==[read_fixed(p,owners=(0,) if i==0 else (0,1000),mode=0o600,optional=(i!=0))
                  for i,p in enumerate(ENV_PATHS)],'CONFIG_DRIFT')
    need(r.returncode==0 and len(r.stdout)<=256,'ROLE_AUTHENTICATION_HOLD')
    fields=r.stdout.decode('ascii').strip().split('|')
    need(len(fields)==4 and fields[:3]==[role,role,db] and fields[3] in ('owner_capable','not_observed'),'ROLE_RESULT_HOLD')
    # This is a new read-only authentication of the pinned configured role,
    # not an observation of the heartbeat backend or comprehensive exclusion.
    return {'status':'HOLD_HEARTBEAT_OWNER_CAPABLE' if fields[3]=='owner_capable' else 'ROLE_AUTHENTICATED_NOT_MAINTENANCE_ADMISSION',
            'role':role,'database':db,'catalog_owner_capability':fields[3],
            'live_heartbeat_backend_observed':False,'maintenance_admitted':False,'financial_authorized':False}

def deliver_permit(nonce):
    need(HEX.fullmatch(nonce) and nonce!='0'*64,'NONCE_INVALID')
    name='permit-'+nonce+'.json'
    data=stage_read([name])[name]
    code=read_fixed(CODE/EXECUTOR,mode=0o600)
    need(sha(code)==PACKAGE[EXECUTOR],'ROOT_EXECUTOR_DRIFT')
    module=types.ModuleType('fixed_media_executor')
    module.__file__=str(CODE/EXECUTOR)
    exec(compile(code,module.__file__,'exec'),module.__dict__)
    _,pub,review=module.live_pins()
    lock=os.open(STATE/'controller.lock',os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW|os.O_CLOEXEC,0o600)
    try:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        phase,_=module.phase_state()
        need(phase=='install' and not list(ROOT.glob('permit-*.json')),'PERMIT_ALREADY_PRESENT_OR_PHASE_HOLD')
        module.verify_packet(data,pub,review,'install',nonce,datetime.now(timezone.utc))
        write_once(ROOT/name,data)
        return {'status':'SIGNED_INSTALL_PERMIT_DELIVERED_NO_SQL','nonce':nonce,'permit_sha256':sha(data)}
    finally:
        os.close(lock)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('attest-role','deliver-trust','deliver-install-permit'))
    parser.add_argument('nonce',nargs='?',default='')
    args=parser.parse_args()
    try:
        need(os.getuid()==os.geteuid()==0,'PROTECTED_ROOT_ENTRYPOINT_REQUIRED')
        os.umask(0o077)
        need((args.action=='deliver-install-permit')==bool(args.nonce),'ARGUMENT_SCOPE')
        if args.action=='attest-role': out=attest_role()
        elif args.action=='deliver-trust': out=deliver_trust()
        else: out=deliver_permit(args.nonce)
        print(json.dumps(out,sort_keys=True))
        return 3 if out['status'].startswith('HOLD') else 0
    except Hold as e:
        print(json.dumps({'status':'HOLD','reason':str(e),'financial_authorized':False}))
        return 3
    except Exception:
        # Exceptions can include connection details: never print raw exception.
        print(json.dumps({'status':'HOLD','reason':'NATIVE_OR_PARSE_FAILURE','financial_authorized':False}))
        return 3

if __name__=='__main__':
    sys.exit(main())

#!/usr/bin/env python3
"""WE1 root-installed, one-purpose Chat Social V2 HD SQL executor. NO finance admission.

Never use untrusted user paths. Root installation, separate purpose-key enrollment
and a fresh signed one-use packet are required. This source does not install itself.
"""
from __future__ import annotations
import argparse
import base64
import binascii
from datetime import datetime, timezone, timedelta
import fcntl
import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import signal
import stat
import subprocess
import sys
import tempfile

ACTION = 'CHAT_SOCIAL_HD_V2_SQL_ONLY'
DOMAIN = b'AOE2WAR-WE1-CHAT-SOCIAL-HD-V2-SQL-ONLY-V1\x00'
SOURCE = '5cf4f223a7b187f6596b6a9caac26aec7afd6e94'
SCHEMA = 'wolo.we1.chat-social-hd-v2-exact-request.v1'
PACKET_SCHEMA = 'wolo.we1.chat-social-hd-v2-signed-packet.v1'
FILES = {
    'install': ('c03_hd_gateway_v2_restricted_install_candidate.sql','9793ff39ca80d646a89041f0174f42bb717ae3e649e49f8d68d6f102792f5c51'),
    'inverse': ('c03_hd_gateway_v2_restricted_inverse_candidate.sql','84114bac7b3e15f4cadaf3a566f705440eeb9cf8ba63f3be97249652d5f25449'),
    'pre': ('c03_chat_social_v2_preimage_readonly.sql','8f0e0f92859b5b0b01fde7552d95263409a1874c672665021a4ea3b5235a7da6'),
    'post': ('c03_chat_social_v2_postimage_readonly.sql','e14eb681cfd097209d05afff5d3ec34df29581643c2c6f5e2cb7918d2adbae6a'),
    'acl': ('c03_chat_social_v2_acl_witness_readonly.sql','d0829593727b8b156ac07f5fc9a8d4477dd5f8e24696ffa2703fa7a802f07faa'),
}
HBA = Path('/etc/postgresql/16/main/pg_hba.conf')
HBA_SHA256 = '3fecbffb683bf2bc21e8bd880b9be982d14cbe3bbf67aae08f801159d6b76789'
ROOT = Path('/etc/wolo-financial-chat-social-v2')
SQL = Path('/usr/local/libexec/wolo-financial-chat-social-v2/sql')
STATE = Path('/var/lib/wolo-financial-role-state/v1/chat-social-hd-v2-exact')
PUBLIC = ROOT / 'owner-chat-social-p256-public-x963.bin'
PERMIT = ROOT / 'signed-one-use-chat-social-v2-permit.json'
SPKI = bytes.fromhex('3059301306072a8648ce3d020106082a8648ce3d030107034200')
HEX64 = re.compile(r'[0-9a-f]{64}\Z')
KEYS = {'schema','action','phase','host','database','source_commit',
        'file_sha256','owner_public_sha256','nonce','not_before','expires_at',
        'financial_authorized','funding_authorized','hba_mutation_authorized',
        'de_database_authorized','raw_event_grants_authorized','hba_sha256'}

class Hold(RuntimeError): pass

def need(condition, why):
    if not condition: raise Hold(why)

def digest(b:bytes)->str: return hashlib.sha256(b).hexdigest()

def canonical(obj)->bytes: return json.dumps(obj, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode()

def strict_json(raw):
    def pairs(xs):
        d={}
        for k,v in xs:
            need(k not in d, 'DUPLICATE_JSON_KEY');d[k]=v
        return d
    value=json.loads(raw,object_pairs_hook=pairs,parse_constant=lambda _:(_ for _ in ()).throw(Hold('NONFINITE_JSON')))
    need(canonical(value)==raw.strip(), 'NONCANONICAL_JSON')
    return value

def utc(v):
    need(type(v) is str and re.fullmatch(r'\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ',v) is not None,'INVALID_UTC')
    try:return datetime.strptime(v,'%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc)
    except ValueError:raise Hold('INVALID_UTC')

def verify_scope(req, public_sha, now, phase):
    need(type(req) is dict and set(req)==KEYS,'REQUEST_SCHEMA_FIELDS')
    need(req['schema']==SCHEMA and req['action']==ACTION and req['phase']==phase,'WRONG_ACTION_OR_PHASE')
    need(req['host']=='HEL1' and req['database']=='aoe2hd_db' and req['source_commit']==SOURCE,'WRONG_TARGET_OR_SOURCE')
    need(type(req['file_sha256']) is dict and req['file_sha256']=={k:s for k,(_,s) in FILES.items()},'SQL_SOURCE_CHANGED')
    need(req['hba_sha256']==HBA_SHA256,'WRONG_HBA_IDENTITY')
    need(type(req['owner_public_sha256']) is str and req['owner_public_sha256']==public_sha,'UNENROLLED_OWNER_KEY')
    need(type(req['nonce']) is str and HEX64.fullmatch(req['nonce']) and req['nonce']!='0'*64,'INVALID_NONCE')
    for flag in ('financial_authorized','funding_authorized','hba_mutation_authorized',
                 'de_database_authorized','raw_event_grants_authorized'):
        need(req[flag] is False, 'FORBIDDEN_AUTHORITY_'+flag)
    begin,end=utc(req['not_before']),utc(req['expires_at'])
    need(timedelta(0)<end-begin<=timedelta(seconds=900) and begin<=now<end,'EXPIRED_OR_OVERSIZED_PERMIT')
    return req

def verify_signed_packet(raw, public, now, phase, verifier=None):
    packet=strict_json(raw)
    need(type(packet) is dict and set(packet)=={'schema','request','signature_der_b64'} and packet['schema']==PACKET_SCHEMA,'INVALID_PACKET')
    need(type(public) is bytes and len(public)==65 and public[0]==4,'INVALID_ENROLLED_P256_KEY')
    req=verify_scope(packet['request'],digest(public),now,phase)
    need(type(packet['signature_der_b64']) is str and len(packet['signature_der_b64'])<=112,'INVALID_SIGNATURE')
    try:sig=base64.b64decode(packet['signature_der_b64'],validate=True)
    except (binascii.Error,ValueError):raise Hold('INVALID_SIGNATURE_ENCODING')
    need(64<=len(sig)<=80 and sig[0]==0x30,'INVALID_SIGNATURE_DER')
    message=DOMAIN+canonical(req)
    if verifier is not None:need(verifier(message,sig,public),'OWNER_SIGNATURE_INVALID')
    else:
        with tempfile.TemporaryDirectory(prefix='we1-chat-social-p256-verify-') as t:
            d=Path(t)
            for name,content in [('public.der',SPKI+public),('message',message),('signature.der',sig)]:
                p=d/name;p.write_bytes(content);p.chmod(0o600)
            cp=subprocess.run(['/usr/bin/openssl','dgst','-sha256','-keyform','DER','-verify',str(d/'public.der'),'-signature',str(d/'signature.der'),str(d/'message')],
                              capture_output=True,timeout=8)
            need(cp.returncode==0 and b'Verified OK' in cp.stdout,'OWNER_SIGNATURE_INVALID')
    return req

def secure_dir(path, mode=None):
    s=path.lstat();need(stat.S_ISDIR(s.st_mode) and s.st_uid==0 and not stat.S_ISLNK(s.st_mode) and not (s.st_mode&0o022),'DIRECTORY_NOT_ROOT_IMMUTABLE')
    if mode is not None:need(stat.S_IMODE(s.st_mode)==mode,'DIRECTORY_MODE_DRIFT')

def secure_file(path, limit=32768):
    for parent in reversed(path.parent.parents):
        if parent == Path('/'): continue
        if parent in (Path('/proc'),Path('/sys')):continue
        secure_dir(parent)
    secure_dir(path.parent)
    s=path.lstat()
    need(stat.S_ISREG(s.st_mode) and s.st_uid==0 and s.st_nlink==1 and not (s.st_mode&0o077) and 0<s.st_size<=limit,'SOURCE_FILE_UNTRUSTED')
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
    try:
        current=os.fstat(fd)
        need(current.st_dev==s.st_dev and current.st_ino==s.st_ino and current.st_size==s.st_size,'SOURCE_FILE_RACE')
        data=os.read(fd,limit+1)
        need(len(data)==s.st_size,'SOURCE_READ_MISMATCH')
        return data
    finally:os.close(fd)

def verify_hba():
    s=HBA.lstat()
    need(stat.S_ISREG(s.st_mode) and s.st_uid==pwd.getpwnam('postgres').pw_uid
         and not (s.st_mode & 0o007) and s.st_nlink==1 and s.st_size<65536,'HBA_FILE_MODE_OR_OWNER')
    fd=os.open(HBA,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
    try:
        cur=os.fstat(fd)
        need((cur.st_dev,cur.st_ino,cur.st_size)==(s.st_dev,s.st_ino,s.st_size),'HBA_FILE_RACE')
        content=os.read(fd,65537)
        need(len(content)==s.st_size and digest(content)==HBA_SHA256,'CHAT_HBA_SOURCE_DRIFT')
        lines=[x.strip().split() for x in content.decode('ascii').splitlines()
               if x.strip() and not x.lstrip().startswith('#')]
        rules=[
          ['local','all','aoe2war_social_writer','reject'],
          ['host','aoe2hd_db','aoe2war_social_writer','127.0.0.1/32','scram-sha-256'],
          ['host','all','aoe2war_social_writer','127.0.0.1/32','reject'],
          ['host','all','aoe2war_social_writer','::1/128','reject']]
        for rule in rules:need(rule in lines,'MISSING_CHAT_HBA_ALLOW_OR_DENY')
        idx=[lines.index(x) for x in rules]
        need(idx[0]<next(i for i,x in enumerate(lines) if x[:3]==['local','all','all']) and
             idx[1]<idx[2]<next(i for i,x in enumerate(lines) if x[:4]==['host','all','all','127.0.0.1/32']) and
             idx[3]<next(i for i,x in enumerate(lines) if x[:4]==['host','all','all','::1/128']),
             'CHAT_HBA_FIRST_MATCH_DENIAL')
        return HBA_SHA256
    finally:os.close(fd)

def verify_files():
    secure_dir(ROOT);secure_dir(SQL);secure_dir(STATE)
    loaded={}
    for role,(name,sha) in FILES.items():
        data=secure_file(SQL/name)
        need(digest(data)==sha,'EXACT_SOURCE_HASH_MISMATCH_'+role)
        loaded[role]=data
    return loaded

def write_once(directory, name, raw):
    need(re.fullmatch(r'[A-Za-z0-9_.-]{1,120}',name) is not None,'UNSAFE_RECEIPT_NAME')
    fd=os.open(directory/name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC,0o600)
    try:
        with os.fdopen(fd,'wb',closefd=False) as f:
            f.write(raw);f.flush();os.fsync(fd)
    finally:os.close(fd)
    dfd=os.open(directory,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(dfd)
    finally:os.close(dfd)

def psql(sql,readonly=False):
    account=pwd.getpwnam('postgres')
    def drop():
        os.setgroups([])
        os.setgid(account.pw_gid)
        os.setuid(account.pw_uid)
        os.umask(0o077)
    env={'PATH':'/usr/bin:/bin','HOME':'/var/lib/postgresql','LANG':'C','PGCONNECT_TIMEOUT':'3',
         'PGDATABASE':'aoe2hd_db','PGUSER':'postgres','PGHOST':'/var/run/postgresql','PGPASSFILE':'/dev/null'}
    if readonly:env['PGOPTIONS']='-c default_transaction_read_only=on'
    command=['/usr/bin/psql','-X','-w','-q','-v','ON_ERROR_STOP=1','-h','/var/run/postgresql','-U','postgres','-d','aoe2hd_db']
    proc=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                          env=env,preexec_fn=drop,start_new_session=True)
    try:out,err=proc.communicate(sql,timeout=25)
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid,signal.SIGKILL);proc.communicate();raise Hold('PSQL_PHASE_TIMEOUT')
    need(proc.returncode==0,'POSTGRES_SQL_PHASE_DENIED')
    need(len(out)<32768,'SQL_OUTPUT_TOO_LARGE')
    return digest(out)

def run_transaction(data,phase,runner):
    evidence={}
    try:
        if phase=='install':
            evidence['preimage_stdout_sha256']=runner(data['pre'],readonly=True)
            original=runner(data['acl'],readonly=True)
            evidence['acl_before_sha256']=original
            evidence['install_stdout_sha256']=runner(data['install'])
            try:
                evidence['postimage_stdout_sha256']=runner(data['post'],readonly=True)
                evidence['acl_after_sha256']=runner(data['acl'],readonly=True)
                need(evidence['acl_after_sha256']==original,'LEGACY_RAW_AND_COLUMN_ACL_DRIFT')
                evidence['status']='INSTALLED_POSTIMAGE_PASS'
            except Exception:
                evidence['status']='POSTIMAGE_HOLD_INVERSE_ATTEMPT'
                try:
                    evidence['inverse_stdout_sha256']=runner(data['inverse'])
                    evidence['after_inverse_preimage_stdout_sha256']=runner(data['pre'],readonly=True)
                    evidence['after_inverse_acl_sha256']=runner(data['acl'],readonly=True)
                    need(evidence['after_inverse_acl_sha256']==original,'AUTO_INVERSE_ACL_DRIFT')
                    evidence['status']='AUTO_INVERSE_PASS_AFTER_POSTIMAGE_HOLD'
                except Exception:
                    evidence['status']='CRITICAL_MANUAL_RECOVERY_REQUIRED'
        else:
            evidence['postimage_stdout_sha256']=runner(data['post'],readonly=True)
            original=runner(data['acl'],readonly=True)
            evidence['acl_before_sha256']=original
            evidence['inverse_stdout_sha256']=runner(data['inverse'])
            evidence['after_inverse_preimage_stdout_sha256']=runner(data['pre'],readonly=True)
            evidence['acl_after_sha256']=runner(data['acl'],readonly=True)
            need(evidence['acl_after_sha256']==original,'INVERSE_LEGACY_ACL_DRIFT')
            evidence['status']='INVERSE_PREIMAGE_PASS'
    except Exception:
        evidence['status']='CRITICAL_PHASE_UNCERTAIN_NO_RETRY'
    return evidence

def execute(phase):
    need(os.geteuid()==0 and os.getuid()==0,'ROOT_EXECUTOR_REQUIRED')
    need(phase in ('install','inverse'),'UNSUPPORTED_PHASE')
    for ancestor in (Path('/etc'),Path('/usr'),Path('/usr/local'),Path('/usr/local/libexec'),Path('/usr/local/libexec/wolo-financial-chat-social-v2'),Path('/var'),Path('/var/lib'),Path('/var/lib/wolo-financial-role-state'),Path('/var/lib/wolo-financial-role-state/v1')):secure_dir(ancestor)
    hba=verify_hba()
    code=secure_file(Path(__file__).resolve(),limit=32768)
    data=verify_files()
    public=secure_file(PUBLIC,limit=128)
    permit=secure_file(PERMIT,limit=8192)
    now=datetime.now(timezone.utc)
    req=verify_signed_packet(permit,public,now,phase)
    nonce=req['nonce'];lockp=STATE/'controller.lock'
    lock=os.open(lockp,os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
    try:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        write_once(STATE,'nonce-'+nonce+'.consumed',canonical({'nonce':nonce,'phase':phase,'permit_sha256':digest(permit),'status':'CONSUMED_BEFORE_SQL'})+b'\n')
        receipt={'schema':'wolo.we1.chat-social-hd-v2-root-execution-receipt.v1','nonce':nonce,
                 'phase':phase,'permit_sha256':digest(permit),'source_commit':SOURCE,
                 'db':'aoe2hd_db','owner_public_sha256':digest(public),'financial_authorized':False,
                 'hba_sha256':hba,'executor_sha256':digest(code),
                 'time':now.strftime('%Y-%m-%dT%H:%M:%SZ'),'status':'UNKNOWN_AFTER_NONCE_CONSUMPTION'}
        receipt.update(run_transaction(data,phase,psql))
        if receipt['status']=='INSTALLED_POSTIMAGE_PASS':
            try:verify_hba()
            except Exception:receipt['status']='CRITICAL_HBA_CHANGED_POST_SQL_NO_RETRY'
        raw=canonical(receipt)+b'\n'
        write_once(STATE,'receipt-'+nonce+'.json',raw)
        need(receipt['status'] in ('INSTALLED_POSTIMAGE_PASS','INVERSE_PREIMAGE_PASS'),receipt['status'])
        return {'status':receipt['status'],'receipt_sha256':digest(raw),'nonce':nonce}
    finally:
        os.close(lock)

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('phase',choices=('install','inverse'))
    a=p.parse_args(argv)
    try:
        print(json.dumps(execute(a.phase),sort_keys=True));return 0
    except (Hold,OSError,ValueError,subprocess.SubprocessError) as exc:
        print(json.dumps({'status':'HOLD_CHAT_SOCIAL_HD_V2_EXACT_EXECUTOR','reason':str(exc)[:110],
                          'financial_authorized':False},sort_keys=True));return 3

if __name__=='__main__':sys.exit(main())

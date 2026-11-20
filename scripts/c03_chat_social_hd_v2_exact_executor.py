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
    'post': ('c03_chat_social_v2_postimage_readonly.sql','e2509411bff373116f936dd378b8eea9dd1fa2e5da766711babce9a5bd5d8360'),
    'acl': ('c03_chat_social_v2_acl_witness_readonly.sql','d0829593727b8b156ac07f5fc9a8d4477dd5f8e24696ffa2703fa7a802f07faa'),
}
HBA = Path('/etc/postgresql/16/main/pg_hba.conf')
HBA_SHA256 = '3fecbffb683bf2bc21e8bd880b9be982d14cbe3bbf67aae08f801159d6b76789'
ROOT = Path('/etc/wolo-financial-chat-social-v2')
SQL = Path('/usr/local/libexec/wolo-financial-chat-social-v2/recovery-v1/sql')
STATE = Path('/var/lib/wolo-financial-role-state/v1/chat-social-hd-v2-exact')
PUBLIC = ROOT / 'owner-chat-social-p256-public-x963.bin'
PERMIT_PREFIX = 'signed-one-use-chat-social-v2'
SPKI = bytes.fromhex('3059301306072a8648ce3d020106082a8648ce3d030107034200')
HEX64 = re.compile(r'[0-9a-f]{64}\Z')
KEYS = {'schema','action','phase','host','database','source_commit',
        'file_sha256','owner_public_sha256','nonce','not_before','expires_at',
        'financial_authorized','funding_authorized','hba_mutation_authorized',
        'de_database_authorized','raw_event_grants_authorized','hba_sha256'}

class Hold(RuntimeError): pass

def need(condition, why):
    if not condition: raise Hold(why)

def permit_path(phase, nonce):
    need(phase in ('install','inverse') and type(nonce) is str
         and HEX64.fullmatch(nonce) and nonce != '0'*64,'INVALID_PHASE_OR_NONCE')
    return ROOT / f'{PERMIT_PREFIX}-{phase}-{nonce}.json'

def next_transition(state, reader=None):
    """Strict append-only SQL and signed auto-inverse recovery sequence.

    Successful install/inverse alternates normally. A failed install can be
    followed ONLY by a separately signed recovery certificate after the exact
    restored live preimage is independently witnessed. No failed/partial SQL
    receipt is ever amended, ignored, or retried.
    """
    if reader is None: reader=secure_file
    events=[]
    for kind,prefix,pattern in (
        ('sql','transition-',r'transition-(\d{8})-([0-9a-f]{64})\.json'),
        ('recovery','recovery-transition-',r'recovery-transition-(\d{8})-([0-9a-f]{64})\.json')):
        for path in state.glob(prefix+'*'):
            match=re.fullmatch(pattern,path.name)
            need(match is not None,'UNKNOWN_TRANSITION_FILE')
            events.append((int(match.group(1)),match.group(2),kind,path))
    # Unrecognized or partial root recovery evidence always blocks further SQL.
    for item in state.glob('recovery-*'):
        need(re.fullmatch(
            r'recovery-(?:transition-\d{8}-[0-9a-f]{64}\.json|'
            r'nonce-[0-9a-f]{64}\.consumed|receipt-[0-9a-f]{64}\.json)',
            item.name) is not None,'UNKNOWN_RECOVERY_EVIDENCE')
    events.sort()
    need(len({nonce for _,nonce,_,_ in events})==len(events),'REUSED_SQL_OR_RECOVERY_NONCE')
    for kind,nonce_prefix,receipt_prefix in (
        ('sql','nonce-','receipt-'),
        ('recovery','recovery-nonce-','recovery-receipt-')):
        required={nonce for _,nonce,k,_ in events if k==kind}
        for prefix,suffix in ((nonce_prefix,'.consumed'),(receipt_prefix,'.json')):
            found=set()
            for p in state.glob(prefix+'*'):
                match=re.fullmatch(re.escape(prefix)+r'([0-9a-f]{64})'+re.escape(suffix),p.name)
                need(match is not None,'UNKNOWN_SQL_OR_RECOVERY_EVIDENCE')
                found.add(match.group(1))
            need(found==required,'ORPHAN_OR_MISSING_SQL_OR_RECOVERY_EVIDENCE')
    previous='0'*64
    expected='install'
    failed=None
    for seq,(index,nonce,kind,path) in enumerate(events,1):
        need(index==seq,'TRANSITION_SEQUENCE_GAP_OR_DUPLICATE')
        intent=strict_json(reader(path))
        if kind=='sql':
            need(expected in ('install','inverse'),'SIGNED_RECOVERY_REQUIRED')
            phase=expected
            need(type(intent) is dict and intent=={
                'sequence':seq,'nonce':nonce,'phase':phase,
                'previous_receipt_sha256':previous,
                'permit_sha256':intent.get('permit_sha256')},'TRANSITION_RECORD_DRIFT')
            need(type(intent['permit_sha256']) is str and HEX64.fullmatch(intent['permit_sha256']),
                 'TRANSITION_PERMIT_HASH_INVALID')
            consumed=strict_json(reader(state/f'nonce-{nonce}.consumed'))
            need(consumed=={'nonce':nonce,'phase':phase,
                            'permit_sha256':intent['permit_sha256'],
                            'status':'CONSUMED_BEFORE_SQL'},'CONSUMPTION_RECORD_DRIFT')
            raw=reader(state/f'receipt-{nonce}.json')
            receipt=strict_json(raw)
            need(type(receipt) is dict and receipt.get('phase')==phase
                 and receipt.get('nonce')==nonce and receipt.get('sequence')==seq
                 and receipt.get('previous_receipt_sha256')==previous
                 and receipt.get('permit_sha256')==intent['permit_sha256']
                 and receipt.get('source_commit')==SOURCE
                 and receipt.get('db') in (None,'aoe2hd_db')
                 and receipt.get('financial_authorized') in (None,False),
                 'SQL_RECEIPT_IDENTITY_DRIFT')
            status=receipt.get('status')
            successful='INSTALLED_POSTIMAGE_PASS' if phase=='install' else 'INVERSE_PREIMAGE_PASS'
            if status==successful:
                expected='inverse' if phase=='install' else 'install'
                failed=None
            elif phase=='install' and status=='AUTO_INVERSE_PASS_AFTER_POSTIMAGE_HOLD':
                need(receipt.get('acl_before_sha256')==receipt.get('after_inverse_acl_sha256')
                     and type(receipt.get('acl_before_sha256')) is str
                     and HEX64.fullmatch(receipt['acl_before_sha256'])
                     and receipt.get('preimage_stdout_sha256')==receipt.get('after_inverse_preimage_stdout_sha256')
                     and type(receipt.get('preimage_stdout_sha256')) is str
                     and HEX64.fullmatch(receipt['preimage_stdout_sha256'])
                     and receipt.get('hba_sha256')==HBA_SHA256,
                     'AUTO_INVERSE_RESTORATION_UNPROVEN')
                expected='recovery'
                failed=(nonce,seq,digest(raw),receipt['acl_before_sha256'],
                        receipt['preimage_stdout_sha256'])
            else:
                raise Hold('INCOMPLETE_OR_FAILED_SQL_TRANSITION')
        else:
            need(expected=='recovery' and failed is not None,
                 'RECOVERY_WITHOUT_EXACT_AUTO_INVERSE')
            fn,fs,fh,fa,fp=failed
            need(type(intent) is dict and intent=={
                'sequence':seq,'nonce':nonce,'phase':'recovery',
                'previous_receipt_sha256':previous,
                'failed_nonce':fn,'failed_sequence':fs,
                'failed_receipt_sha256':fh,
                'permit_sha256':intent.get('permit_sha256')},'RECOVERY_TRANSITION_RECORD_DRIFT')
            need(type(intent['permit_sha256']) is str
                 and HEX64.fullmatch(intent['permit_sha256']),'RECOVERY_PERMIT_HASH_INVALID')
            signed_recovery=rooted_recovery_permit=reader(
                ROOT/f'signed-one-use-chat-social-auto-inverse-recovery-{nonce}.json')
            need(digest(signed_recovery)==intent['permit_sha256'],
                 'SIGNED_RECOVERY_PERMIT_HASH_DRIFT')
            consumed=strict_json(reader(state/f'recovery-nonce-{nonce}.consumed'))
            need(consumed=={'nonce':nonce,'phase':'recovery',
                            'permit_sha256':intent['permit_sha256'],
                            'status':'CONSUMED_BEFORE_RECOVERY'},'RECOVERY_CONSUMPTION_DRIFT')
            raw=reader(state/f'recovery-receipt-{nonce}.json')
            rec=strict_json(raw)
            need(type(rec) is dict
                 and rec.get('status')=='AUTO_INVERSE_RECOVERY_EPOCH_PASS'
                 and rec.get('phase')=='recovery'
                 and rec.get('nonce')==nonce and rec.get('sequence')==seq
                 and rec.get('previous_receipt_sha256')==previous
                 and rec.get('failed_receipt_sha256')==fh
                 and rec.get('failed_sequence')==fs and rec.get('failed_nonce')==fn
                 and rec.get('permit_sha256')==intent['permit_sha256']
                 and rec.get('live_preimage_stdout_sha256')==fp
                 and rec.get('live_acl_sha256')==fa
                 and rec.get('hba_sha256')==HBA_SHA256
                 and rec.get('financial_authorized') is False
                 and rec.get('funding_authorized') is False
                 and rec.get('de_database_authorized') is False
                 and rec.get('source_commit')==SOURCE
                 and rec.get('new_postimage_sha256')==FILES['post'][1]
                 and rec.get('old_executor_sha256')==
                      'cab4b055e169d6544953611bc08a8132cd917f4a6500b19cd75b5576f99dc1b6'
                 and rec.get('new_executor_sha256')==digest(Path(__file__).read_bytes()),
                 'RECOVERY_RECEIPT_OR_LIVE_PREIMAGE_DRIFT')
            expected='install'
            failed=None
        previous=digest(raw)
    return expected,len(events)+1,previous

def no_pending_permit(root, state, reader=None):
    # All older immutable permit files remain for audit; only consumed ones are past.
    if reader is None:reader=secure_file
    permit_nonces=set()
    for path in root.glob(PERMIT_PREFIX+'-*.json'):
        match=re.fullmatch(re.escape(PERMIT_PREFIX)+r'-(install|inverse)-([0-9a-f]{64})\.json',path.name)
        need(match is not None,'UNKNOWN_PERMIT_FILE')
        phase,nonce=match.groups()
        need(nonce not in permit_nonces,'REUSED_DELIVERY_NONCE')
        permit_nonces.add(nonce)
        record=state/f'nonce-{nonce}.consumed'
        need(record.is_file(),'UNCONSUMED_PERMIT_REQUIRES_REVIEW')
        consumed=strict_json(reader(record))
        need(consumed.get('phase')==phase and consumed.get('nonce')==nonce
             and consumed.get('permit_sha256')==digest(reader(path)),
             'PERMIT_CONSUMPTION_DRIFT')
    for receipt in state.glob('permit-delivery-*.json'):
        match=re.fullmatch(r'permit-delivery-([0-9a-f]{64})\.json',receipt.name)
        need(match is not None and match.group(1) in permit_nonces,
             'ORPHAN_PERMIT_DELIVERY_RECEIPT')

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

def execute(phase, nonce):
    need(os.geteuid()==0 and os.getuid()==0,'ROOT_EXECUTOR_REQUIRED')
    permit_file=permit_path(phase,nonce)
    for ancestor in (Path('/etc'),Path('/usr'),Path('/usr/local'),Path('/usr/local/libexec'),Path('/usr/local/libexec/wolo-financial-chat-social-v2'),Path('/var'),Path('/var/lib'),Path('/var/lib/wolo-financial-role-state'),Path('/var/lib/wolo-financial-role-state/v1')):secure_dir(ancestor)
    hba=verify_hba()
    code=secure_file(Path(__file__).resolve(),limit=32768)
    data=verify_files()
    public=secure_file(PUBLIC,limit=128)
    lockp=STATE/'controller.lock'
    lock=os.open(lockp,os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
    try:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        expected,sequence,previous=next_transition(STATE)
        need(phase==expected,'UNAUTHORIZED_PHASE_ORDER')
        permit=secure_file(permit_file,limit=8192)
        req=verify_signed_packet(permit,public,datetime.now(timezone.utc),phase)
        need(req['nonce']==nonce,'PERMIT_NONCE_FILENAME_MISMATCH')
        recorded=strict_json(secure_file(STATE/f'permit-delivery-{nonce}.json',limit=8192))
        need(recorded.get('nonce')==nonce and recorded.get('phase')==phase
             and recorded.get('permit_sha256')==digest(permit)
             and recorded.get('sequence')==sequence
             and recorded.get('status')=='PASS_SIGNED_CHAT_SOCIAL_PERMIT_ROOT_DELIVERED_NO_SQL',
             'ROOT_PERMIT_DELIVERY_RECEIPT_MISSING_OR_DRIFT')
        write_once(STATE,f'transition-{sequence:08d}-{nonce}.json',
            canonical({'sequence':sequence,'nonce':nonce,'phase':phase,
                       'previous_receipt_sha256':previous,'permit_sha256':digest(permit)})+b'\n')
        write_once(STATE,'nonce-'+nonce+'.consumed',
                   canonical({'nonce':nonce,'phase':phase,'permit_sha256':digest(permit),
                              'status':'CONSUMED_BEFORE_SQL'})+b'\n')
        receipt={'schema':'wolo.we1.chat-social-hd-v2-root-execution-receipt.v1','nonce':nonce,
                 'sequence':sequence,'previous_receipt_sha256':previous,
                 'phase':phase,'permit_sha256':digest(permit),'source_commit':SOURCE,
                 'db':'aoe2hd_db','owner_public_sha256':digest(public),'financial_authorized':False,
                 'hba_sha256':hba,'executor_sha256':digest(code),
                 'time':datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
                 'status':'UNKNOWN_AFTER_NONCE_CONSUMPTION'}
        receipt.update(run_transaction(data,phase,psql))
        if receipt['status'] in ('INSTALLED_POSTIMAGE_PASS','INVERSE_PREIMAGE_PASS'):
            try:verify_hba()
            except Exception:receipt['status']='CRITICAL_HBA_CHANGED_POST_SQL_NO_RETRY'
        raw=canonical(receipt)+b'\n'
        write_once(STATE,'receipt-'+nonce+'.json',raw)
        need(receipt['status'] in ('INSTALLED_POSTIMAGE_PASS','INVERSE_PREIMAGE_PASS'),receipt['status'])
        return {'status':receipt['status'],'receipt_sha256':digest(raw),
                'nonce':nonce,'sequence':sequence}
    finally:
        os.close(lock)

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('phase',choices=('install','inverse'))
    p.add_argument('nonce',nargs='?',default='0'*64,help='fresh signed permit nonce, 64 lowercase hex')
    a=p.parse_args(argv)
    try:
        print(json.dumps(execute(a.phase,a.nonce),sort_keys=True));return 0
    except (Hold,OSError,ValueError,subprocess.SubprocessError) as exc:
        print(json.dumps({'status':'HOLD_CHAT_SOCIAL_HD_V2_EXACT_EXECUTOR','reason':str(exc)[:110],
                          'financial_authorized':False},sort_keys=True));return 3

if __name__=='__main__':sys.exit(main())

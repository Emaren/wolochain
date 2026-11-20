#!/usr/bin/env python3
"""Social-only protected root recovery of one verified automatically inverted SQL.

Independent WE2 admission is required to execute this source. This is NOT a
general-purpose replacement for sudo, financial access, or the original journal.
The old executor, original SQL, original signer enrollment and receipts remain.
"""
from __future__ import annotations
import base64
import binascii
from datetime import datetime, timezone, timedelta
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import pwd
import re
import stat
import sys
import subprocess
import tempfile

STAGE=Path('/home/tony/we1-chat-social-auto-inverse-recovery-stage-20261120')
ROOT=Path('/etc/wolo-financial-chat-social-v2')
LIB=Path('/usr/local/libexec/wolo-financial-chat-social-v2')
OLD_EXEC=LIB/'c03_chat_social_hd_v2_exact_executor.py'
OLD_SQL=LIB/'sql'
NEW=LIB/'recovery-v1'
NEW_EXEC=NEW/'c03_chat_social_hd_v2_exact_executor.py'
NEW_SQL=NEW/'sql'
STATE=Path('/var/lib/wolo-financial-role-state/v1/chat-social-hd-v2-exact')
PUBLIC=ROOT/'owner-chat-social-p256-public-x963.bin'
HBA=Path('/etc/postgresql/16/main/pg_hba.conf')
SOURCE='5cf4f223a7b187f6596b6a9caac26aec7afd6e94'
PUBLIC_SHA='032e9bf17d6b6f71d672d2728aad2c41f6c061893e8dc9cbc2616353a5e10bc3'
HBA_SHA='3fecbffb683bf2bc21e8bd880b9be982d14cbe3bbf67aae08f801159d6b76789'
OLD_EXEC_SHA='cab4b055e169d6544953611bc08a8132cd917f4a6500b19cd75b5576f99dc1b6'
OLD_POST_SHA='e14eb681cfd097209d05afff5d3ec34df29581643c2c6f5e2cb7918d2adbae6a'
NEW_POST_SHA='e2509411bff373116f936dd378b8eea9dd1fa2e5da766711babce9a5bd5d8360'
# Populated by source-pinned reviewer once exact recovery-aware executor settles.
NEW_EXEC_SHA='01db41022c0a80031d4c882617d369096da0e578f26af791ff27570e4e584d30'
FAIL_NONCE='3220f863b804455dfdcb3d882ade6af42c6b5401e00f292bbcec956bd92e7b10'
FAIL_RECEIPT_SHA='4ebea01e9f495441656749984bba9438b9df0a3eba8b06d96ff9ec63ac12beda'
ROOT_RECEIPT_SHA='360a6ca0c04ed44634ea3493abc8ec489e24a511cf4b1a4627f7661409fecf91'
FAIL_SEQUENCE=1
PREIMAGE_SHA='e4886ba04cea4d6d6ac4bea86244a1f2b699e0e9c2e922cf22802d42997a4156'
ACL_SHA='3f0f3dfcfb0ae6694ec9d6833545c96860bc7e1657d9bfc3e384efe3f1926321'
ORIGINAL_SQL={
 'install':('c03_hd_gateway_v2_restricted_install_candidate.sql','9793ff39ca80d646a89041f0174f42bb717ae3e649e49f8d68d6f102792f5c51'),
 'inverse':('c03_hd_gateway_v2_restricted_inverse_candidate.sql','84114bac7b3e15f4cadaf3a566f705440eeb9cf8ba63f3be97249652d5f25449'),
 'pre':('c03_chat_social_v2_preimage_readonly.sql','8f0e0f92859b5b0b01fde7552d95263409a1874c672665021a4ea3b5235a7da6'),
 'post':('c03_chat_social_v2_postimage_readonly.sql',OLD_POST_SHA),
 'acl':('c03_chat_social_v2_acl_witness_readonly.sql','d0829593727b8b156ac07f5fc9a8d4477dd5f8e24696ffa2703fa7a802f07faa')
}
NEW_SQL_PIN={key:(name,NEW_POST_SHA if key=='post' else sha)
             for key,(name,sha) in ORIGINAL_SQL.items()}
HEX64=re.compile(r'[0-9a-f]{64}\Z')
RECOVERY_DOMAIN=b'AOE2WAR-WE1-CHAT-SOCIAL-HD-V2-AUTO-INVERSE-RECOVERY-ONLY-V1\x00'
RECOVERY_SCHEMA='wolo.we1.chat-social-auto-inverse-recovery.v1'
RECOVERY_ACTION='CHAT_SOCIAL_HD_V2_AUTO_INVERSE_RECOVERY_ONLY'
RECOVERY_PACKET='wolo.we1.chat-social-auto-inverse-signed-packet.v1'
STAGED_RECOVERY='signed-chat-social-auto-inverse-recovery.json'
STAGED_SQL='signed-one-use-chat-social-v2-permit.json'

class Hold(RuntimeError):pass
def need(cond,reason):
    if not cond:raise Hold(reason)
def digest(raw):return hashlib.sha256(raw).hexdigest()
def canonical(obj):return json.dumps(obj,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode()
def strict(raw):
    def pairs(kvs):
        result={}
        for key,val in kvs:
            need(key not in result,'DUPLICATE_JSON_KEY')
            result[key]=val
        return result
    value=json.loads(raw,object_pairs_hook=pairs)
    need(canonical(value)==raw.strip(),'NONCANONICAL_PACKET')
    return value
def read_trusted(path,owner,limit=32768):
    s=path.lstat()
    need(stat.S_ISREG(s.st_mode) and s.st_uid==owner and stat.S_IMODE(s.st_mode)==0o600
         and s.st_nlink==1 and 0<s.st_size<=limit,'FILE_OWNER_MODE_OR_SIZE_'+path.name)
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
    try:
        t=os.fstat(fd)
        need((s.st_dev,s.st_ino,s.st_size)==(t.st_dev,t.st_ino,t.st_size),'FILE_RACE')
        raw=os.read(fd,limit+1)
        need(len(raw)==s.st_size,'FILE_READ_DRIFT')
        return raw
    finally:os.close(fd)
def stage(name,limit=32768):return read_trusted(STAGE/name,1000,limit)
def root(path,limit=32768):return read_trusted(path,0,limit)
def verify_dir(p,owner,mode=0o700):
    st=p.lstat()
    need(stat.S_ISDIR(st.st_mode) and not stat.S_ISLNK(st.st_mode)
         and st.st_uid==owner and stat.S_IMODE(st.st_mode)==mode,'ROOT_OR_STAGE_DIRECTORY_DRIFT')
def write_once(parent,name,content):
    need(re.fullmatch(r'[A-Za-z0-9_.-]{1,130}',name),'FILE_NAME_DENIED')
    fd=os.open(parent/name,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW|os.O_CLOEXEC,0o600)
    try:
        with os.fdopen(fd,'wb',closefd=False) as f:
            f.write(content);f.flush();os.fsync(fd)
    finally:os.close(fd)
    dfd=os.open(parent,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(dfd)
    finally:os.close(dfd)
def new_dir(p):
    need(not p.exists() and not p.is_symlink(),'RECOVERY_PARTIAL_OR_ALREADY_INSTALLED')
    os.mkdir(p,0o700)
    verify_dir(p,0)
def open_module(path,expect):
    need(digest(root(path))==expect,'EXECUTOR_VERSION_SHA_DRIFT')
    spec=importlib.util.spec_from_file_location('we1_social_recovery_module',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    need(module.SOURCE==SOURCE and module.HBA_SHA256==HBA_SHA,'EXECUTOR_SCOPE_DRIFT')
    return module
def common():
    need(os.getuid()==os.geteuid()==0,'PROTECTED_ROOT_REQUIRED')
    verify_dir(STAGE,1000)
    for p in (ROOT,LIB,OLD_SQL,STATE):verify_dir(p,0)
    need(digest(root(PUBLIC,128))==PUBLIC_SHA,'UNEXPECTED_SOCIAL_KEY')
    old=open_module(OLD_EXEC,OLD_EXEC_SHA)
    need(old.verify_hba()==HBA_SHA,'HBA_DRIFT')
    for role,(name,sha) in ORIGINAL_SQL.items():
        need(digest(root(OLD_SQL/name))==sha,'ORIGINAL_SQL_DRIFT_'+role)
    enrollment=list(STATE.glob('root-enroll-receipt-*.json'))
    need(len(enrollment)==1 and digest(root(enrollment[0]))==ROOT_RECEIPT_SHA,
         'ORIGINAL_ROOT_ENROLLMENT_RECEIPT_DRIFT')
    failed=root(STATE/f'receipt-{FAIL_NONCE}.json')
    need(digest(failed)==FAIL_RECEIPT_SHA,'FAILED_SQL_RECEIPT_HASH_DRIFT')
    rec=strict(failed)
    need(rec.get('sequence')==1 and rec.get('nonce')==FAIL_NONCE
         and rec.get('status')=='AUTO_INVERSE_PASS_AFTER_POSTIMAGE_HOLD'
         and rec.get('phase')=='install' and rec.get('financial_authorized') is False
         and rec.get('after_inverse_acl_sha256')==ACL_SHA
         and rec.get('acl_before_sha256')==ACL_SHA
         and rec.get('preimage_stdout_sha256')==PREIMAGE_SHA
         and rec.get('after_inverse_preimage_stdout_sha256')==PREIMAGE_SHA
         and rec.get('hba_sha256')==HBA_SHA,'FAILED_SQL_RECEIPT_CONTENT_DRIFT')
    return old

def instant(s):
    need(type(s) is str and re.fullmatch(r'\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ',s),'INVALID_TIME')
    return datetime.strptime(s,'%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc)
def signed_recovery(raw,public,clock=None):
    packet=strict(raw)
    need(type(packet) is dict and set(packet)=={'schema','request','signature_der_b64'}
         and packet['schema']==RECOVERY_PACKET,'RECOVERY_PACKET_FIELDS')
    req=packet['request']
    exact={'schema':RECOVERY_SCHEMA,'action':RECOVERY_ACTION,'source_commit':SOURCE,
       'host':'HEL1','database':'aoe2hd_db','owner_public_sha256':PUBLIC_SHA,
       'failed_sequence':FAIL_SEQUENCE,'failed_nonce':FAIL_NONCE,
       'failed_receipt_sha256':FAIL_RECEIPT_SHA,
       'root_enrollment_receipt_sha256':ROOT_RECEIPT_SHA,
       'original_acl_sha256':ACL_SHA,'original_preimage_sha256':PREIMAGE_SHA,
       'hba_sha256':HBA_SHA,'old_executor_sha256':OLD_EXEC_SHA,
       'new_executor_sha256':NEW_EXEC_SHA,'new_postimage_sha256':NEW_POST_SHA,
       'recovery_bootstrap_sha256':digest(Path(__file__).read_bytes()),
       'financial_authorized':False,'funding_authorized':False,
       'de_database_authorized':False,'raw_event_grants_authorized':False,
       'hba_mutation_authorized':False}
    need(type(req) is dict and set(req)==set(exact)|{'nonce','not_before','expires_at'},
         'RECOVERY_REQUEST_FIELDS')
    for k,v in exact.items():need(req[k]==v,'RECOVERY_SCOPE_DRIFT_'+k)
    need(type(req['nonce']) is str and HEX64.fullmatch(req['nonce'])
         and req['nonce']!='0'*64 and req['nonce']!=FAIL_NONCE,'RECOVERY_NONCE_REUSED')
    begin,end=instant(req['not_before']),instant(req['expires_at'])
    now=clock or datetime.now(timezone.utc)
    need(timedelta(0)<end-begin<=timedelta(seconds=900) and begin<=now<end,
         'RECOVERY_SIGNATURE_EXPIRED_OR_OVERSIZED')
    try:sig=base64.b64decode(packet['signature_der_b64'],validate=True)
    except (ValueError,binascii.Error):raise Hold('RECOVERY_SIGNATURE_ENCODING')
    need(64<=len(sig)<=80 and sig[0]==0x30,'RECOVERY_SIGNATURE_DER')
    need(type(public) is bytes and len(public)==65 and public[0]==4
         and digest(public)==PUBLIC_SHA,'RECOVERY_SIGNING_KEY_DRIFT')
    # Same audited isolated OpenSSL P256 verifier as the existing Social executor.
    spki=bytes.fromhex('3059301306072a8648ce3d020106082a8648ce3d030107034200')
    with tempfile.TemporaryDirectory(prefix='we1-chat-recovery-verify-') as tmp:
        directory=Path(tmp)
        for name,data in [('public.der',spki+public),
                          ('message',RECOVERY_DOMAIN+canonical(req)),
                          ('signature.der',sig)]:
            p=directory/name
            p.write_bytes(data);p.chmod(0o600)
        result=subprocess.run(['/usr/bin/openssl','dgst','-sha256','-keyform','DER',
             '-verify',str(directory/'public.der'),'-signature',str(directory/'signature.der'),
             str(directory/'message')],capture_output=True,timeout=8)
        need(result.returncode==0 and b'Verified OK' in result.stdout,
             'RECOVERY_SIGNATURE_INVALID')
    return req

def recover():
    old=common()
    need(not NEW.exists() and not NEW.is_symlink(),'RECOVERY_VERSION_ALREADY_EXISTS')
    data={role:stage(name) for role,(name,_) in NEW_SQL_PIN.items()}
    for role,(_,sha) in NEW_SQL_PIN.items():
        need(digest(data[role])==sha,'NEW_SQL_SOURCE_DRIFT_'+role)
    exe=stage('c03_chat_social_hd_v2_exact_executor.py')
    need(digest(exe)==NEW_EXEC_SHA,'NEW_EXECUTOR_SOURCE_DRIFT')
    req_raw=stage(STAGED_RECOVERY,8192)
    req=signed_recovery(req_raw,root(PUBLIC,128))
    nonce=req['nonce']
    lock=os.open(STATE/'controller.lock',os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
    try:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        fresh=open_module(OLD_EXEC,OLD_EXEC_SHA) # a second live check under lock
        need(fresh.verify_hba()==HBA_SHA,'HBA_CHANGE')
        # Never import owner-writable staged Python as root. Existing original
        # root executor MUST be stuck at the exact auto-inverse receipt, with no
        # extra transition/nonce/receipt. The new executable is imported only
        # after exact bytes are root-installed.
        need({x.name for x in STATE.glob('transition-*.json')}==
             {f'transition-00000001-{FAIL_NONCE}.json'},
             'NOT_EXACT_ONE_FAILED_SQL_TRANSITION')
        need(not list(STATE.glob('recovery-*')),'RECOVERY_PARTIAL_OR_REPLAY')
        old.no_pending_permit(ROOT,STATE,reader=root)
        try:old.next_transition(STATE,reader=root)
        except old.Hold as exc:
            need(str(exc)=='INCOMPLETE_OR_FAILED_SQL_TRANSITION',
                 'OLD_SQL_JOURNAL_UNEXPECTED_FAILURE')
        else:raise Hold('OLD_SQL_JOURNAL_IS_NOT_FAILED')
        sequence=2
        previous=FAIL_RECEIPT_SHA
        old_pre=fresh.psql(root(OLD_SQL/ORIGINAL_SQL['pre'][0]),readonly=True)
        old_acl=fresh.psql(root(OLD_SQL/ORIGINAL_SQL['acl'][0]),readonly=True)
        need(old_pre==PREIMAGE_SHA and old_acl==ACL_SHA,'LIVE_RESTORED_HD_PREIMAGE_OR_ACL_DRIFT')
        need(fresh.verify_hba()==HBA_SHA,'HBA_POST_READ_DRIFT')
        permit_hash=digest(req_raw)
        # Immutable admission and nonce consumption happen before root version
        # creation. Any crash/partial file is HOLD, never implicit retry.
        write_once(ROOT,f'signed-one-use-chat-social-auto-inverse-recovery-{nonce}.json',req_raw)
        write_once(STATE,f'recovery-transition-{sequence:08d}-{nonce}.json',canonical({
            'sequence':sequence,'nonce':nonce,'phase':'recovery',
            'previous_receipt_sha256':previous,
            'failed_nonce':FAIL_NONCE,'failed_sequence':FAIL_SEQUENCE,
            'failed_receipt_sha256':FAIL_RECEIPT_SHA,
            'permit_sha256':permit_hash})+b'\n')
        write_once(STATE,f'recovery-nonce-{nonce}.consumed',canonical({
            'nonce':nonce,'phase':'recovery','permit_sha256':permit_hash,
            'status':'CONSUMED_BEFORE_RECOVERY'})+b'\n')
        new_dir(NEW);new_dir(NEW_SQL)
        write_once(NEW,NEW_EXEC.name,exe)
        for role,(name,_) in NEW_SQL_PIN.items():write_once(NEW_SQL,name,data[role])
        need(digest(root(NEW_EXEC))==NEW_EXEC_SHA,'NEW_ROOT_EXECUTOR_POSTIMAGE')
        for role,(name,sha) in NEW_SQL_PIN.items():
            need(digest(root(NEW_SQL/name))==sha,'NEW_ROOT_SQL_POSTIMAGE_'+role)
        need(fresh.verify_hba()==HBA_SHA,'HBA_POST_SOURCE_INSTALL')
        receipt={'schema':'wolo.we1.chat-social-auto-inverse-root-recovery-receipt.v1',
            'status':'AUTO_INVERSE_RECOVERY_EPOCH_PASS','phase':'recovery',
            'sequence':sequence,'nonce':nonce,'previous_receipt_sha256':previous,
            'failed_nonce':FAIL_NONCE,'failed_sequence':FAIL_SEQUENCE,
            'failed_receipt_sha256':FAIL_RECEIPT_SHA,'permit_sha256':permit_hash,
            'source_commit':SOURCE,'owner_public_sha256':PUBLIC_SHA,
            'old_executor_sha256':OLD_EXEC_SHA,'new_executor_sha256':NEW_EXEC_SHA,
            'new_postimage_sha256':NEW_POST_SHA,
            'live_preimage_stdout_sha256':old_pre,'live_acl_sha256':old_acl,
            'hba_sha256':HBA_SHA,'financial_authorized':False,
            'funding_authorized':False,'de_database_authorized':False,
            'utc':datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}
        raw=canonical(receipt)+b'\n'
        write_once(STATE,f'recovery-receipt-{nonce}.json',raw)
        # The reviewed root-owned executable alone interprets the new journal.
        newmod=open_module(NEW_EXEC,NEW_EXEC_SHA)
        need(newmod.next_transition(STATE,reader=root)==('install',3,digest(raw)),
             'RECOVERY_JOURNAL_NOT_INSTALL_READY')
        return {'status':'PASS_SIGNED_AUTO_INVERSE_RECOVERY_NO_SQL',
                'receipt_sha256':digest(raw),'sequence':sequence,'nonce':nonce}
    finally:os.close(lock)

def deliver_sql():
    old=common()
    verify_dir(NEW,0);verify_dir(NEW_SQL,0)
    new=open_module(NEW_EXEC,NEW_EXEC_SHA)
    need(new.verify_hba()==HBA_SHA,'NEW_HBA_DRIFT')
    for role,(name,sha) in NEW_SQL_PIN.items():
        need(digest(root(NEW_SQL/name))==sha,'NEW_SQL_ROOT_SOURCE_DRIFT_'+role)
    packet=stage(STAGED_SQL,8192)
    parsed=new.strict_json(packet)
    need(type(parsed) is dict and type(parsed.get('request')) is dict,'INVALID_SQL_PACKET')
    phase=parsed['request'].get('phase')
    need(phase in ('install','inverse'),'SQL_ONLY_PHASE_DENIED')
    req=new.verify_signed_packet(packet,root(PUBLIC,128),datetime.now(timezone.utc),phase)
    nonce=req['nonce']
    lock=os.open(STATE/'controller.lock',os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
    try:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        expected,sequence,_=new.next_transition(STATE,reader=root)
        need(phase==expected and sequence>=3,'NO_SIGNED_RECOVERY_EPOCH')
        new.no_pending_permit(ROOT,STATE,reader=root)
        target=new.permit_path(phase,nonce)
        need(not target.exists(),'PERMIT_ALREADY_DELIVERED')
        write_once(ROOT,target.name,packet)
        receipt={'schema':'wolo.we1.chat-social-v2-permit-delivery-receipt.v2',
            'status':'PASS_SIGNED_CHAT_SOCIAL_PERMIT_ROOT_DELIVERED_NO_SQL',
            'phase':phase,'sequence':sequence,'nonce':nonce,'permit_sha256':digest(packet),
            'permit_file':target.name,'source_commit':SOURCE,'database_sql_executed':False,
            'utc':datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}
        raw=canonical(receipt)+b'\n'
        write_once(STATE,f'permit-delivery-{nonce}.json',raw)
        return {'status':receipt['status'],'phase':phase,'sequence':sequence,
                'nonce':nonce,'receipt_sha256':digest(raw)}
    finally:os.close(lock)

def main():
    try:
        need(len(sys.argv)==2 and sys.argv[1] in ('recover','deliver-sql'),
             'RECOVERY_OPERATOR_PHASE_DENIED')
        result=recover() if sys.argv[1]=='recover' else deliver_sql()
        print(json.dumps(result,sort_keys=True));return 0
    except Exception as e:
        print(json.dumps({'status':'HOLD_CHAT_SOCIAL_AUTO_INVERSE_RECOVERY',
             'reason':str(e)[:150],'financial_authorized':False,
             'sql_executed':False},sort_keys=True));return 3

if __name__=='__main__':sys.exit(main())

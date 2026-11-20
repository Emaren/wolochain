#!/usr/bin/env python3
"""WE2-reviewed Chat-only root enrollment and signed-permit delivery.

NO SQL execution here. Admission is NOT conferred by this source; WE2 must
independently approve and invoke it through the protected root pathway.
"""
from __future__ import annotations
import base64
from datetime import datetime,timezone,timedelta
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import pwd
import re
import stat
import sys
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import hashes

STAGE=Path('/home/tony/we1-chat-social-v2-executor-stage-20261120')
ROOT=Path('/etc/wolo-financial-chat-social-v2')
LIB=Path('/usr/local/libexec/wolo-financial-chat-social-v2')
SQL=LIB/'sql'
STATE=Path('/var/lib/wolo-financial-role-state/v1/chat-social-hd-v2-exact')
PUBLIC=ROOT/'owner-chat-social-p256-public-x963.bin'
PERMIT=ROOT/'signed-one-use-chat-social-v2-permit.json'
HBA=Path('/etc/postgresql/16/main/pg_hba.conf')
HBA_SHA='3fecbffb683bf2bc21e8bd880b9be982d14cbe3bbf67aae08f801159d6b76789'
SOURCE='5cf4f223a7b187f6596b6a9caac26aec7afd6e94'
PUBLIC_SHA='032e9bf17d6b6f71d672d2728aad2c41f6c061893e8dc9cbc2616353a5e10bc3'
EXEC_SHA='9b5ec495946517b253a0c1dfdd86dd5a487bc55a3791eaddcaea9d7456f02323'
NAMES={
'c03_chat_social_hd_v2_exact_executor.py':EXEC_SHA,
'c03_hd_gateway_v2_restricted_install_candidate.sql':'9793ff39ca80d646a89041f0174f42bb717ae3e649e49f8d68d6f102792f5c51',
'c03_hd_gateway_v2_restricted_inverse_candidate.sql':'84114bac7b3e15f4cadaf3a566f705440eeb9cf8ba63f3be97249652d5f25449',
'c03_chat_social_v2_preimage_readonly.sql':'8f0e0f92859b5b0b01fde7552d95263409a1874c672665021a4ea3b5235a7da6',
'c03_chat_social_v2_postimage_readonly.sql':'e14eb681cfd097209d05afff5d3ec34df29581643c2c6f5e2cb7918d2adbae6a',
'c03_chat_social_v2_acl_witness_readonly.sql':'d0829593727b8b156ac07f5fc9a8d4477dd5f8e24696ffa2703fa7a802f07faa'
}
DOMAIN=b'AOE2WAR-WE1-CHAT-SOCIAL-HD-V2-SQL-ONLY-V1\x00ROOT_TRUST_ENROLL_ONLY_V1\x00'
SCHEMA='wolo.we1.chat-social-v2-root-enrollment.v1'
ACTION='CHAT_SOCIAL_HD_V2_ROOT_ENROLL_ONLY'
HEX=re.compile(r'[0-9a-f]{64}\Z')

class Hold(RuntimeError): pass

def check(ok, reason):
    if not ok:raise Hold(reason)

def sha(raw):return hashlib.sha256(raw).hexdigest()
def canonical(obj):return json.dumps(obj,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode()
def json_exact(raw):
    def pairs(xs):
        d={}
        for k,v in xs:
            check(k not in d,'DUPLICATE_JSON_KEY');d[k]=v
        return d
    q=json.loads(raw,object_pairs_hook=pairs)
    check(canonical(q)==raw.strip(),'NONCANONICAL_JSON')
    return q
def clock(s):
    check(type(s) is str and re.fullmatch(r'\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ',s),'BAD_TIME')
    try:return datetime.strptime(s,'%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc)
    except ValueError:raise Hold('BAD_TIME')

def stage_file(name,limit=32768):
    p=STAGE/name
    check(p.name==name and not p.is_symlink(),'STAGE_NAME')
    a=p.lstat()
    check(stat.S_ISREG(a.st_mode) and a.st_uid==1000 and stat.S_IMODE(a.st_mode)==0o600 and
          a.st_nlink==1 and 0<a.st_size<=limit,'STAGED_FILE_OWNER_OR_MODE')
    fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
    try:
        b=os.fstat(fd)
        check((a.st_dev,a.st_ino,a.st_size)==(b.st_dev,b.st_ino,b.st_size),'STAGE_RACE')
        data=os.read(fd,limit+1)
        check(len(data)==a.st_size,'STAGE_LENGTH')
        return data
    finally:os.close(fd)

def root_file(p,limit=32768):
    a=p.lstat()
    check(stat.S_ISREG(a.st_mode) and a.st_uid==0 and stat.S_IMODE(a.st_mode)==0o600
          and a.st_nlink==1 and 0<a.st_size<=limit,'ROOT_FILE_OWNER_OR_MODE')
    fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
    try:
        b=os.fstat(fd)
        check((a.st_dev,a.st_ino,a.st_size)==(b.st_dev,b.st_ino,b.st_size),'ROOT_RACE')
        data=os.read(fd,limit+1)
        check(len(data)==a.st_size,'ROOT_LENGTH')
        return data
    finally:os.close(fd)

def newdir(p):
    check(not p.exists() and not p.is_symlink(),'TARGET_NOT_ABSENT')
    os.mkdir(p,0o700)
    os.chmod(p,0o700)
    check(p.lstat().st_uid==0 and stat.S_IMODE(p.lstat().st_mode)==0o700,'TARGET_DIR_MODE')

def newfile(p,data):
    fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC,0o600)
    try:
        os.fchmod(fd,0o600)
        with os.fdopen(fd,'wb',closefd=False) as f:f.write(data);f.flush();os.fsync(f.fileno())
    finally:os.close(fd)
    dfd=os.open(p.parent,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(dfd)
    finally:os.close(dfd)

def prerequisite():
    check(os.getuid()==os.geteuid()==0,'ROOT_EXECUTOR_REQUIRED')
    st=STAGE.lstat()
    check(stat.S_ISDIR(st.st_mode) and st.st_uid==1000 and stat.S_IMODE(st.st_mode)==0o700,
          'OWNER_STAGE_DIR_UNSAFE')
    for base in (ROOT.parent,LIB.parent,STATE.parent):
        d=base
        while d!=Path('/'):
            st=d.lstat()
            check(stat.S_ISDIR(st.st_mode) and st.st_uid==0 and not st.st_mode&0o022,
                 'ROOT_PARENT_UNSAFE_'+str(d))
            d=d.parent
    st=HBA.lstat()
    check(stat.S_ISREG(st.st_mode) and st.st_uid==pwd.getpwnam('postgres').pw_uid
          and sha(HBA.read_bytes())==HBA_SHA,'HBA_NOT_ADMITTED')
    check(sha(stage_file('owner-chat-social-p256-public-x963.bin',128))==PUBLIC_SHA,
          'WRONG_OWNER_SOCIAL_PUBLIC')

def validate_enrollment(raw,sig,public):
    q=json_exact(raw)
    expect={'schema':SCHEMA,'action':ACTION,'source_commit':SOURCE,
        'host':'HEL1','database':'aoe2hd_db','owner_public_sha256':PUBLIC_SHA,
        'executor_sha256':EXEC_SHA,'file_sha256':NAMES,'hba_sha256':HBA_SHA,
        'financial_authorized':False,'funding_authorized':False,
        'de_database_authorized':False,'hba_mutation_authorized':False,
        'custody_authorized':False,'product_release_authorized':False}
    check(set(q)==set(expect)|{'nonce','not_before','expires_at','bootstrap_sha256'},
          'ENROLL_REQUEST_FIELDS')
    for k,v in expect.items():check(q[k]==v,'ENROLL_WRONG_'+k)
    check(q['bootstrap_sha256']==sha(Path(__file__).read_bytes()),'BOOTSTRAP_SOURCE_DRIFT')
    check(type(q['nonce']) is str and HEX.fullmatch(q['nonce']) and q['nonce']!='0'*64,'ENROLL_NONCE')
    begin,end=clock(q['not_before']),clock(q['expires_at'])
    now=datetime.now(timezone.utc)
    check(timedelta(0)<end-begin<=timedelta(seconds=900) and begin<=now<end,'ENROLL_EXPIRED')
    check(len(public)==65 and public[0]==4 and sha(public)==PUBLIC_SHA,'OWNER_PUBLIC_INVALID')
    ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(),public).verify(
        sig,DOMAIN+canonical(q),ec.ECDSA(hashes.SHA256()))
    return q

def enroll():
    prerequisite()
    for p in (ROOT,LIB,SQL,STATE):
        check(not p.exists() and not p.is_symlink(),'SOCIAL_ROOT_ALREADY_PRESENT')
    public=stage_file('owner-chat-social-p256-public-x963.bin',128)
    request=stage_file('root-enrollment-request.json',8192)
    signature=stage_file('root-enrollment-signature.der',128)
    q=validate_enrollment(request,signature,public)
    data={name:stage_file(name,32768) for name in NAMES}
    for name,expected in NAMES.items():check(sha(data[name])==expected,'SOURCE_SHA_DRIFT_'+name)
    newdir(STATE)
    newfile(STATE/('root-enroll-nonce-'+q['nonce']+'.consumed'),
       canonical({'status':'CONSUMED_BEFORE_ROOT_ENROLL','nonce':q['nonce'],
                  'signed_request_sha256':sha(request)})+b'\n')
    newdir(ROOT);newdir(LIB);newdir(SQL)
    newfile(PUBLIC,public)
    newfile(ROOT/'root-enrollment-request.json',request)
    newfile(ROOT/'root-enrollment-signature.der',signature)
    newfile(LIB/'c03_chat_social_hd_v2_exact_executor.py',data['c03_chat_social_hd_v2_exact_executor.py'])
    for name in NAMES:
        if name.endswith('.sql'):newfile(SQL/name,data[name])
    check(sha(root_file(PUBLIC,128))==PUBLIC_SHA,'PUBLIC_POSTIMAGE')
    check(sha(root_file(LIB/'c03_chat_social_hd_v2_exact_executor.py'))==EXEC_SHA,'EXECUTOR_POSTIMAGE')
    for name,h in NAMES.items():
        if name.endswith('.sql'):check(sha(root_file(SQL/name))==h,'SQL_POSTIMAGE')
    receipt={'schema':'wolo.we1.chat-social-v2-root-enrollment-receipt.v1',
      'status':'PASS_CHAT_SOCIAL_ROOT_TRUST_ENROLLED_NO_SQL',
      'source_commit':SOURCE,'action':ACTION,'nonce':q['nonce'],
      'owner_public_sha256':PUBLIC_SHA,'executor_sha256':EXEC_SHA,
      'signed_request_sha256':sha(request),'signature_sha256':sha(signature),
      'hba_sha256':HBA_SHA,'files_sha256':NAMES,
      'database_sql_executed':False,'financial_authorized':False,
      'utc':datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}
    raw=canonical(receipt)+b'\n'
    newfile(STATE/('root-enroll-receipt-'+q['nonce']+'.json'),raw)
    return {'status':receipt['status'],'receipt_sha256':sha(raw)}

def install_permit():
    prerequisite()
    for d in (ROOT,LIB,SQL,STATE):
        st=d.lstat()
        check(stat.S_ISDIR(st.st_mode) and st.st_uid==0 and stat.S_IMODE(st.st_mode)==0o700,
              'ROOT_DIR_NOT_ADMITTED')
    check(sha(root_file(PUBLIC,128))==PUBLIC_SHA,'ROOT_PUBLIC_DRIFT')
    check(sha(root_file(LIB/'c03_chat_social_hd_v2_exact_executor.py'))==EXEC_SHA,
          'EXECUTOR_UNTRUSTED')
    for name,digest in NAMES.items():
        if name.endswith('.sql'):check(sha(root_file(SQL/name))==digest,'ROOT_SQL_DRIFT')
    data=stage_file('signed-one-use-chat-social-v2-permit.json',8192)
    spec=importlib.util.spec_from_file_location('we1_social_exact',LIB/'c03_chat_social_hd_v2_exact_executor.py')
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    check(module.verify_hba()==HBA_SHA,'HBA_POSTIMAGE_CHANGED')
    req=module.verify_signed_packet(data,root_file(PUBLIC,128),datetime.now(timezone.utc),'install')
    check(not PERMIT.exists() and not PERMIT.is_symlink(),'SIGNED_PERMIT_ALREADY_INSTALLED')
    newfile(PERMIT,data)
    receipt={'schema':'wolo.we1.chat-social-v2-permit-delivery-receipt.v1',
       'status':'PASS_SIGNED_CHAT_SOCIAL_PERMIT_ROOT_DELIVERED_NO_SQL',
       'nonce':req['nonce'],'permit_sha256':sha(data),
       'source_commit':SOURCE,'database_sql_executed':False,
       'utc':datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}
    raw=canonical(receipt)+b'\n'
    newfile(STATE/('permit-delivery-'+req['nonce']+'.json'),raw)
    return {'status':receipt['status'],'receipt_sha256':sha(raw)}

def main():
    try:
        check(len(sys.argv)==2 and sys.argv[1] in ('enroll','install-permit'),'UNSUPPORTED_PHASE')
        print(json.dumps(enroll() if sys.argv[1]=='enroll' else install_permit(),sort_keys=True))
        return 0
    except Exception as e:
        print(json.dumps({'status':'HOLD_CHAT_SOCIAL_ROOT_INSTALL',
             'reason':str(e)[:160],'database_sql_executed':False},sort_keys=True))
        return 3

if __name__=='__main__':sys.exit(main())

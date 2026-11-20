#!/usr/bin/env python3
"""Owner Mac only. Build a fresh purpose-locked Chat Social V2 P256 packet.

No private-key export. Generation alone is not root/DB authorization.
Use only after WE2 admits the exact Chat root executor and delivery channel.
"""
from __future__ import annotations
import base64
from datetime import datetime,timedelta,timezone
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys

PUBLIC_SHA='032e9bf17d6b6f71d672d2728aad2c41f6c061893e8dc9cbc2616353a5e10bc3'
EXEC_SHA='abdf19968227e41a6c5f7e003408f9e7a55cc1cb4cdf0d1cb833cf3306adaa25'
BOOTSTRAP_SHA='5c49ce261954893fb1eaaf570d29bd9e2587b6c30e7430575d60164b4be3e765'
SOURCE='5cf4f223a7b187f6596b6a9caac26aec7afd6e94'
HBA_SHA='3fecbffb683bf2bc21e8bd880b9be982d14cbe3bbf67aae08f801159d6b76789'
ROOT_SCHEMA='wolo.we1.chat-social-v2-root-enrollment.v1'
SQL_SCHEMA='wolo.we1.chat-social-hd-v2-exact-request.v1'
PACKET_SCHEMA='wolo.we1.chat-social-hd-v2-signed-packet.v1'
ACTION='CHAT_SOCIAL_HD_V2_SQL_ONLY'
ROOT_ACTION='CHAT_SOCIAL_HD_V2_ROOT_ENROLL_ONLY'
DOMAIN=b'AOE2WAR-WE1-CHAT-SOCIAL-HD-V2-SQL-ONLY-V1\x00'
ROOT_SUFFIX=b'ROOT_TRUST_ENROLL_ONLY_V1\x00'
FILES={
'c03_chat_social_hd_v2_exact_executor.py':EXEC_SHA,
'c03_hd_gateway_v2_restricted_install_candidate.sql':'9793ff39ca80d646a89041f0174f42bb717ae3e649e49f8d68d6f102792f5c51',
'c03_hd_gateway_v2_restricted_inverse_candidate.sql':'84114bac7b3e15f4cadaf3a566f705440eeb9cf8ba63f3be97249652d5f25449',
'c03_chat_social_v2_preimage_readonly.sql':'8f0e0f92859b5b0b01fde7552d95263409a1874c672665021a4ea3b5235a7da6',
'c03_chat_social_v2_postimage_readonly.sql':'e14eb681cfd097209d05afff5d3ec34df29581643c2c6f5e2cb7918d2adbae6a',
'c03_chat_social_v2_acl_witness_readonly.sql':'e5262f05dacbe6b108aa1807f3fff702e2019b16041bc0a3d60aca6449a07527'}
SOCIAL_PUBLIC=Path('/private/tmp/we1-chat-social-owner-signing-20261120/owner-chat-social-p256-public-x963.bin')
SIGNER=Path(__file__).with_name('c03_chat_social_owner_keychain_v1.swift')
SPKI=bytes.fromhex('3059301306072a8648ce3d020106082a8648ce3d030107034200')

def canonical(o):return json.dumps(o,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode()
def hashb(o):return hashlib.sha256(o).hexdigest()
def make(path,data):
    fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb') as f:f.write(data);f.flush();os.fsync(f.fileno())

def issue(mode,out):
    assert mode in ('enroll','install','inverse')
    assert out.is_dir() and not out.is_symlink() and (out.stat().st_mode&0o777)==0o700 and out.stat().st_uid==os.geteuid()
    assert sys.platform=='darwin' and os.geteuid()!=0
    assert SOCIAL_PUBLIC.is_file() and (SOCIAL_PUBLIC.stat().st_mode&0o777)==0o600
    pub=SOCIAL_PUBLIC.read_bytes()
    assert len(pub)==65 and pub[0]==4 and hashb(pub)==PUBLIC_SHA
    assert SIGNER.is_file() and SIGNER.is_absolute()
    now=datetime.now(timezone.utc)
    times={'not_before':(now-timedelta(seconds=10)).strftime('%Y-%m-%dT%H:%M:%SZ'),
           'expires_at':(now+timedelta(minutes=10)).strftime('%Y-%m-%dT%H:%M:%SZ')}
    flags=dict(financial_authorized=False,funding_authorized=False,
               de_database_authorized=False,hba_mutation_authorized=False)
    if mode=='enroll':
        req=dict(schema=ROOT_SCHEMA,action=ROOT_ACTION,source_commit=SOURCE,
             host='HEL1',database='aoe2hd_db',owner_public_sha256=PUBLIC_SHA,
             executor_sha256=EXEC_SHA,file_sha256=FILES,hba_sha256=HBA_SHA,
             bootstrap_sha256=BOOTSTRAP_SHA,
             custody_authorized=False,product_release_authorized=False,
             **flags,**times,nonce=secrets.token_hex(32))
        message=DOMAIN+ROOT_SUFFIX+canonical(req)
        request_name='root-enrollment-request.json'
        signature_name='root-enrollment-signature.der'
    else:
        req=dict(schema=SQL_SCHEMA,action=ACTION,phase=mode,host='HEL1',
             database='aoe2hd_db',source_commit=SOURCE,
             owner_public_sha256=PUBLIC_SHA,
             file_sha256={
               'install':FILES['c03_hd_gateway_v2_restricted_install_candidate.sql'],
               'inverse':FILES['c03_hd_gateway_v2_restricted_inverse_candidate.sql'],
               'pre':FILES['c03_chat_social_v2_preimage_readonly.sql'],
               'post':FILES['c03_chat_social_v2_postimage_readonly.sql'],
               'acl':FILES['c03_chat_social_v2_acl_witness_readonly.sql']},
             hba_sha256=HBA_SHA,raw_event_grants_authorized=False,
             **flags,**times,nonce=secrets.token_hex(32))
        message=DOMAIN+canonical(req)
        request_name='signed-chat-social-request.json'
        signature_name='signed-chat-social-signature.der'
    make(out/request_name,canonical(req)+b'\n')
    make(out/'owner-chat-social-signing-message.bin',message)
    p=subprocess.run(['swift',str(SIGNER),'sign',str(out/'owner-chat-social-signing-message.bin'),
                       str(out/signature_name)],capture_output=True,text=True,timeout=55)
    if p.returncode:raise RuntimeError('KEYCHAIN_SIGN_REJECTED: '+p.stdout[-200:])
    sig=(out/signature_name).read_bytes()
    assert 64<=len(sig)<=80
    make(out/'owner-social-public-spki.der',SPKI+pub)
    v=subprocess.run(['/usr/bin/openssl','dgst','-sha256','-keyform','DER','-verify',
      str(out/'owner-social-public-spki.der'),'-signature',str(out/signature_name),
      str(out/'owner-chat-social-signing-message.bin')],capture_output=True,timeout=10)
    assert v.returncode==0 and b'Verified OK' in v.stdout
    if mode!='enroll':
        packet=dict(schema=PACKET_SCHEMA,request=req,
                    signature_der_b64=base64.b64encode(sig).decode('ascii'))
        make(out/'signed-one-use-chat-social-v2-permit.json',canonical(packet)+b'\n')
    print(json.dumps({'status':'PASS_OWNER_SOCIAL_P256_SIGNED_NOT_ADMITTED',
      'mode':mode,'nonce':req['nonce'],'expires_at':req['expires_at'],
      'public_sha256':PUBLIC_SHA,'signature_sha256':hashb(sig),
      'root_and_db_authority_admitted':False},sort_keys=True))

if __name__=='__main__':
    if len(sys.argv)!=3:raise SystemExit('usage: builder.py enroll|install|inverse PRIVATE_0700_OUTPUT_DIRECTORY')
    issue(sys.argv[1],Path(sys.argv[2]).resolve())

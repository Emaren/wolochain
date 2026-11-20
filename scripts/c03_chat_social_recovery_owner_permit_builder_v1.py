#!/usr/bin/env python3
"""Mac owner-only, Keychain-bound recovery and fresh Social SQL permit builder.

Requires separate WE2-reviewed recovery source admission. Never exports the
private P256 key. Recovery is NOT a retry of the failed original install.
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

SOURCE='5cf4f223a7b187f6596b6a9caac26aec7afd6e94'
PUBLIC_SHA='032e9bf17d6b6f71d672d2728aad2c41f6c061893e8dc9cbc2616353a5e10bc3'
HBA_SHA='3fecbffb683bf2bc21e8bd880b9be982d14cbe3bbf67aae08f801159d6b76789'
OLD_EXEC_SHA='cab4b055e169d6544953611bc08a8132cd917f4a6500b19cd75b5576f99dc1b6'
NEW_EXEC_SHA='01db41022c0a80031d4c882617d369096da0e578f26af791ff27570e4e584d30'
NEW_POST_SHA='e2509411bff373116f936dd378b8eea9dd1fa2e5da766711babce9a5bd5d8360'
ROOT_RECOVERY_SHA='f7ccffd384b780ea029a0b558a5460ac3fef07d4fa2d5822c3f2ae7cf1849526'
FAIL_NONCE='3220f863b804455dfdcb3d882ade6af42c6b5401e00f292bbcec956bd92e7b10'
FAIL_RECEIPT_SHA='4ebea01e9f495441656749984bba9438b9df0a3eba8b06d96ff9ec63ac12beda'
ROOT_RECEIPT_SHA='360a6ca0c04ed44634ea3493abc8ec489e24a511cf4b1a4627f7661409fecf91'
PREIMAGE_SHA='e4886ba04cea4d6d6ac4bea86244a1f2b699e0e9c2e922cf22802d42997a4156'
ACL_SHA='3f0f3dfcfb0ae6694ec9d6833545c96860bc7e1657d9bfc3e384efe3f1926321'
RECOVERY_DOMAIN=b'AOE2WAR-WE1-CHAT-SOCIAL-HD-V2-AUTO-INVERSE-RECOVERY-ONLY-V1\x00'
SQL_DOMAIN=b'AOE2WAR-WE1-CHAT-SOCIAL-HD-V2-SQL-ONLY-V1\x00'
RECOVERY_SCHEMA='wolo.we1.chat-social-auto-inverse-recovery.v1'
RECOVERY_ACTION='CHAT_SOCIAL_HD_V2_AUTO_INVERSE_RECOVERY_ONLY'
RECOVERY_PACKET='wolo.we1.chat-social-auto-inverse-signed-packet.v1'
SQL_SCHEMA='wolo.we1.chat-social-hd-v2-exact-request.v1'
SQL_ACTION='CHAT_SOCIAL_HD_V2_SQL_ONLY'
SQL_PACKET='wolo.we1.chat-social-hd-v2-signed-packet.v1'
FILES={
    'install':'9793ff39ca80d646a89041f0174f42bb717ae3e649e49f8d68d6f102792f5c51',
    'inverse':'84114bac7b3e15f4cadaf3a566f705440eeb9cf8ba63f3be97249652d5f25449',
    'pre':'8f0e0f92859b5b0b01fde7552d95263409a1874c672665021a4ea3b5235a7da6',
    'post':NEW_POST_SHA,
    'acl':'d0829593727b8b156ac07f5fc9a8d4477dd5f8e24696ffa2703fa7a802f07faa'
}
PUBLIC=Path('/private/tmp/we1-chat-social-owner-signing-20261120/owner-chat-social-p256-public-x963.bin')
SIGNER=Path(__file__).with_name('c03_chat_social_owner_keychain_v1.swift')
SPKI=bytes.fromhex('3059301306072a8648ce3d020106082a8648ce3d030107034200')

def canonical(obj):return json.dumps(obj,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode()
def digest(raw):return hashlib.sha256(raw).hexdigest()
def write_once(path,raw):
    fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb') as f:
        f.write(raw);f.flush();os.fsync(f.fileno())
def request(mode,now,nonce):
    assert mode in ('recover','install','inverse')
    assert len(nonce)==64 and nonce.isascii() and all(c in '0123456789abcdef' for c in nonce)
    time_fields={'not_before':(now-timedelta(seconds=10)).strftime('%Y-%m-%dT%H:%M:%SZ'),
                 'expires_at':(now+timedelta(minutes=10)).strftime('%Y-%m-%dT%H:%M:%SZ')}
    flags={'financial_authorized':False,'funding_authorized':False,
           'de_database_authorized':False,'raw_event_grants_authorized':False,
           'hba_mutation_authorized':False}
    if mode=='recover':
        return dict(schema=RECOVERY_SCHEMA,action=RECOVERY_ACTION,source_commit=SOURCE,
            host='HEL1',database='aoe2hd_db',owner_public_sha256=PUBLIC_SHA,
            failed_sequence=1,failed_nonce=FAIL_NONCE,
            failed_receipt_sha256=FAIL_RECEIPT_SHA,
            root_enrollment_receipt_sha256=ROOT_RECEIPT_SHA,
            original_acl_sha256=ACL_SHA,original_preimage_sha256=PREIMAGE_SHA,
            hba_sha256=HBA_SHA,old_executor_sha256=OLD_EXEC_SHA,
            new_executor_sha256=NEW_EXEC_SHA,new_postimage_sha256=NEW_POST_SHA,
            recovery_bootstrap_sha256=ROOT_RECOVERY_SHA,
            nonce=nonce,**flags,**time_fields)
    return dict(schema=SQL_SCHEMA,action=SQL_ACTION,phase=mode,source_commit=SOURCE,
        host='HEL1',database='aoe2hd_db',owner_public_sha256=PUBLIC_SHA,
        file_sha256=FILES,hba_sha256=HBA_SHA,nonce=nonce,
        **flags,**time_fields)

def sign(mode,out):
    assert mode in ('recover','install','inverse')
    assert sys.platform=='darwin' and os.geteuid()!=0
    assert out.is_dir() and not out.is_symlink() and out.stat().st_uid==os.geteuid()
    assert (out.stat().st_mode & 0o777)==0o700
    assert PUBLIC.is_file() and (PUBLIC.stat().st_mode&0o777)==0o600
    public=PUBLIC.read_bytes()
    assert len(public)==65 and public[0]==4 and digest(public)==PUBLIC_SHA
    assert SIGNER.is_file() and SIGNER.is_absolute()
    req=request(mode,datetime.now(timezone.utc),secrets.token_hex(32))
    domain=RECOVERY_DOMAIN if mode=='recover' else SQL_DOMAIN
    message=domain+canonical(req)
    write_once(out/'owner-chat-social-signing-message.bin',message)
    cp=subprocess.run(['swift',str(SIGNER),'sign',str(out/'owner-chat-social-signing-message.bin'),
                       str(out/'owner-chat-social-signature.der')],capture_output=True,text=True,timeout=55)
    if cp.returncode:raise RuntimeError('KEYCHAIN_SIGNATURE_NOT_GRANTED')
    signature=(out/'owner-chat-social-signature.der').read_bytes()
    assert 64<=len(signature)<=80 and signature[0]==0x30
    write_once(out/'owner-social-public-spki.der',SPKI+public)
    check=subprocess.run(['/usr/bin/openssl','dgst','-sha256','-keyform','DER',
          '-verify',str(out/'owner-social-public-spki.der'),
          '-signature',str(out/'owner-chat-social-signature.der'),
          str(out/'owner-chat-social-signing-message.bin')],capture_output=True,timeout=10)
    assert check.returncode==0 and b'Verified OK' in check.stdout
    schema=RECOVERY_PACKET if mode=='recover' else SQL_PACKET
    packet={'schema':schema,'request':req,
            'signature_der_b64':base64.b64encode(signature).decode('ascii')}
    name='signed-chat-social-auto-inverse-recovery.json' if mode=='recover' \
         else 'signed-one-use-chat-social-v2-permit.json'
    write_once(out/name,canonical(packet)+b'\n')
    print(json.dumps({'status':'PASS_OWNER_SOCIAL_RECOVERY_SIGNED_NOT_ROOT_ADMITTED',
        'mode':mode,'nonce':req['nonce'],'expires_at':req['expires_at'],
        'signature_sha256':digest(signature),'owner_public_sha256':PUBLIC_SHA,
        'financial_authorized':False,'sql_executed':False},sort_keys=True))

if __name__=='__main__':
    if len(sys.argv)!=3:raise SystemExit('usage: owner_builder.py recover|install|inverse PRIVATE_0700_OUTDIR')
    sign(sys.argv[1],Path(sys.argv[2]).resolve())

#!/usr/bin/env python3
"""Generate only a separately enrolled Lobby P256 SQL permit. Mac login Keychain only.

No Social, Financial, Wallet, C08 or custody key is accepted. Never exports key.
"""
from __future__ import annotations
import base64
from datetime import datetime,timedelta,timezone
import hashlib
import json
import os
from pathlib import Path
import secrets
import stat
import subprocess
import sys

HEAD='5049e148b345481a4e1a3a3ffe8625635771963e'
PUBLIC_SHA='02f2cd051de06553213dc96b9f73d53d0c530ad0a730672960a17acafc8d8b7e'
SQL_INSTALL='41381fc3ab254549e7ca982d95cab4c44bd9f2782681152d73b9c468597ab434'
SQL_INVERSE='cc18548000ef149b19352dc3dab23b49264c24f49e27b5b1619a37a0d0d26452'
CONTRACT='f571d8f3a0b1982a0189ea6e512d154bf6eca32ff4044a381e243a19d73faccb'
SOCIAL_INSTALLED_SHA='f129576f3c45bb51229e1f35e52c631dfb1f1e77abb672471141743021103120'
HBA_SHA='3fecbffb683bf2bc21e8bd880b9be982d14cbe3bbf67aae08f801159d6b76789'
DOMAIN=b'AOE2WAR-WE1-LOBBY-HD-V1-SQL-ONLY-V1\x00'
SCHEMA='wolo.we1.lobby-hd-v1-exact-request.v1'
ACTION='LOBBY_HD_V1_SQL_ONLY'
PACKET_SCHEMA='wolo.we1.lobby-hd-v1-signed-packet.v1'
SPKI=bytes.fromhex('3059301306072a8648ce3d020106082a8648ce3d030107034200')
ROOT=Path(__file__).resolve().parents[1]
SIGNER=ROOT/'scripts/c03_lobby_hd_v1_owner_keychain.swift'
EXECUTOR=ROOT/'scripts/c03_lobby_hd_v1_root_executor.py'

def sha(raw):return hashlib.sha256(raw).hexdigest()
def canonical(o):return json.dumps(o,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode()
def write_once(path,data):
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    try:
        with os.fdopen(fd,'wb',closefd=False) as f:f.write(data);f.flush();os.fsync(fd)
    finally:os.close(fd)

def sign(phase,output,public_path):
    assert sys.platform=='darwin' and os.geteuid()!=0
    assert phase in ('install','inverse')
    assert output.is_dir() and not output.is_symlink() and output.stat().st_uid==os.geteuid()
    assert stat.S_IMODE(output.stat().st_mode)==0o700
    assert public_path.is_file() and not public_path.is_symlink()
    assert public_path.stat().st_uid==os.geteuid() and stat.S_IMODE(public_path.stat().st_mode)==0o600
    pub=public_path.read_bytes()
    assert len(pub)==65 and pub[0]==4 and sha(pub)==PUBLIC_SHA
    assert SIGNER.is_file() and EXECUTOR.is_file()
    now=datetime.now(timezone.utc)
    req={'schema':SCHEMA,'action':ACTION,'phase':phase,'source_head':HEAD,
        'host':'HEL1','database':'aoe2hd_db','owner_public_sha256':PUBLIC_SHA,
        'root_executor_sha256':sha(EXECUTOR.read_bytes()),
        'sql_install_sha256':SQL_INSTALL,'sql_inverse_sha256':SQL_INVERSE,
        'source_contract_sha256':CONTRACT,'social_installed_receipt_sha256':SOCIAL_INSTALLED_SHA,
        'hba_sha256':HBA_SHA,'financial_authorized':False,'funding_authorized':False,
        'de_database_authorized':False,'raw_event_grants_authorized':False,
        'hba_mutation_authorized':False,'nonce':secrets.token_hex(32),
        'not_before':(now-timedelta(seconds=10)).strftime('%Y-%m-%dT%H:%M:%SZ'),
        'expires_at':(now+timedelta(minutes=10)).strftime('%Y-%m-%dT%H:%M:%SZ')}
    msg=DOMAIN+canonical(req)
    write_once(output/'owner-lobby-message.bin',msg)
    r=subprocess.run(['swift',str(SIGNER),'sign',str(output/'owner-lobby-message.bin'),
         str(output/'owner-lobby-signature.der')],capture_output=True,text=True,timeout=85)
    if r.returncode:raise RuntimeError('LOBBY_KEYCHAIN_SIGNATURE_DENIED:'+r.stdout[-80:])
    der=(output/'owner-lobby-signature.der').read_bytes()
    assert 64<=len(der)<=80 and der[0]==0x30
    write_once(output/'public-spki.der',SPKI+pub)
    v=subprocess.run(['/usr/bin/openssl','dgst','-sha256','-keyform','DER',
        '-verify',str(output/'public-spki.der'),
        '-signature',str(output/'owner-lobby-signature.der'),
        str(output/'owner-lobby-message.bin')],capture_output=True,timeout=10)
    assert v.returncode==0 and b'Verified OK' in v.stdout
    packet={'schema':PACKET_SCHEMA,'request':req,
            'signature_der_b64':base64.b64encode(der).decode('ascii')}
    raw=canonical(packet)+b'\n'
    write_once(output/'signed-one-use-lobby-hd-v1.json',raw)
    print(json.dumps({'status':'PASS_LOBBY_P256_KEYCHAIN_SQL_ONLY_SIGNED_NOT_EXECUTED',
        'source_head':HEAD,'phase':phase,'nonce':req['nonce'],
        'root_executor_sha256':req['root_executor_sha256'],
        'packet_sha256':sha(raw),'signature_sha256':sha(der),
        'owner_public_sha256':PUBLIC_SHA,'expires_at':req['expires_at'],
        'financial_authorized':False,'sql_executed':False},sort_keys=True))

if __name__=='__main__':
    if len(sys.argv)!=4:raise SystemExit('usage: lobby_owner_permit.py install|inverse PRIVATE_0700_OUT PUBLIC_0600')
    sign(sys.argv[1],Path(sys.argv[2]).resolve(),Path(sys.argv[3]).resolve())

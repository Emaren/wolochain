#!/usr/bin/env python3
"""Owner-present M1 packet builder. Does not install or deliver to root."""
import base64
from datetime import datetime,timedelta,timezone
import json
import os
from pathlib import Path
import secrets
import stat
import subprocess
import sys
import c03_hd_direct_media_native_executor as contract

def file0600(p,limit=16384):
    f=os.open(p,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
    try:
        s=os.fstat(f)
        contract.need(stat.S_ISREG(s.st_mode) and s.st_uid==os.getuid() and stat.S_IMODE(s.st_mode)==0o600 and s.st_nlink==1 and 0<s.st_size<=limit,'OWNER_INPUT_UNSAFE')
        data=os.read(f,limit+1)
        contract.need(len(data)==s.st_size,'OWNER_INPUT_READ_MISMATCH')
        return data
    finally:os.close(f)
def main():
    contract.need(sys.platform=='darwin' and os.getuid()!=0 and sys.stdin.isatty() and sys.stdout.isatty(),'OWNER_M1_TERMINAL_REQUIRED')
    if len(sys.argv)!=5:raise SystemExit('usage: builder.py install|inverse ROOT_PREFLIGHT_JSON OWNER_PUBLIC_0600 PRIVATE_EMPTY_DIR')
    phase,prepath,pubpath,outpath=sys.argv[1:]
    contract.need(phase in ('install','inverse'),'BAD_PHASE')
    out=Path(outpath).absolute();s=out.lstat()
    contract.need(stat.S_ISDIR(s.st_mode) and stat.S_IMODE(s.st_mode)==0o700 and s.st_uid==os.getuid() and out.resolve()==out and not any(out.iterdir()),'EMPTY_PRIVATE_DIR_REQUIRED')
    pub=file0600(Path(pubpath),128)
    pre=json.loads(file0600(Path(prepath)))
    review=pre['review']
    contract.need(pre['status']=='READ_ONLY_PREFLIGHT_NOT_ADMISSION' and review['schema']=='wolo.we1.hd-direct-media-root-review.v1','BAD_PREFLIGHT')
    contract.need(review['source_commit']==contract.SOURCE and review['executor_sha256']==contract.digest(Path(contract.__file__).read_bytes()) and review['file_sha256']==contract.file_pins() and review['owner_public_sha256']==contract.digest(pub),'LOCAL_SOURCE_OR_KEY_MISMATCH')
    for name,h in contract.FILES.values():contract.need(contract.digest(Path(contract.__file__).with_name(name).read_bytes())==h,'LOCAL_SQL_DRIFT')
    hd=contract.parse_witness(json.dumps(pre['hd']).encode(),'aoe2hd_db')
    de=contract.parse_witness(json.dumps(pre['de']).encode(),'aoe2de_db')
    contract.need(de['media_relations']==0 and de['media_functions']==0,'DE_DRIFT')
    contract.need((hd['media_relations'],hd['media_functions'])==((0,0) if phase=='install' else (5,4)),'HD_PHASE_DRIFT')
    now=datetime.now(timezone.utc).replace(microsecond=0)
    req={k:v for k,v in review.items() if k!='schema'}
    req.update(schema='wolo.we1.hd-direct-media-permit.v1',action='HD_DIRECT_MEDIA_SQL_ONLY',database='aoe2hd_db',phase=phase,nonce=secrets.token_hex(32),not_before=now.strftime('%Y-%m-%dT%H:%M:%SZ'),expires_at=(now+timedelta(minutes=10)).strftime('%Y-%m-%dT%H:%M:%SZ'),hd_full_sha256=hd['full_sha256'],hd_invariant_sha256=hd['invariant_sha256'],de_full_sha256=de['full_sha256'],**{x:False for x in contract.FLAGS})
    msg=out/'signing-message.bin';sig=out/'owner-signature.der'
    contract.write_once(msg,contract.DOMAIN+contract.canonical(req))
    subprocess.run(['swift',str(Path(__file__).with_name('c03_hd_direct_media_owner_keychain.swift')),'sign',str(msg),str(sig)],check=True,timeout=120)
    packet=contract.canonical({'request':req,'signature_der_b64':base64.b64encode(file0600(sig,128)).decode()})
    contract.verify_packet(packet,pub,review,phase,req['nonce'],datetime.now(timezone.utc))
    contract.write_once(out/('permit-'+req['nonce']+'.json'),packet+b'\n')
    print(json.dumps({'status':'SIGNED_OWNER_PACKET_NOT_ROOT_DELIVERED_OR_EXECUTED','nonce':req['nonce'],'phase':phase,'expires_at':req['expires_at'],'permit_sha256':contract.digest(packet+b'\n'),'financial_authorized':False}))
if __name__=='__main__':main()

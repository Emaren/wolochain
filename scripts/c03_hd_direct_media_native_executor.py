#!/usr/bin/env python3
"""Source-only fixed HD media SQL executor. No self-install or signing."""
from __future__ import annotations
import argparse
import base64
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

ROOT=Path('/etc/aoe2war-chat-media-hd-v1')
CODE=Path('/usr/local/libexec/aoe2war-chat-media-hd-v1')
STATE=Path('/var/lib/aoe2war-chat-media-hd-v1')
HBA=Path('/etc/postgresql/16/main/pg_hba.conf')
SOURCE='3e4c50452541805742f31bd743117b0863582f60'
DOMAIN=b'AOE2WAR-WE1-HD-DIRECT-MEDIA-SQL-ONLY-V1\x00'
FILES={
 'install':('c03_hd_direct_image_install_candidate.sql','db4c80451f9bb627598105b826c45d9ee115fd462a56d08aebf5deb79ad0723c'),
 'inverse':('c03_hd_direct_image_inverse_candidate.sql','2298690e5c1c412cdd73d232c9469ee7e268c191fbaa0816e9f6340fde138baf'),
 'witness':('c03_hd_direct_media_catalog_witness.sql','29d57312178c9ea3aeaaa215fce53ad1438316465c8508ff3d2f507c34826582'),
}
HEX=re.compile(r'[0-9a-f]{64}\Z')
SPKI=bytes.fromhex('3059301306072a8648ce3d020106082a8648ce3d030107034200')
FLAGS=('financial_authorized','funding_authorized','de_mutation_authorized','hba_mutation_authorized','raw_grants_authorized','custody_authorized')
class Hold(RuntimeError): pass
def need(ok,reason):
    if not ok: raise Hold(reason)
def digest(data):return hashlib.sha256(data).hexdigest()
def canonical(obj):return json.dumps(obj,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode()
def strict(raw):
    def pairs(xs):
        d={}
        for k,v in xs:
            need(k not in d,'DUPLICATE_JSON_KEY');d[k]=v
        return d
    obj=json.loads(raw,object_pairs_hook=pairs)
    need(canonical(obj)==raw.strip(),'NONCANONICAL_JSON')
    return obj
def hex64(x):return type(x) is str and HEX.fullmatch(x) is not None
def utc(x):
    need(type(x) is str and re.fullmatch(r'\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ',x),'UTC_INVALID')
    return datetime.strptime(x,'%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc)

def secure_dir(p):
    for q in reversed((p,*p.parents)):
        s=q.lstat()
        need(stat.S_ISDIR(s.st_mode) and s.st_uid==0 and not s.st_mode&0o022,'UNTRUSTED_DIRECTORY')
def secure_file(p,limit=131072):
    secure_dir(p.parent)
    fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC|os.O_NONBLOCK)
    try:
        a=os.fstat(fd)
        need(stat.S_ISREG(a.st_mode) and a.st_uid==0 and a.st_nlink==1 and not a.st_mode&0o077 and 0<a.st_size<=limit,'UNTRUSTED_FILE')
        raw=b''
        while len(raw)<a.st_size:
            chunk=os.read(fd,a.st_size-len(raw))
            need(chunk,'SHORT_READ');raw+=chunk
        b=os.fstat(fd)
        need((a.st_dev,a.st_ino,a.st_size,a.st_mtime_ns,a.st_ctime_ns)==(b.st_dev,b.st_ino,b.st_size,b.st_mtime_ns,b.st_ctime_ns),'FILE_RACE')
        return raw
    finally:os.close(fd)

def write_once(p,raw):
    fd=os.open(p,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW|os.O_CLOEXEC,0o600)
    with os.fdopen(fd,'wb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
    fd=os.open(p.parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:os.fsync(fd)
    finally:os.close(fd)
def file_pins():return {k:v[1] for k,v in FILES.items()}

def verify_packet(raw,public,review,phase,nonce,now,verify=None):
    p=strict(raw)
    need(type(p) is dict and set(p)=={'request','signature_der_b64'},'PACKET_FIELDS')
    r=p['request']
    keys={'schema','action','phase','nonce','not_before','expires_at','host_id_sha256','database','source_commit','executor_sha256','file_sha256','hba_sha256','owner_public_sha256','hd_full_sha256','hd_invariant_sha256','de_full_sha256',*FLAGS}
    need(type(r) is dict and set(r)==keys,'REQUEST_FIELDS')
    need(r['schema']=='wolo.we1.hd-direct-media-permit.v1' and r['action']=='HD_DIRECT_MEDIA_SQL_ONLY' and r['database']=='aoe2hd_db' and r['phase']==phase and phase in ('install','inverse'),'WRONG_SCOPE')
    need(hex64(nonce) and nonce!='0'*64 and r['nonce']==nonce,'NONCE_DRIFT')
    for k in ('host_id_sha256','source_commit','executor_sha256','file_sha256','hba_sha256','owner_public_sha256'):
        need(r[k]==review[k],'REVIEW_PIN_DRIFT_'+k)
    for k in ('hd_full_sha256','hd_invariant_sha256','de_full_sha256'):need(hex64(r[k]),'BAD_CATALOG_PIN')
    need(all(r[k] is False for k in FLAGS),'FORBIDDEN_AUTHORITY')
    a,b=utc(r['not_before']),utc(r['expires_at'])
    need(timedelta(0)<b-a<=timedelta(minutes=10) and a<=now<b,'PERMIT_EXPIRED')
    need(type(public) is bytes and len(public)==65 and public[0]==4 and digest(public)==r['owner_public_sha256'],'PUBLIC_KEY_DRIFT')
    need(type(p['signature_der_b64']) is str and len(p['signature_der_b64'])<=112,'SIGNATURE_FORMAT')
    sig=base64.b64decode(p['signature_der_b64'],validate=True)
    need(64<=len(sig)<=80 and sig[0]==48,'SIGNATURE_FORMAT')
    msg=DOMAIN+canonical(r)
    if verify is not None:need(verify(msg,sig,public),'INVALID_SIGNATURE')
    else:
        with tempfile.TemporaryDirectory(prefix='media-owner-verify-') as tmp:
            d=Path(tmp)
            for n,v in [('pub',SPKI+public),('msg',msg),('sig',sig)]:
                q=d/n;q.write_bytes(v);q.chmod(0o600)
            x=subprocess.run(['/usr/bin/openssl','dgst','-sha256','-keyform','DER','-verify',str(d/'pub'),'-signature',str(d/'sig'),str(d/'msg')],capture_output=True,timeout=8)
            need(x.returncode==0 and b'Verified OK' in x.stdout,'INVALID_SIGNATURE')
    return r

def psql(data,db,readonly):
    need(db in ('aoe2hd_db','aoe2de_db') and (readonly or db=='aoe2hd_db'),'DATABASE_SCOPE')
    account=pwd.getpwnam('postgres')
    def drop():
        os.setgroups([]);os.setgid(account.pw_gid);os.setuid(account.pw_uid);os.umask(0o077)
    env={'PATH':'/usr/bin:/bin','HOME':'/var/lib/postgresql','LANG':'C','PGCONNECT_TIMEOUT':'3','PGPASSFILE':'/dev/null','PGOPTIONS':'-c search_path=pg_catalog,pg_temp'+(' -c default_transaction_read_only=on' if readonly else '')}
    argv=['/usr/bin/psql','-X','-w','-qAt','-v','ON_ERROR_STOP=1','-h','/var/run/postgresql','-p','5432','-U','postgres','-d',db]
    p=subprocess.Popen(argv,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,preexec_fn=drop,env=env,start_new_session=True)
    try:out,err=p.communicate(data,timeout=25)
    except subprocess.TimeoutExpired:
        os.killpg(p.pid,signal.SIGKILL);p.communicate();raise Hold('SQL_TIMEOUT_UNKNOWN')
    need(p.returncode==0 and len(out)<16384,'SQL_PHASE_DENIED_OR_UNKNOWN')
    return out

def parse_witness(raw,db):
    obj=json.loads(raw)
    need(type(obj) is dict and obj['database']==db and str(obj['pg_version']).startswith('16') and hex64(obj['full_sha256']) and hex64(obj['invariant_sha256']),'WITNESS_INVALID')
    need(obj['enabled_event_triggers']==0 and obj['hba_parse_errors']==0,'EVENT_TRIGGER_OR_HBA_PARSE_HOLD')
    return obj

def witness(data,db,runner=psql):
    return parse_witness(runner(b"BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY; SET LOCAL statement_timeout='5s'; SET LOCAL lock_timeout='350ms';\n"+data['witness']+b";\nROLLBACK;\n",db,True),db)

def build_transaction(data,r,original_full=None):
    phase=r['phase']
    need(phase!='inverse' or hex64(original_full),'ORIGINAL_PREIMAGE_REQUIRED')
    need(phase in ('install','inverse') and all(hex64(r[k]) for k in ('hd_full_sha256','hd_invariant_sha256')),'TRANSACTION_SCOPE')
    for k in FILES:need(digest(data[k])==FILES[k][1],'SQL_SOURCE_DRIFT_'+k)
    witness_sql=data['witness'].decode().strip().rstrip(';')
    sql=data[phase].decode()
    # Fixed reviewed transaction only. Strip its outer boundaries to bind the
    # exact signed catalog preimage and invariant in the same transaction.
    need(sql.count('\nBEGIN;\n')==1 and sql.rstrip().endswith('COMMIT;'),'SQL_WRAPPER_DRIFT')
    inner=sql.split('\nBEGIN;\n',1)[1].rsplit('COMMIT;',1)[0]
    full=r['hd_full_sha256'];inv=r['hd_invariant_sha256']
    def guard(expr,reason):
        return "DO $media_guard$ BEGIN IF ("+expr+") IS DISTINCT FROM true THEN RAISE EXCEPTION '"+reason+"'; END IF; END $media_guard$;\n"
    pre="SELECT (j->>'full_sha256'='"+full+"' AND j->>'invariant_sha256'='"+inv+"' AND (j->>'enabled_event_triggers')::int=0 AND (j->>'hba_parse_errors')::int=0) FROM ("+witness_sql+") w(j)"
    post="SELECT (j->>'invariant_sha256'='"+inv+"' AND (j->>'enabled_event_triggers')::int=0 AND (j->>'media_functions')::int="+('4' if phase=='install' else '0')+" AND (j->>'media_relations')::int="+('5' if phase=='install' else '0')+" AND j->>'text_body_md5'='"+('aa1766746cc5f1ee1235c1e6c99bd487' if phase=='install' else '29748632792ceb09d6260bbb51900dba')+"'"+(" AND j->>'full_sha256'='"+original_full+"'" if phase=='inverse' else '')+") FROM ("+witness_sql+") w(j)"
    # No retries or automatic destructive inverse on uncertain COMMIT.
    return ("BEGIN ISOLATION LEVEL SERIALIZABLE; SET LOCAL search_path=pg_catalog,pg_temp; SET LOCAL lock_timeout='350ms'; SET LOCAL statement_timeout='10s';\n"+guard(pre,'SIGNED_PREIMAGE_DRIFT')+inner+guard(post,'INVARIANT_OR_POSTIMAGE_DRIFT')+witness_sql+";\nCOMMIT;\n").encode()

def phase_state():
    need(all(x.name=='controller.lock' or re.fullmatch(r'(nonce|receipt)-[0-9a-f]{64}\.json',x.name) for x in STATE.iterdir()),'UNRECOGNIZED_STATE_EVIDENCE')
    entries=list(STATE.glob('nonce-*.json'))
    receipts=list(STATE.glob('receipt-*.json'))
    need(len(entries)==len(receipts) and len(entries)<=1,'UNKNOWN_OR_ALREADY_USED_EPOCH')
    if not entries:return 'install',None
    n=entries[0].name[6:-5]
    need(hex64(n) and receipts[0].name=='receipt-'+n+'.json','STATE_DRIFT')
    consumed=strict(secure_file(entries[0]))
    receipt=strict(secure_file(receipts[0]))
    need(receipt['status']=='INSTALLED_POSTIMAGE_PASS' and consumed['phase']=='install' and receipt['phase']=='install' and consumed['nonce']==n==receipt['nonce'] and receipt['source_commit']==SOURCE and receipt['financial_authorized'] is False and hex64(consumed['permit_sha256']) and consumed['permit_sha256']==receipt['permit_sha256'],'STATE_HOLD')
    for key in ('hd_before','hd_after','de_before','de_after'):need(type(receipt[key]) is dict,'RECEIPT_WITNESS_MISSING')
    need(receipt['hd_before']['invariant_sha256']==receipt['hd_after']['invariant_sha256'] and receipt['de_before']==receipt['de_after'],'RECEIPT_LINEAGE_DRIFT')
    return 'inverse',receipt

def live_pins():
    data={k:secure_file(CODE/name) for k,(name,h) in FILES.items()}
    need(all(digest(data[k])==h for k,(_,h) in FILES.items()),'SQL_FILE_DRIFT')
    code=secure_file(CODE/'c03_hd_direct_media_native_executor.py')
    need(Path(__file__).resolve()==CODE/'c03_hd_direct_media_native_executor.py','EXECUTOR_LOCATION')
    pub=secure_file(ROOT/'owner-p256-public-x963.bin',128)
    review=strict(secure_file(ROOT/'review.json',8192))
    # Machine ID and HBA are current native pins, not hostname guesses.
    host=Path('/etc/machine-id').read_bytes().strip()
    need(re.fullmatch(b'[0-9a-f]{32}',host),'MACHINE_ID_INVALID')
    fd=os.open(HBA,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
    try:
        st=os.fstat(fd);need(stat.S_ISREG(st.st_mode) and st.st_uid==pwd.getpwnam('postgres').pw_uid and st.st_nlink==1 and st.st_size<65536 and not st.st_mode&0o007,'HBA_FILE_DRIFT')
        hba=os.read(fd,65536);need(len(hba)==st.st_size,'HBA_SHORT_READ')
    finally:os.close(fd)
    rules=[x.split() for x in hba.decode('ascii').splitlines() if x.strip() and not x.lstrip().startswith('#')]
    expected=[['local','all','aoe2war_social_writer','reject'],['host','aoe2hd_db','aoe2war_social_writer','127.0.0.1/32','scram-sha-256'],['host','all','aoe2war_social_writer','127.0.0.1/32','reject'],['host','all','aoe2war_social_writer','::1/128','reject']]
    need(all(x in rules for x in expected),'HBA_RULE_MISSING')
    indices=[rules.index(x) for x in expected]
    need(indices[0]<next(i for i,x in enumerate(rules) if x[:3]==['local','all','all']) and indices[1]<indices[2]<next(i for i,x in enumerate(rules) if x[:4]==['host','all','all','127.0.0.1/32']) and indices[3]<next(i for i,x in enumerate(rules) if x[:4]==['host','all','all','::1/128']),'HBA_ORDER_DRIFT')
    actual={'schema':'wolo.we1.hd-direct-media-root-review.v1','source_commit':SOURCE,'executor_sha256':digest(code),'file_sha256':file_pins(),'host_id_sha256':digest(host),'hba_sha256':digest(hba),'owner_public_sha256':digest(pub)}
    need(review==actual,'ROOT_REVIEW_MISMATCH')
    return data,pub,review

def execute(phase,nonce):
    need(os.getuid()==0 and os.geteuid()==0,'ROOT_REQUIRED')
    for p in (ROOT,CODE,STATE):secure_dir(p)
    data,pub,review=live_pins()
    lock=os.open(STATE/'controller.lock',os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW|os.O_CLOEXEC,0o600)
    try:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        hd=witness(data,'aoe2hd_db');de=witness(data,'aoe2de_db')
        if phase=='preflight':return {'status':'READ_ONLY_PREFLIGHT_NOT_ADMISSION','hd':hd,'de':de,'review':review}
        expected,prior=phase_state()
        need(expected==phase and hex64(nonce),'PHASE_OR_NONCE_HOLD')
        raw=secure_file(ROOT/('permit-'+nonce+'.json'),8192)
        r=verify_packet(raw,pub,review,phase,nonce,datetime.now(timezone.utc))
        need((hd['full_sha256'],hd['invariant_sha256'],de['full_sha256'])==(r['hd_full_sha256'],r['hd_invariant_sha256'],r['de_full_sha256']),'LIVE_PREIMAGE_DRIFT')
        need(de['media_functions']==0 and de['media_relations']==0,'DE_MEDIA_SCOPE_DRIFT')
        if phase=='install':need(hd['media_functions']==0 and hd['media_relations']==0 and hd['text_body_md5']=='29748632792ceb09d6260bbb51900dba','HD_PREIMAGE_DRIFT')
        else:need(hd==prior['hd_after'] and de==prior['de_after'] and hd['media_functions']==4 and hd['media_relations']==5,'HD_POSTIMAGE_LINEAGE_DRIFT')
        txn=build_transaction(data,r,prior['hd_before']['full_sha256'] if prior else None)
        info={'phase':phase,'nonce':nonce,'permit_sha256':digest(raw)}
        write_once(STATE/('nonce-'+nonce+'.json'),canonical(info)+b'\n')
        rec={**info,'status':'UNKNOWN_NO_RETRY','source_commit':SOURCE,'financial_authorized':False}
        try:
            after=parse_witness(psql(txn,'aoe2hd_db',False),'aoe2hd_db')
            h2=witness(data,'aoe2hd_db');d2=witness(data,'aoe2de_db')
            _,_,r2=live_pins()
            need(after==h2 and h2['invariant_sha256']==hd['invariant_sha256'] and d2==de and r2==review,'POSTIMAGE_OR_CROSS_DB_DRIFT')
            rec.update(status='INSTALLED_POSTIMAGE_PASS' if phase=='install' else 'INVERSE_PREIMAGE_PASS',hd_before=hd,hd_after=h2,de_before=de,de_after=d2)
        except Exception:pass
        write_once(STATE/('receipt-'+nonce+'.json'),canonical(rec)+b'\n')
        need(rec['status']!='UNKNOWN_NO_RETRY','UNKNOWN_NO_RETRY')
        return rec
    finally:os.close(lock)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('phase',choices=('preflight','install','inverse'));p.add_argument('nonce',nargs='?',default='')
    a=p.parse_args()
    try:print(json.dumps(execute(a.phase,a.nonce),sort_keys=True))
    except Exception as e:print(json.dumps({'status':'HOLD','reason':str(e)[:120],'financial_authorized':False}));sys.exit(3)

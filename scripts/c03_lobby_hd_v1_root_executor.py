#!/usr/bin/env python3
"""Exact-source, owner-Keychain P256 signed, one-use HD-only Lobby SQL executor.

No generic SQL, root key export, financial admission, website credential, or
unrestricted user UID input. Independent source-hash installation required.
The signed-session service, not this root operator, binds human UIDs.
"""
from __future__ import annotations

import base64
import binascii
from datetime import datetime, timedelta, timezone
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
import tempfile

HEAD = '5049e148b345481a4e1a3a3ffe8625635771963e'
SQL_INSTALL = '41381fc3ab254549e7ca982d95cab4c44bd9f2782681152d73b9c468597ab434'
SQL_INVERSE = 'cc18548000ef149b19352dc3dab23b49264c24f49e27b5b1619a37a0d0d26452'
CONTRACT = 'f571d8f3a0b1982a0189ea6e512d154bf6eca32ff4044a381e243a19d73faccb'
PUBLIC_SHA = '02f2cd051de06553213dc96b9f73d53d0c530ad0a730672960a17acafc8d8b7e'
SOCIAL_INSTALLED_SHA = 'f129576f3c45bb51229e1f35e52c631dfb1f1e77abb672471141743021103120'
SOCIAL_RECEIPT = Path('/var/lib/wolo-financial-role-state/v1/chat-social-hd-v2-exact/receipt-4b683379f965d99122c2e6d4418773874e693225cb0e6403b271ad69df2ccdb1.json')
HBA_SHA = '3fecbffb683bf2bc21e8bd880b9be982d14cbe3bbf67aae08f801159d6b76789'
HBA = Path('/etc/postgresql/16/main/pg_hba.conf')
STAGE = Path('/home/tony/we1-lobby-hd-v1-signed-stage-20261120')
ROOT = Path('/etc/wolo-financial-lobby-hd-v1')
LIB = Path('/usr/local/libexec/wolo-financial-lobby-hd-v1')
STATE = Path('/var/lib/wolo-financial-role-state/v1/lobby-hd-v1-exact')
PUBLIC = ROOT / 'owner-lobby-hd-v1-p256-public-x963.bin'
INSTALL = LIB / 'c03_lobby_hd_v1_install_candidate.sql'
INVERSE = LIB / 'c03_lobby_hd_v1_inverse_candidate.sql'
DOMAIN = b'AOE2WAR-WE1-LOBBY-HD-V1-SQL-ONLY-V1\x00'
SCHEMA = 'wolo.we1.lobby-hd-v1-exact-request.v1'
ACTION = 'LOBBY_HD_V1_SQL_ONLY'
PACKET_SCHEMA = 'wolo.we1.lobby-hd-v1-signed-packet.v1'
PACKET = STAGE / 'signed-one-use-lobby-hd-v1.json'
PG = Path('/usr/lib/postgresql/16/bin/psql')
HEX64 = re.compile(r'[0-9a-f]{64}\Z')

# Captures raw NULL vs explicit legacy relacl and column attacl representations.
# Does not read raw guest-session or financial row data.
ACL_SQL = """
SELECT 'R|'||n.nspname||'|'||c.relname||'|'||
       pg_catalog.pg_get_userbyid(c.relowner)||'|'||
       CASE WHEN c.relacl IS NULL THEN 'RAW_NULL' ELSE c.relacl::text END
FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
WHERE n.nspname='public' AND c.relname IN
('users','users_id_seq','chat_rooms','chat_rooms_id_seq',
 'chat_messages','chat_messages_id_seq','chat_message_guest_reactions','bet_wagers')
UNION ALL
SELECT 'C|'||n.nspname||'|'||c.relname||'|'||a.attname||'|'||
       CASE WHEN a.attacl IS NULL THEN 'RAW_NULL' ELSE a.attacl::text END
FROM pg_catalog.pg_attribute a
JOIN pg_catalog.pg_class c ON c.oid=a.attrelid
JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
WHERE n.nspname='public' AND c.relname IN
('users','chat_rooms','chat_messages','chat_message_guest_reactions','bet_wagers')
AND a.attnum>0 AND NOT a.attisdropped
ORDER BY 1;
"""
POST_SQL = """
DO $post$
BEGIN
 IF to_regnamespace('aoe2war_lobby_hd_v1') IS NULL OR
    to_regrole('aoe2war_lobby_exec_v1') IS NULL OR
    to_regrole('aoe2war_social_writer') IS NULL OR
    to_regprocedure('aoe2war_lobby_hd_v1.post_text(text,text,text)') IS NULL OR
    to_regprocedure('aoe2war_lobby_hd_v1.leaf_append_lobby(integer,integer,text)') IS NULL OR
    EXISTS (SELECT 1 FROM pg_catalog.pg_roles
      WHERE rolname='aoe2war_lobby_exec_v1'
        AND (rolcanlogin OR rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication OR rolbypassrls)) OR
    (SELECT pg_catalog.pg_get_userbyid(p.proowner) FROM pg_catalog.pg_proc p
      WHERE p.oid='aoe2war_lobby_hd_v1.post_text(text,text,text)'::regprocedure)
          <> 'aoe2war_lobby_exec_v1' OR
    has_table_privilege('aoe2war_social_writer','public.chat_messages','INSERT') OR
    has_table_privilege('aoe2war_social_writer','public.chat_message_guest_reactions','SELECT') OR
    has_table_privilege('aoe2war_social_writer','public.bet_wagers','INSERT') OR
    has_function_privilege('aoe2war_social_writer',
      'aoe2war_lobby_hd_v1.leaf_append_lobby(integer,integer,text)','EXECUTE') OR
    NOT has_function_privilege('aoe2war_social_writer',
      'aoe2war_lobby_hd_v1.post_text(text,text,text)','EXECUTE')
 THEN RAISE EXCEPTION 'LOBBY_REAL_POSTIMAGE_DENIED'; END IF;
END $post$;
SELECT 'PASS_WE1_PRODUCTION_LOBBY_POSTIMAGE';
"""
INVERSE_POST_SQL = """
DO $p$
BEGIN
 IF to_regnamespace('aoe2war_lobby_hd_v1') IS NOT NULL OR
    to_regrole('aoe2war_lobby_exec_v1') IS NOT NULL OR
    to_regrole('aoe2war_social_writer') IS NULL
 THEN RAISE EXCEPTION 'LOBBY_INVERSE_PREIMAGE_DENIED'; END IF;
END $p$;
SELECT 'PASS_WE1_PRODUCTION_LOBBY_INVERSE';
"""

class Hold(RuntimeError): pass

def need(condition, reason):
    if not condition: raise Hold(reason)

def sha(raw): return hashlib.sha256(raw).hexdigest()
def canonical(obj): return json.dumps(obj,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode()

def parse(raw):
    def unique(items):
        result={}
        for key,val in items:
            need(key not in result,'DUPLICATE_JSON_KEY')
            result[key]=val
        return result
    value=json.loads(raw,object_pairs_hook=unique)
    need(canonical(value)==raw.strip(),'JSON_NOT_CANONICAL')
    return value

def file_bytes(path,uid,limit=32768):
    x=path.lstat()
    need(stat.S_ISREG(x.st_mode) and x.st_uid==uid and
         stat.S_IMODE(x.st_mode)==0o600 and x.st_nlink==1 and 0<x.st_size<=limit,
         'UNTRUSTED_FILE_'+path.name)
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
    try:
        y=os.fstat(fd)
        need((x.st_dev,x.st_ino,x.st_size)==(y.st_dev,y.st_ino,y.st_size),
             'FILE_RACE')
        raw=os.read(fd,limit+1)
        need(len(raw)==x.st_size,'FILE_SIZE_RACE')
        return raw
    finally: os.close(fd)

def trusted_dir(path,owner):
    x=path.lstat()
    need(stat.S_ISDIR(x.st_mode) and not stat.S_ISLNK(x.st_mode) and
         x.st_uid==owner and stat.S_IMODE(x.st_mode)==0o700,
         'UNTRUSTED_DIR_'+path.name)

def once(parent,name,data):
    need(bool(re.fullmatch('[A-Za-z0-9_.-]{1,150}',name)),'OUTPUT_NAME_DENIED')
    fd=os.open(parent/name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    try:
        with os.fdopen(fd,'wb',closefd=False) as f:
            f.write(data);f.flush();os.fsync(fd)
    finally:os.close(fd)
    dfd=os.open(parent,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(dfd)
    finally:os.close(dfd)

def utc(value):
    need(type(value) is str and re.fullmatch(r'\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ',value),'UNSAFE_TIME')
    return datetime.strptime(value,'%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc)

def signed(raw,public,phase,now=None):
    item=parse(raw)
    need(type(item) is dict and set(item)=={'schema','request','signature_der_b64'}
         and item['schema']==PACKET_SCHEMA,'UNEXPECTED_PACKET_FIELDS')
    req=item['request']
    expected={'schema':SCHEMA,'action':ACTION,'phase':phase,'source_head':HEAD,
       'host':'HEL1','database':'aoe2hd_db','owner_public_sha256':PUBLIC_SHA,
       'root_executor_sha256':sha(Path(__file__).read_bytes()),
       'sql_install_sha256':SQL_INSTALL,'sql_inverse_sha256':SQL_INVERSE,
       'source_contract_sha256':CONTRACT,'social_installed_receipt_sha256':SOCIAL_INSTALLED_SHA,
       'hba_sha256':HBA_SHA,'financial_authorized':False,'funding_authorized':False,
       'de_database_authorized':False,'raw_event_grants_authorized':False,
       'hba_mutation_authorized':False}
    need(type(req) is dict and set(req)==set(expected)|{'nonce','not_before','expires_at'},
         'SIGNATURE_REQUEST_FIELDS')
    for key,value in expected.items(): need(req[key]==value,'SIGNED_SCOPE_DRIFT_'+key)
    nonce=req['nonce']
    need(type(nonce) is str and HEX64.fullmatch(nonce) and nonce!='0'*64,
         'SIGNED_NONCE_INVALID')
    start,end=utc(req['not_before']),utc(req['expires_at'])
    clock=now or datetime.now(timezone.utc)
    need(timedelta(0)<end-start<=timedelta(seconds=900) and start<=clock<end,
         'SIGNED_PERMIT_EXPIRED')
    try: der=base64.b64decode(item['signature_der_b64'],validate=True)
    except (ValueError,binascii.Error): raise Hold('SIGNATURE_ENCODING')
    need(64<=len(der)<=80 and der[0]==0x30,'SIGNATURE_DER_INVALID')
    need(len(public)==65 and public[0]==4 and sha(public)==PUBLIC_SHA,'PUBLIC_KEY_CHANGED')
    spki=bytes.fromhex('3059301306072a8648ce3d020106082a8648ce3d030107034200')
    with tempfile.TemporaryDirectory(prefix='lobby-owner-verify-') as td:
        d=Path(td)
        for name,data in [('public.der',spki+public),('message',DOMAIN+canonical(req)),('signature.der',der)]:
            p=d/name;p.write_bytes(data);p.chmod(0o600)
        c=subprocess.run(['/usr/bin/openssl','dgst','-sha256','-keyform','DER',
          '-verify',str(d/'public.der'),'-signature',str(d/'signature.der'),
          str(d/'message')],capture_output=True,timeout=10)
        need(c.returncode==0 and b'Verified OK' in c.stdout,
             'LOBBY_OWNER_SIGNATURE_INVALID')
    return req

def psql(sql,timeout=50):
    need(PG.is_file(),'PG16_EXECUTABLE_ABSENT')
    postgres=pwd.getpwnam('postgres')
    def drop():
        os.setgroups([])
        os.setgid(postgres.pw_gid)
        os.setuid(postgres.pw_uid)
    p=subprocess.run([str(PG),'-X','-q','-A','-t','-v','ON_ERROR_STOP=1',
         '-h','/var/run/postgresql','-p','5432','-U','postgres','-d','aoe2hd_db'],
         input=sql,text=True,capture_output=True,preexec_fn=drop,
         env={'PATH':'/usr/bin:/bin','PGCONNECT_TIMEOUT':'5',
              'PGAPPNAME':'we1-exact-signed-lobby-sql-v1'},timeout=timeout)
    need(p.returncode==0,'PINNED_SQL_REJECTED_'+sha((p.stderr or '').encode())[:16])
    return p.stdout

def confirm():
    need(os.getuid()==os.geteuid()==0,'ROOT_REQUIRED')
    need(Path(__file__).resolve()==LIB/'c03_lobby_hd_v1_root_executor.py',
         'ROOT_SOURCE_PATH_DRIFT')
    for d,owner in [(STAGE,1000),(ROOT,0),(LIB,0),(STATE,0)]:trusted_dir(d,owner)
    need(sha(file_bytes(PUBLIC,0,128))==PUBLIC_SHA,'ROOT_OWNER_PUBLIC_DRIFT')
    for path,expected in [(INSTALL,SQL_INSTALL),(INVERSE,SQL_INVERSE),
                          (LIB/'c03_lobby_hd_v1_reconciliation_contract.json',CONTRACT),
                          (SOCIAL_RECEIPT,SOCIAL_INSTALLED_SHA)]:
        need(sha(file_bytes(path,0,32768))==expected,'PINNED_SOURCE_OR_SOCIAL_DRIFT_'+path.name)
    need(sha(HBA.read_bytes())==HBA_SHA,'HBA_SHA_CHANGED')
    social=parse(file_bytes(SOCIAL_RECEIPT,0))
    need(social['status']=='INSTALLED_POSTIMAGE_PASS' and social['sequence']==3 and
         social['financial_authorized'] is False and
         social['hba_sha256']==HBA_SHA,'SOCIAL_PRODUCTION_NOT_READY')
    need(psql("SELECT current_database();").strip()=='aoe2hd_db',
         'WRONG_PRODUCTION_DATABASE')
    tcp=subprocess.run(['/usr/bin/ss','-lnt'],capture_output=True,text=True,timeout=6)
    need(tcp.returncode==0 and not re.search(r':809[2-5](?:\s|$)',tcp.stdout),
         'FINANCIAL_PORTS_ACTIVE')

def phase_expected(phase):
    transitions=sorted(STATE.glob('transition-*.json'))
    if phase=='install':
        need(not transitions and not list(STATE.glob('receipt-*.json')),
             'LOBBY_INSTALL_ALREADY_ATTEMPTED')
        return 1,'0'*64
    need(len(transitions)==1 and bool(list(STATE.glob('nonce-*.consumed'))),
         'LOBBY_INVERSE_JOURNAL_INCOMPLETE')
    receipt=list(STATE.glob('receipt-*.json'))
    need(len(receipt)==1,'LOBBY_INSTALL_RECEIPT_MISSING')
    prior=file_bytes(receipt[0],0,8192)
    data=parse(prior)
    need(data['status']=='INSTALLED_LOBBY_POSTIMAGE_PASS' and data['sequence']==1,
         'LOBBY_NOT_INSTALLED')
    return 2,sha(prior)

def execute(phase):
    need(phase in ('install','inverse'),'UNAUTHORIZED_PHASE')
    confirm()
    sql_path,sql_sha = (INSTALL,SQL_INSTALL) if phase=='install' else (INVERSE,SQL_INVERSE)
    sql=file_bytes(sql_path,0,32768)
    need(sha(sql)==sql_sha,'SQL_SOURCE_DRIFT')
    packet=file_bytes(PACKET,1000,8192)
    req=signed(packet,file_bytes(PUBLIC,0,128),phase)
    nonce=req['nonce']
    fd=os.open(STATE/'controller.lock',os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
    try:
        fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        sequence,previous=phase_expected(phase)
        before=psql(ACL_SQL)
        before_sha=sha(before.encode())
        need(sha(HBA.read_bytes())==HBA_SHA,'HBA_DRIFT_PRE_SQL')
        once(STATE,f'transition-{sequence:08d}-{nonce}.json',
             canonical({'phase':phase,'sequence':sequence,'nonce':nonce,
                'previous_receipt_sha256':previous,'permit_sha256':sha(packet)})+b'\n')
        once(STATE,f'nonce-{nonce}.consumed',
             canonical({'nonce':nonce,'phase':phase,'permit_sha256':sha(packet)})+b'\n')
        evidence={'schema':'wolo.we1.lobby-hd-v1-root-execution-receipt.v1',
            'phase':phase,'sequence':sequence,'nonce':nonce,'permit_sha256':sha(packet),
            'source_head':HEAD,'executor_sha256':sha(Path(__file__).read_bytes()),
            'sql_sha256':sql_sha,'social_installed_receipt_sha256':SOCIAL_INSTALLED_SHA,
            'previous_receipt_sha256':previous,'hba_sha256':HBA_SHA,
            'acl_before_sha256':before_sha,'financial_authorized':False,
            'funding_authorized':False,'de_database_authorized':False,
            'utc':datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
            'status':'UNKNOWN_AFTER_NONCE_CONSUMPTION'}
        try:
            psql(sql.decode(),timeout=55)
            after=psql(ACL_SQL)
            evidence['acl_after_sha256']=sha(after.encode())
            need(after==before,'LEGACY_ACL_OR_COLUMN_DRIFT')
            test=psql(POST_SQL if phase=='install' else INVERSE_POST_SQL)
            require='PASS_WE1_PRODUCTION_LOBBY_POSTIMAGE' if phase=='install' else 'PASS_WE1_PRODUCTION_LOBBY_INVERSE'
            need(test.strip()==require,'PRODUCTION_POSTIMAGE_DENIED')
            need(sha(HBA.read_bytes())==HBA_SHA,'HBA_CHANGED_POST_LOBBY')
            evidence['status']='INSTALLED_LOBBY_POSTIMAGE_PASS' if phase=='install' else 'INVERSE_LOBBY_PREIMAGE_PASS'
            evidence['postimage_result']=require
        except Exception as e:
            evidence['status']='HOLD_LOBBY_POSTIMAGE_NO_RETRY'
            evidence['denial_reason']=str(e)[:110]
        raw=canonical(evidence)+b'\n'
        once(STATE,f'receipt-{nonce}.json',raw)
        need(evidence['status'] in ('INSTALLED_LOBBY_POSTIMAGE_PASS','INVERSE_LOBBY_PREIMAGE_PASS'),
             evidence['status'])
        return {'status':evidence['status'],'phase':phase,'sequence':sequence,
                'nonce':nonce,'receipt_sha256':sha(raw)}
    finally:os.close(fd)

def main():
    try:
        need(len(sys.argv)==2 and sys.argv[1] in ('install','inverse'),'INVALID_ARGS')
        result=execute(sys.argv[1])
        print(json.dumps(result,sort_keys=True));return 0
    except (Hold,OSError,ValueError,subprocess.SubprocessError,KeyError) as e:
        print(json.dumps({'status':'HOLD_LOBBY_HD_V1_EXACT_ROOT','reason':str(e)[:180],
           'financial_authorized':False},sort_keys=True));return 3

if __name__=='__main__':sys.exit(main())

#!/usr/bin/env python3
"""Build SOURCE-ONLY paired helper enrollment/inverse from qualified metadata.
No connection, execution, credential, funding or listener entry point exists.
Every generated script refuses before DDL until a new exact admission exists.
"""
from pathlib import Path
import argparse,hashlib,json

PINS={
 '20261017_012000_war_satchel_funded_ledger_foundation/migration.sql':'b2521d9d00f1c70e91255e9077e33b4c5dff1d9b',
 '20261019_010000_war_satchel_wager_authority/migration.sql':'81bdb156f10469d42ad19644aa9ec5975e827f48',
 '20261108_212700_c02_native_forward_only_returns/migration.sql':'6ee938f20b7332c17114690ff28900b1dc4fe3eb'}
MATCHER_SHA='13f07b31836f4bbba6bde733dddb27d5a71c3bb0684868a5fefe4ce72b9b10a4'
# Derived from verified migration compilation plus the test's declared owner
# setup. This is not a production owner policy. New profiles require source
# review of their independently qualified structural AND owner provenance.
QUALIFIED_ORACLES={'6fe4a234578a4da0b84e7250901ae045f98d85297afbb80abc9eead9abed2d21':'ISOLATED_FIXTURE_ONLY'}
ROLE='c02_row_lock';WORKER='c02_journal_worker'
READ={
 'war_satchel_wager_authorizations':['operation_id','reservation_id','owner_user_id'],
 'war_satchel_wager_broadcasts':['operation_id','tx_hash'],
 'war_satchel_funded_reservations':['id','ticket_id','status','owner_user_id','ticket_request_id','amount_uwolo','tx_hash']}
IDENT={t:('id' if t.endswith('reservations') else 'operation_id') for t in READ}
STATE_SQL=Path(__file__).with_name('c02_helper_history_state.sql').read_text()
IDENTITY_SQL="""SELECT jsonb_build_object(
 'role',(SELECT to_jsonb(r) FROM pg_roles r WHERE rolname='c02_row_lock'),
 'schema',(SELECT to_jsonb(n) FROM pg_namespace n WHERE nspname='c02_internal'),
 'helper',(SELECT to_jsonb(p) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
 WHERE n.nspname='c02_internal' AND p.proname='matches_original_funding'
 AND p.oid='c02_internal.matches_original_funding(character varying,integer,character varying,integer,bigint)'::regprocedure))"""
HOLD="""DO $c02source$ BEGIN
 RAISE EXCEPTION 'HOLD:C02_HELPER_ENROLLMENT_REQUIRES_EXACT_OWNER_SOURCE_AND_WRITER_EXCLUSION' USING ERRCODE='42501';
END $c02source$;
"""
def sha(raw):return hashlib.sha256(raw).hexdigest()
def git_blob(raw):return hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()
def q(s):return "'"+s.replace("'","''")+"'"
def ident(s):return '"'+s.replace('"','""')+'"'
def jsql(value):return q(json.dumps(value,sort_keys=True,separators=(',',':')))+'::jsonb'
def verify_sources(migrations,matcher):
 data={name:(Path(migrations)/name).read_bytes() for name in PINS}
 for name,pin in PINS.items():
  if git_blob(data[name])!=pin:raise ValueError('HISTORICAL_BLOB_DRIFT:'+name)
 raw=Path(matcher).read_bytes()
 if sha(raw)!=MATCHER_SHA:raise ValueError('MATCHER_SOURCE_DRIFT')
 text=raw.decode();helper=text[text.index('CREATE FUNCTION c02_internal.matches_original_funding'):text.index('-- No financial writer fence')]
 native=data[next(n for n in data if 'native_forward' in n)].decode()
 original=native[native.index('CREATE FUNCTION war_satchel_native_source_admission()'):native.index('CREATE TRIGGER c02_original_funding_bound')]
 return data,helper,original
def role_guard():
 return """
IF NOT EXISTS(SELECT 1 FROM pg_roles WHERE rolname='c02_row_lock'
 AND NOT rolcanlogin AND NOT rolinherit AND NOT rolsuper AND NOT rolcreatedb
 AND NOT rolcreaterole AND NOT rolreplication AND NOT rolbypassrls
 AND rolconnlimit=-1 AND rolvaliduntil IS NULL)
 OR EXISTS(SELECT 1 FROM pg_authid WHERE rolname='c02_row_lock' AND rolpassword IS NOT NULL)
 OR EXISTS(SELECT 1 FROM pg_auth_members WHERE 'c02_row_lock'::regrole IN(roleid,member,grantor))
 OR EXISTS(SELECT 1 FROM pg_db_role_setting WHERE setrole='c02_row_lock'::regrole)
 OR EXISTS(SELECT 1 FROM pg_default_acl WHERE defaclrole='c02_row_lock'::regrole)
THEN RAISE EXCEPTION 'C02_NEW_ROLE_AUTHORITY_DRIFT' USING ERRCODE='42501'; END IF;
"""
def generate(preimage,oracle,helper,original,postimage=None):
 # SQL literals sit inside fixed DO bodies. Never let captured metadata close
 # one of those outer dollar quotes, even though ordinary quotes are escaped.
 encoded=json.dumps([preimage,postimage],sort_keys=True)
 if any(tag in encoded for tag in ['$pre$','$post$','$inversepre$','$original$','$finalrole$']):raise ValueError('CAPTURE_CONTAINS_RESERVED_SQL_DELIMITER')
 if preimage.get('inheritance'):raise ValueError('UNADMITTED_INHERITANCE')
 if preimage.get('policies') or preimage.get('rules'):raise ValueError('UNADMITTED_POLICY_OR_RULE')
 if oracle.get('schema')!='wolo.c02.helper-historical-oracle.v1' or oracle.get('historical_blobs')!=PINS:raise ValueError('HISTORICAL_ORACLE_SOURCE_NOT_QUALIFIED')
 if sha(json.dumps(oracle,sort_keys=True,separators=(',',':')).encode()) not in QUALIFIED_ORACLES:raise ValueError('HISTORICAL_ORACLE_NOT_SOURCE_PINNED')
 if preimage['owners']!=oracle['owners']:raise ValueError('HISTORICAL_OWNER_NOT_ORIGINAL')
 if preimage['shape']!=oracle['shape']:raise ValueError('HISTORICAL_SHAPE_NOT_ORIGINAL')
 if set(preimage['owners'])!=set(READ):raise ValueError('HISTORICAL_TARGETS_NOT_EXACT')
 if any(a['attacl']=='{}' for a in preimage['attributes']):raise ValueError('EXPLICIT_EMPTY_COLUMN_ACL_NOT_REVERSIBLE')
 worker=preimage['worker']
 if not worker or worker['rolname']!=WORKER or any(worker[k] for k in ['rolsuper','rolcreatedb','rolcreaterole','rolreplication','rolbypassrls','rolinherit']):raise ValueError('WORKER_AUTHORITY_NOT_RESTRICTED')
 rels={r['relname']:r for r in preimage['relations'] if r['relname'] in READ}
 attrs={(a['attrelid'],a['attname']):a for a in preimage['attributes']}
 grant_rows=[];commands=[];revokes=[];allowed=[]
 for table,columns in READ.items():
  r=rels[table];owner=preimage['owners'][table]
  if owner in [ROLE,WORKER]:raise ValueError('HISTORICAL_OWNER_NOT_SEPARATE')
  if r['relkind']!='r' or r['relrowsecurity'] or r['relforcerowsecurity'] or r['relispartition']:raise ValueError('UNADMITTED_RELATION_KIND_OR_RLS')
  for col in columns:
   a=attrs[(r['oid'],col)];grant_rows.append([r['oid'],a['attnum'],r['relowner'],'SELECT',False]);allowed.append([r['oid'],a['attnum']])
  a=attrs[(r['oid'],IDENT[table])]
  if a['attidentity'] or a['attgenerated'] or a['atthasdef']:raise ValueError('IDENTIFIER_HAS_SEQUENCE_OR_GENERATION')
  grant_rows.append([r['oid'],a['attnum'],r['relowner'],'UPDATE',False])
  selected=','.join(map(ident,columns));target='public.'+ident(table)
  commands.append(f'SET LOCAL ROLE {ident(owner)};\nGRANT SELECT({selected}), UPDATE({ident(IDENT[table])}) ON {target} TO c02_row_lock;\nRESET ROLE;')
  revokes.append(f'SET LOCAL ROLE {ident(owner)};\nREVOKE SELECT({selected}), UPDATE({ident(IDENT[table])}) ON {target} FROM c02_row_lock;\nRESET ROLE;')
 grant_rows.sort(key=lambda r:(r[0],r[1],r[3]))
 expected=jsql(preimage)
 original_body=original.split('$native_source$')[1]
 original_wrapper="""IF NOT EXISTS(SELECT 1 FROM pg_proc WHERE oid='public.war_satchel_native_source_admission()'::regprocedure
 AND NOT prosecdef AND prosrc="""+q(original_body)+""" AND proconfig=ARRAY['search_path=pg_catalog, public'])
 THEN RAISE EXCEPTION 'C02_RESTORE_ORIGINAL_WRAPPER_FIRST' USING ERRCODE='42501'; END IF;\n"""
 exact_grants="""IF (SELECT COALESCE(jsonb_agg(jsonb_build_array(a.attrelid,a.attnum,x.grantor,x.privilege_type,x.is_grantable) ORDER BY a.attrelid,a.attnum,x.privilege_type),'[]'::jsonb)
 FROM pg_attribute a CROSS JOIN LATERAL aclexplode(a.attacl) x
 WHERE x.grantee='c02_row_lock'::regrole) IS DISTINCT FROM """+jsql(grant_rows)+"""
 THEN RAISE EXCEPTION 'C02_COLUMN_GRANTS_OR_GRANTORS_NOT_EXACT' USING ERRCODE='42501'; END IF;\n"""
 depend_guard="""IF EXISTS(SELECT 1 FROM pg_shdepend d WHERE d.refclassid='pg_authid'::regclass AND d.refobjid='c02_row_lock'::regrole
 AND NOT(d.dbid=(SELECT oid FROM pg_database WHERE datname=current_database()) AND (
 (d.classid='pg_class'::regclass AND d.deptype='a' AND jsonb_build_array(d.objid,d.objsubid) IN(SELECT value FROM jsonb_array_elements("""+jsql(allowed)+""")))
 OR (d.classid='pg_namespace'::regclass AND d.objid='c02_internal'::regnamespace AND d.objsubid=0 AND d.deptype='o')
 OR (d.classid='pg_proc'::regclass AND d.objid='c02_internal.matches_original_funding(character varying,integer,character varying,integer,bigint)'::regprocedure AND d.objsubid=0 AND d.deptype='o'))))
 THEN RAISE EXCEPTION 'C02_FOREIGN_ROLE_DEPENDENCY' USING ERRCODE='42501'; END IF;
IF EXISTS(SELECT 1 FROM pg_depend WHERE refclassid='pg_namespace'::regclass AND refobjid='c02_internal'::regnamespace
 AND NOT(classid='pg_proc'::regclass AND objid='c02_internal.matches_original_funding(character varying,integer,character varying,integer,bigint)'::regprocedure))
 THEN RAISE EXCEPTION 'C02_FOREIGN_SCHEMA_OBJECT' USING ERRCODE='42501'; END IF;\n"""
 helper_body=helper.split('$F$')[1]
 helper_guard="""IF NOT EXISTS(SELECT 1 FROM pg_proc WHERE oid='c02_internal.matches_original_funding(character varying,integer,character varying,integer,bigint)'::regprocedure
 AND proowner='c02_row_lock'::regrole AND prosecdef AND prosrc="""+q(helper_body)+"""
 AND proargnames=ARRAY['p_operation_id','p_owner','p_hash','p_ticket','p_amount']
 AND proconfig=ARRAY['search_path=pg_catalog'] AND prolang=(SELECT oid FROM pg_language WHERE lanname='plpgsql')
 AND prorettype='boolean'::regtype AND NOT proretset AND prokind='f' AND pronargs=5
 AND pronargdefaults=0 AND proargdefaults IS NULL AND proargmodes IS NULL AND provariadic=0
 AND NOT proisstrict AND NOT proleakproof AND provolatile='v' AND proparallel='u' AND prosupport=0::oid)
 THEN RAISE EXCEPTION 'C02_HELPER_DEFINITION_DRIFT' USING ERRCODE='42501'; END IF;
IF (SELECT nspowner FROM pg_namespace WHERE nspname='c02_internal')<>'c02_row_lock'::regrole
 OR (SELECT COALESCE(jsonb_agg(jsonb_build_array(x.grantor,x.grantee,x.privilege_type,x.is_grantable) ORDER BY x.grantee,x.privilege_type),'[]'::jsonb)
 FROM pg_namespace n CROSS JOIN LATERAL aclexplode(COALESCE(n.nspacl,acldefault('n',n.nspowner))) x WHERE n.nspname='c02_internal')
 IS DISTINCT FROM (SELECT jsonb_agg(value ORDER BY (value->>1)::oid,value->>2) FROM jsonb_array_elements(jsonb_build_array(
 jsonb_build_array('c02_row_lock'::regrole::oid,'c02_row_lock'::regrole::oid,'CREATE',false),
 jsonb_build_array('c02_row_lock'::regrole::oid,'c02_row_lock'::regrole::oid,'USAGE',false),
 jsonb_build_array('c02_row_lock'::regrole::oid,'c02_journal_worker'::regrole::oid,'USAGE',false))))
 THEN RAISE EXCEPTION 'C02_PRIVATE_SCHEMA_AUTHORITY_DRIFT' USING ERRCODE='42501'; END IF;
IF (SELECT COALESCE(jsonb_agg(jsonb_build_array(x.grantor,x.grantee,x.privilege_type,x.is_grantable) ORDER BY x.grantee,x.privilege_type),'[]'::jsonb)
 FROM pg_proc p CROSS JOIN LATERAL aclexplode(COALESCE(p.proacl,acldefault('f',p.proowner))) x
 WHERE p.oid='c02_internal.matches_original_funding(character varying,integer,character varying,integer,bigint)'::regprocedure)
 IS DISTINCT FROM (SELECT jsonb_agg(value ORDER BY (value->>1)::oid,value->>2) FROM jsonb_array_elements(jsonb_build_array(
 jsonb_build_array('c02_row_lock'::regrole::oid,'c02_row_lock'::regrole::oid,'EXECUTE',false),
 jsonb_build_array('c02_row_lock'::regrole::oid,'c02_journal_worker'::regrole::oid,'EXECUTE',false))))
 THEN RAISE EXCEPTION 'C02_PRIVATE_FUNCTION_AUTHORITY_DRIFT' USING ERRCODE='42501'; END IF;\n"""
 prefix="""-- SOURCE ONLY. Production admission, owner permit and durable writer/DDL
-- exclusion are separate. No CASCADE, DROP OWNED, sequence/table-level grant,
-- historical ownership change, financial DML, worker-role mutation or listeners.
BEGIN;
SET LOCAL search_path=pg_catalog;
SET LOCAL standard_conforming_strings=on;
SET LOCAL statement_timeout='10s';
SET LOCAL lock_timeout='300ms';
"""+HOLD+"""DO $operator$ BEGIN
IF session_user<>'postgres' OR current_user<>session_user
 OR NOT EXISTS(SELECT 1 FROM pg_roles WHERE rolname=session_user AND rolsuper)
THEN RAISE EXCEPTION 'C02_ROOT_OPERATOR_REQUIRED' USING ERRCODE='42501'; END IF;
END $operator$;
"""+STATE_SQL+'\n'
 untouched="IF pg_temp.c02_history_state(NULL) IS DISTINCT FROM "+expected+" THEN RAISE EXCEPTION 'C02_HISTORICAL_PREIMAGE_CHANGED' USING ERRCODE='42501'; END IF;\n"
 normalized="IF pg_temp.c02_history_state('c02_row_lock'::regrole) IS DISTINCT FROM "+expected+" THEN RAISE EXCEPTION 'C02_HISTORICAL_PREIMAGE_CHANGED' USING ERRCODE='42501'; END IF;\n"
 install=prefix+"DO $pre$ BEGIN\n"+untouched+original_wrapper+"""IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='c02_row_lock')
 OR EXISTS(SELECT 1 FROM pg_namespace WHERE nspname='c02_internal')
 THEN RAISE EXCEPTION 'C02_NEW_OWNER_SCHEMA_MUST_BE_ABSENT' USING ERRCODE='42501'; END IF;
IF EXISTS(SELECT 1 FROM pg_attribute a WHERE a.attrelid IN(SELECT oid FROM pg_class WHERE relname IN('war_satchel_wager_authorizations','war_satchel_wager_broadcasts','war_satchel_funded_reservations') AND relnamespace='public'::regnamespace) AND a.attacl='{}'::aclitem[])
 THEN RAISE EXCEPTION 'C02_EXPLICIT_EMPTY_COLUMN_ACL' USING ERRCODE='42501'; END IF;
IF EXISTS(SELECT 1 FROM pg_depend WHERE classid='pg_class'::regclass AND refclassid='pg_class'::regclass
 AND refobjid IN(SELECT oid FROM pg_class WHERE relname IN('war_satchel_wager_authorizations','war_satchel_wager_broadcasts','war_satchel_funded_reservations') AND relnamespace='public'::regnamespace)
 AND deptype IN('a','i') AND objid IN(SELECT oid FROM pg_class WHERE relkind='S'))
 THEN RAISE EXCEPTION 'C02_UNEXPECTED_OWNED_SEQUENCE' USING ERRCODE='42501'; END IF;
END $pre$;
CREATE ROLE c02_row_lock NOLOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
DO $usage$ BEGIN IF NOT has_schema_privilege('c02_row_lock','public','USAGE') THEN RAISE EXCEPTION 'C02_EXISTING_PUBLIC_SCHEMA_USAGE_REQUIRED' USING ERRCODE='42501'; END IF; END $usage$;
CREATE SCHEMA c02_internal AUTHORIZATION c02_row_lock;
"""+'\n'.join(commands)+"\nSET LOCAL ROLE c02_row_lock;\nREVOKE ALL ON SCHEMA c02_internal FROM PUBLIC;\nGRANT USAGE ON SCHEMA c02_internal TO c02_journal_worker;\n"+helper+"\nRESET ROLE;\nDO $post$ BEGIN\n"+role_guard()+helper_guard+exact_grants+depend_guard+normalized+"END $post$;\nCOMMIT;\n"
 if postimage is None:
  identity_guard="RAISE EXCEPTION 'HOLD:C02_ENROLLMENT_POSTIMAGE_REQUIRED' USING ERRCODE='42501';\n"
 else:
  if not all(postimage.get(k) for k in ['role','schema','helper']):raise ValueError('ENROLLED_IDENTITY_INCOMPLETE')
  if postimage['role']['rolname']!=ROLE or postimage['schema']['nspname']!='c02_internal' or postimage['helper']['proname']!='matches_original_funding':raise ValueError('ENROLLED_IDENTITY_SCOPE')
  identity_guard='IF ('+IDENTITY_SQL+') IS DISTINCT FROM '+jsql(postimage)+" THEN RAISE EXCEPTION 'C02_ENROLLED_IDENTITY_CHANGED' USING ERRCODE='42501'; END IF;\n"
 inverse=prefix+"DO $inversepre$ BEGIN\n"+role_guard()+original_wrapper+helper_guard+identity_guard+exact_grants+depend_guard+normalized+"END $inversepre$;\nDROP FUNCTION c02_internal.matches_original_funding(varchar,integer,varchar,integer,bigint) RESTRICT;\nDROP SCHEMA c02_internal RESTRICT;\n"+'\n'.join(revokes)+"\nDO $original$ BEGIN\n"+untouched+"END $original$;\nDO $finalrole$ BEGIN\n"+role_guard()+"IF EXISTS(SELECT 1 FROM pg_shdepend WHERE refclassid='pg_authid'::regclass AND refobjid='c02_row_lock'::regrole) THEN RAISE EXCEPTION 'C02_ROLE_DEPENDENCY_REMAINS' USING ERRCODE='42501'; END IF;\nEND $finalrole$;\nDROP ROLE c02_row_lock;\nCOMMIT;\n"
 return install,inverse

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--migrations',required=True,type=Path);p.add_argument('--matcher',required=True,type=Path);p.add_argument('--preimage',required=True,type=Path);p.add_argument('--oracle',required=True,type=Path);p.add_argument('--postimage',type=Path);p.add_argument('--out',required=True,type=Path)
 a=p.parse_args();data,helper,original=verify_sources(a.migrations,a.matcher)
 pre=json.loads(a.preimage.read_bytes());oracle=json.loads(a.oracle.read_bytes())
 post=json.loads(a.postimage.read_bytes()) if a.postimage else None
 install,inverse=generate(pre,oracle,helper,original,post);a.out.mkdir(mode=0o700,parents=True,exist_ok=True)
 receipt={'schema':'wolo.c02.helper-enrollment.source-only.v1','source_sha256':sha(Path(__file__).read_bytes()),'state_source_sha256':sha(Path(__file__).with_name('c02_helper_history_state.sql').read_bytes()),'historical_blobs':PINS,'matcher_sha256':MATCHER_SHA,'preimage_sha256':sha(a.preimage.read_bytes()),'oracle_sha256':sha(a.oracle.read_bytes()),'oracle_canonical_sha256':sha(json.dumps(oracle,sort_keys=True,separators=(',',':')).encode()),'oracle_profile':QUALIFIED_ORACLES[sha(json.dumps(oracle,sort_keys=True,separators=(',',':')).encode())],'postimage_sha256':sha(a.postimage.read_bytes()) if a.postimage else None,'inverse_requires_enrolled_identity':True,'production_admitted':False,'funding':'DENIED'}
 for name,text in [('install.sql',install),('inverse.sql',inverse)]:
  dest=a.out/name
  with dest.open('x') as f:f.write(text)
  dest.chmod(0o600);receipt[name+'_sha256']=sha(dest.read_bytes())
 with (a.out/'source-receipt.json').open('x') as f:json.dump(receipt,f,indent=2,sort_keys=True);f.write('\n')
 (a.out/'source-receipt.json').chmod(0o600)
 print(json.dumps(receipt,sort_keys=True))
if __name__=='__main__':main()

#!/usr/bin/env python3
"""Finite NEW PG16 enrollment/inverse proof. Never connects to an existing DB.
Inputs are immutable historical migration blobs, not a production database.
The 8-lock/17-binding/20-wrapper suites are not rerun.
"""
from pathlib import Path
from datetime import datetime,timezone
import argparse,hashlib,json,os,re,shutil,subprocess,sys,tempfile,time
sys.path.insert(0,str(Path(__file__).resolve().parent))
import c02_helper_enrollment as e

ENV={'PATH':'/usr/bin:/bin','LC_ALL':'C','PGCONNECT_TIMEOUT':'2'}
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--migrations',required=True,type=Path);p.add_argument('--matcher',required=True,type=Path);p.add_argument('--v2-install',required=True,type=Path);p.add_argument('--v2-inverse',required=True,type=Path);p.add_argument('--pg-bin',required=True,type=Path);p.add_argument('--out',required=True,type=Path);p.add_argument('--tmp-root',type=Path)
 a=p.parse_args();data,helper,original=e.verify_sources(a.migrations,a.matcher)
 assert e.sha(a.v2_install.read_bytes())=='a4a2233cc8d931b20120efae732f36a20c968960f08328dc4f5c6b99dcc9f469'
 assert e.sha(a.v2_inverse.read_bytes())=='7a8d47b320fdc9294ac60a87a86ab62123b4534c5f5258f1609f119535f2f675'
 a.out.mkdir(mode=0o700,parents=True,exist_ok=True)
 base=Path(tempfile.mkdtemp(prefix='c02-enroll-',dir=a.tmp_root));cluster=base/'data';port='57741';checks={};failure=None;started=False;sources={};oracle=None
 def cmd(argv,**kw):return subprocess.run([str(x) for x in argv],env=ENV,capture_output=True,text=True,timeout=20,**kw)
 def sql(text,db='postgres',role='postgres',error=None):
  r=cmd([a.pg_bin/'psql','-XqAt','-w','-h',base,'-p',port,'-U',role,'-d',db,'-v','ON_ERROR_STOP=1','-c',text])
  if error is None:assert r.returncode==0,r.stderr[-2500:]
  else:assert r.returncode!=0 and error in r.stderr,(error,r.returncode,r.stderr[-2500:])
  return r.stdout.strip()
 def hist(strip='NULL'):
  return json.loads(sql(e.STATE_SQL+'SELECT pg_temp.c02_history_state('+strip+')::text;'))
 def full():
  return sql(e.STATE_SQL+"""SELECT jsonb_build_object('history',pg_temp.c02_history_state(NULL),
   'role',(SELECT to_jsonb(r) FROM pg_roles r WHERE rolname='c02_row_lock'),
   'schema',(SELECT to_jsonb(n) FROM pg_namespace n WHERE nspname='c02_internal'),
   'funcs',(SELECT jsonb_agg(to_jsonb(p) ORDER BY p.oid) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='c02_internal'),
   'roledeps',(SELECT jsonb_agg(to_jsonb(d) ORDER BY dbid,classid,objid,objsubid,deptype) FROM pg_shdepend d WHERE refclassid='pg_authid'::regclass AND refobjid=(SELECT oid FROM pg_roles WHERE rolname='c02_row_lock')),
   'members',(SELECT jsonb_agg(to_jsonb(m) ORDER BY roleid,member,grantor) FROM pg_auth_members m WHERE (SELECT oid FROM pg_roles WHERE rolname='c02_row_lock') IN(roleid,member,grantor)),
   'settings',(SELECT jsonb_agg(to_jsonb(s) ORDER BY setdatabase,setrole) FROM pg_db_role_setting s WHERE setrole=(SELECT oid FROM pg_roles WHERE rolname='c02_row_lock')))::text;""")
 def runnable(s):assert s.count(e.HOLD)==1;return s.replace(e.HOLD,'',1)
 def rows():
  return sql("""SELECT jsonb_build_object(
  'a',(SELECT jsonb_agg(to_jsonb(t) ORDER BY operation_id) FROM war_satchel_wager_authorizations t),
  'b',(SELECT jsonb_agg(to_jsonb(t) ORDER BY operation_id) FROM war_satchel_wager_broadcasts t),
  'r',(SELECT jsonb_agg(to_jsonb(t) ORDER BY id) FROM war_satchel_funded_reservations t),
  'credits',(SELECT count(*) FROM war_satchel_funded_journal),
  'native',(SELECT count(*) FROM war_satchel_native_return_operations),
  'native_seq',(SELECT jsonb_build_array(last_value,is_called) FROM war_satchel_native_claim_id_seq))::text""")
 try:
  r=cmd([a.pg_bin/'initdb','-D',cluster,'-U','postgres','--auth-local=trust','--auth-host=reject','--no-locale']);assert r.returncode==0,r.stderr
  r=cmd([a.pg_bin/'pg_ctl','-D',cluster,'-l',base/'log','-o',f"-c listen_addresses='' -c shared_buffers=16MB -k {base} -p {port}",'-w','start']);assert r.returncode==0,r.stderr;started=True
  version=sql('SHOW server_version');assert version.startswith('16.')
  assert sql("SELECT inet_server_addr() IS NULL AND current_setting('listen_addresses')=''")=='t';checks['new_unix_only_PG16_cluster']=True
  sql('CREATE ROLE history_owner NOLOGIN NOINHERIT; CREATE ROLE auth_owner NOLOGIN NOINHERIT; CREATE ROLE broadcast_owner NOLOGIN NOINHERIT; CREATE ROLE reserve_owner NOLOGIN NOINHERIT; CREATE ROLE c02_journal_worker LOGIN NOINHERIT; CREATE ROLE website LOGIN NOINHERIT; CREATE ROLE unrelated LOGIN NOINHERIT; ALTER SCHEMA public OWNER TO history_owner; CREATE SCHEMA attacker AUTHORIZATION website')
  sql('CREATE TABLE users(id integer PRIMARY KEY); CREATE TABLE war_satchel_proof_candidates(id bigint PRIMARY KEY); CREATE TABLE pending_wolo_claims(id integer PRIMARY KEY); CREATE TABLE bet_auto_executions(id integer PRIMARY KEY); CREATE TABLE bet_auto_presets(id integer PRIMARY KEY); GRANT REFERENCES ON ALL TABLES IN SCHEMA public TO history_owner')
  for name,raw in data.items():
   source=raw.decode()
   if 'native_forward' in name:
    source=source[source.index('CREATE SEQUENCE war_satchel_native_claim_id_seq'):source.index('-- A separately signed original-op approval')]
   sql('SET ROLE history_owner;\n'+source+'\nRESET ROLE;')
  sql('ALTER TABLE war_satchel_wager_authorizations OWNER TO auth_owner; ALTER TABLE war_satchel_wager_broadcasts OWNER TO broadcast_owner; ALTER TABLE war_satchel_funded_reservations OWNER TO reserve_owner')
  # A synthetic original-source path; no bank deposit or credit is performed.
  sql("""INSERT INTO users VALUES(1); INSERT INTO bet_auto_executions VALUES(10);
  INSERT INTO war_satchel_funded_reservations(id,owner_user_id,execution_id,amount_uwolo,ticket_request_id) VALUES('reservation',1,10,1000,'operation');
  INSERT INTO war_satchel_wager_authorizations(operation_id,reservation_id,owner_user_id,snapshot_json,reservation_digest,ledger_revision,consent_digest)
  VALUES('operation','reservation',1,'{"ownerUserId":1,"executionId":10,"reservationId":"reservation","operationId":"operation","amountUwolo":"1000"}',repeat('a',64),repeat('b',64),repeat('c',64));
  INSERT INTO war_satchel_wager_approvals(operation_id,approval_json) VALUES('operation','{}');
  UPDATE war_satchel_funded_reservations SET status='unknown_hold';
  INSERT INTO war_satchel_wager_broadcasts(operation_id,tx_hash) VALUES('operation',repeat('A',64));
  UPDATE war_satchel_funded_reservations SET status='committed',ticket_id=11,tx_hash=repeat('A',64);""")
  initial_rows=rows();original_state=hist();oracle={'schema':'wolo.c02.helper-historical-oracle.v1','historical_blobs':e.PINS,'owners':original_state['owners'],'shape':original_state['shape']};checks['two_full_historical_blobs_and_exact_native_wrapper_subset_with_declared_FK_prerequisites']=True
  oracle_path=a.out/'historical-shape.json';oracle_path.write_text(json.dumps(oracle,sort_keys=True,indent=2)+'\n');oracle_path.chmod(0o600)
  for label,ddl,error in [
   ('inheritance','CREATE TABLE public.forbidden_child() INHERITS(public.war_satchel_wager_broadcasts)','UNADMITTED_INHERITANCE'),
   ('policy','CREATE POLICY forbidden_policy ON public.war_satchel_funded_reservations USING(true)','UNADMITTED_POLICY_OR_RULE'),
   ('rewrite','CREATE TABLE attacker.sink(x integer); CREATE RULE forbidden_rule AS ON UPDATE TO public.war_satchel_funded_reservations DO ALSO INSERT INTO attacker.sink VALUES(1)','UNADMITTED_POLICY_OR_RULE'),
   ('owner','ALTER TABLE public.war_satchel_wager_broadcasts OWNER TO unrelated','HISTORICAL_OWNER_NOT_ORIGINAL'),
   ('disabled_guard','ALTER TABLE public.war_satchel_wager_authorizations DISABLE TRIGGER satchel_wager_authorization_immutable','HISTORICAL_SHAPE_NOT_ORIGINAL'),
   ('metadata_delimiter',"ALTER ROLE c02_journal_worker SET application_name='$pre$'",'CAPTURE_CONTAINS_RESERVED_SQL_DELIMITER')]:
   captured=json.loads(sql('BEGIN;'+ddl+';'+e.STATE_SQL+'SELECT pg_temp.c02_history_state(NULL)::text; ROLLBACK;'))
   try:e.generate(captured,oracle,helper,original)
   except ValueError as ex:assert str(ex)==error,(label,str(ex))
   else:raise AssertionError('unqualified '+label+' adopted')
   if label=='owner':
    bad_oracle=json.loads(json.dumps(oracle));bad_oracle['owners']=captured['owners']
    try:e.generate(captured,bad_oracle,helper,original)
    except ValueError as ex:assert str(ex)=='HISTORICAL_ORACLE_NOT_SOURCE_PINNED'
    else:raise AssertionError('joint owner/oracle rebaseline accepted')
    checks['joint_owner_and_oracle_rebaseline_rejected']=True
   assert hist()==original_state;checks['existing_'+label+'_cannot_be_adopted_as_original']=True
  audit=data[next(n for n in data if 'funded_ledger_foundation' in n)].decode();audit=audit[audit.index('CREATE FUNCTION war_satchel_funded_audit_immutable()'):audit.index('CREATE TRIGGER satchel_funded_claim_return_immutable')].replace('CREATE FUNCTION','CREATE OR REPLACE FUNCTION',1)
  for case in ['raw_null','unrelated_explicit']:
   if case=='unrelated_explicit':
    sql('SET ROLE auth_owner; GRANT SELECT(operation_id), UPDATE(reservation_id) ON war_satchel_wager_authorizations TO unrelated; RESET ROLE; SET ROLE broadcast_owner; GRANT SELECT(tx_hash) ON war_satchel_wager_broadcasts TO unrelated; RESET ROLE; SET ROLE reserve_owner; GRANT SELECT(status) ON war_satchel_funded_reservations TO unrelated; RESET ROLE')
   baseline=hist();install,inverse=e.generate(baseline,oracle,helper,original)
   for name,text in [('install.sql',install),('inverse-template.sql',inverse)]:
    pth=a.out/(case+'-'+name);pth.write_text(text);pth.chmod(0o600);sources[pth.name]=e.sha(pth.read_bytes())
   (a.out/(case+'-preimage.json')).write_text(json.dumps(baseline,sort_keys=True,indent=2)+'\n');(a.out/(case+'-preimage.json')).chmod(0o600)
   sql(install,error='HOLD:C02_HELPER_ENROLLMENT');assert hist()==baseline;checks[case+'_whole_source_refuses_before_DDL']=True
   # Explicit-empty preimage is refused without forbidden catalog edits.
   empty=json.loads(json.dumps(baseline));empty['attributes'][0]['attacl']='{}'
   try:e.generate(empty,oracle,helper,original)
   except ValueError as ex:assert str(ex)=='EXPLICIT_EMPTY_COLUMN_ACL_NOT_REVERSIBLE'
   else:raise AssertionError('empty ACL accepted')
   checks[case+'_explicit_empty_capture_rejected_without_catalog_write']=True
   # Reusing any unknown new identity/schema is forbidden.
   sql('CREATE ROLE c02_row_lock NOLOGIN');sql(runnable(install),error='C02_NEW_OWNER_SCHEMA_MUST_BE_ABSENT');sql('DROP ROLE c02_row_lock')
   sql('CREATE SCHEMA c02_internal');sql(runnable(install),error='C02_NEW_OWNER_SCHEMA_MUST_BE_ABSENT');sql('DROP SCHEMA c02_internal RESTRICT');assert hist()==baseline
   checks[case+'_preexisting_owner_or_schema_refused_without_history_change']=True
   # Trusted oracle prevents adopting an already changed historical guard.
   sql("CREATE OR REPLACE FUNCTION war_satchel_funded_audit_immutable() RETURNS trigger LANGUAGE plpgsql AS $$BEGIN RETURN NEW; END$$")
   sql(runnable(install),error='C02_HISTORICAL_PREIMAGE_CHANGED')
   try:e.generate(hist(),oracle,helper,original)
   except ValueError as ex:assert str(ex)=='HISTORICAL_SHAPE_NOT_ORIGINAL'
   else:raise AssertionError('changed original adopted')
   changed=hist();bad_oracle=json.loads(json.dumps(oracle));bad_oracle['shape']=changed['shape']
   try:e.generate(changed,bad_oracle,helper,original)
   except ValueError as ex:assert str(ex)=='HISTORICAL_ORACLE_NOT_SOURCE_PINNED'
   else:raise AssertionError('joint guard/oracle rebaseline accepted')
   checks[case+'_joint_guard_and_oracle_rebaseline_rejected']=True
   sql(audit);assert hist()==baseline;checks[case+'_changed_guard_rejected_by_capture_and_transaction']=True
   partial=runnable(install).replace('SET LOCAL ROLE c02_row_lock;\nREVOKE',"DO $$BEGIN RAISE EXCEPTION 'INJECTED_AFTER_COLUMN_GRANTS'; END$$;\nSET LOCAL ROLE c02_row_lock;\nREVOKE",1)
   sql(partial,error='INJECTED_AFTER_COLUMN_GRANTS');assert hist()==baseline
   assert sql("SELECT NOT EXISTS(SELECT 1 FROM pg_roles WHERE rolname='c02_row_lock') AND NOT EXISTS(SELECT 1 FROM pg_namespace WHERE nspname='c02_internal')")=='t'
   checks[case+'_failure_after_grants_restores_exact_preimages']=True
   inner=runnable(install).replace('\nBEGIN;\n','\n',1).rsplit('COMMIT;',1)[0]
   sql("BEGIN; SET LOCAL log_min_error_statement=panic; DO $$BEGIN EXECUTE format('ALTER ROLE c02_journal_worker PASSWORD %L',md5(random()::text)); END$$;"+inner,error='C02_HISTORICAL_PREIMAGE_CHANGED');assert hist()==baseline
   checks[case+'_worker_credential_drift_detected_without_exposing_credential']=True
   sql(runnable(install));assert hist("'c02_row_lock'::regrole")==baseline
   before=full();sql(runnable(inverse),error='HOLD:C02_ENROLLMENT_POSTIMAGE_REQUIRED');assert full()==before
   checks[case+'_inverse_without_created_identity_refused']=True
   postimage=json.loads(sql(e.IDENTITY_SQL+'::text'))
   postpath=a.out/(case+'-postimage.json');postpath.write_text(json.dumps(postimage,sort_keys=True,indent=2)+'\n');postpath.chmod(0o600)
   same_install,inverse=e.generate(baseline,oracle,helper,original,postimage);assert same_install==install
   finalpath=a.out/(case+'-inverse.sql');finalpath.write_text(inverse);finalpath.chmod(0o600);sources[finalpath.name]=e.sha(finalpath.read_bytes())
   checks[case+'_column_enrollment_preserves_all_original_metadata_and_grantors']=True
   assert sql("SELECT c02_internal.matches_original_funding('operation',1,repeat('A',64),11,1000)",role='c02_journal_worker')=='t'
   checks[case+'_enrolled_real_helper_reads_original_three_source_rows']=True
   # A custom attacker-owned trigger cannot borrow private helper authority.
   sql("CREATE TABLE attacker.trap(x integer); ALTER TABLE attacker.trap OWNER TO website; CREATE FUNCTION attacker.call_helper() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog AS $$BEGIN PERFORM c02_internal.matches_original_funding('operation',1,repeat('A',64),11,1000); RETURN NEW; END$$; ALTER FUNCTION attacker.call_helper() OWNER TO website; CREATE TRIGGER trapped BEFORE INSERT ON attacker.trap FOR EACH ROW EXECUTE FUNCTION attacker.call_helper()")
   sql('INSERT INTO attacker.trap VALUES(1)',role='website',error='permission denied for schema c02_internal')
   sql('DROP TABLE attacker.trap RESTRICT; DROP FUNCTION attacker.call_helper() RESTRICT');checks[case+'_attacker_owned_trigger_cannot_enter_private_helper']=True
   helper_head,helper_tail=helper.split('RETURNS',1)
   inverse_inner=runnable(inverse).replace('\nBEGIN;\n','\n',1).rsplit('COMMIT;',1)[0]
   for label,left,right in [('swapped_integer_names','p_owner','p_ticket'),('swapped_varchar_names','p_operation_id','p_hash'),('same_definition_new_OID',None,None)]:
    h=helper_head
    if left:
     h=re.sub(r'\b'+left+r'\b','c02_swap',h);h=re.sub(r'\b'+right+r'\b',left,h);h=h.replace('c02_swap',right)
    recreated=h+'RETURNS'+helper_tail
    before=full();sql("BEGIN; SET LOCAL ROLE c02_row_lock; DROP FUNCTION c02_internal.matches_original_funding(varchar,integer,varchar,integer,bigint) RESTRICT;"+recreated+'RESET ROLE;'+inverse_inner,error='C02_HELPER_DEFINITION_DRIFT' if left else 'C02_ENROLLED_IDENTITY_CHANGED');assert full()==before
    checks[case+'_'+label+'_inverse_refusal_restores_original_enrolled_OID']=True
   before=full();partial=runnable(inverse).replace('DROP SCHEMA c02_internal RESTRICT;',"DO $$BEGIN RAISE EXCEPTION 'INJECTED_AFTER_HELPER_DROP'; END$$;\nDROP SCHEMA c02_internal RESTRICT;",1)
   sql(partial,error='INJECTED_AFTER_HELPER_DROP');assert full()==before
   checks[case+'_failure_after_helper_drop_restores_exact_enrollment']=True
   # Accepted wrapper files are setup dependencies here; their suites are not replayed.
   wi=re.sub(r'DO \$C02_V2_NOT_ADMITTED\$.*?END \$C02_V2_NOT_ADMITTED\$;','',a.v2_install.read_text(),count=1,flags=re.S)
   wr=re.sub(r'DO \$C02_V2_NOT_ADMITTED\$.*?END \$C02_V2_NOT_ADMITTED\$;','',a.v2_inverse.read_text(),count=1,flags=re.S)
   # V2 expects the deployed web-role identity, not the independent attacker.
   sql('CREATE ROLE aoe2war_web_prod NOLOGIN') if case=='raw_null' else None
   sql(wi);before=full();sql(runnable(inverse),error='C02_RESTORE_ORIGINAL_WRAPPER_FIRST');assert full()==before;sql(wr)
   checks[case+'_inverse_refuses_installed_V2_wrapper_and_preserves_enrollment']=True
   for label,setup,cleanup,error in [
    ('schema_object','CREATE TABLE c02_internal.foreign_object(x integer)','DROP TABLE c02_internal.foreign_object RESTRICT','C02_FOREIGN_SCHEMA_OBJECT'),
    ('membership','GRANT c02_row_lock TO unrelated','REVOKE c02_row_lock FROM unrelated','C02_NEW_ROLE_AUTHORITY_DRIFT'),
    ('role_setting',"ALTER ROLE c02_row_lock SET statement_timeout='1s'",'ALTER ROLE c02_row_lock RESET ALL','C02_NEW_ROLE_AUTHORITY_DRIFT')]:
    sql(setup);before=full();sql(runnable(inverse),error=error);assert full()==before;sql(cleanup);checks[case+'_'+label+'_refusal_is_transactionally_exact']=True
   foreign='c02_foreign_'+case
   sql('CREATE DATABASE '+foreign)
   sql('CREATE TABLE public.foreign_dependency(x integer); ALTER TABLE public.foreign_dependency OWNER TO c02_row_lock',db=foreign)
   before=full();sql(runnable(inverse),error='C02_FOREIGN_ROLE_DEPENDENCY');assert full()==before
   sql('DROP TABLE public.foreign_dependency RESTRICT',db=foreign);sql('DROP DATABASE '+foreign);checks[case+'_cross_database_dependency_refuses_inverse']=True
   sql(runnable(inverse));assert hist()==baseline and rows()==initial_rows
   assert sql("SELECT NOT EXISTS(SELECT 1 FROM pg_roles WHERE rolname='c02_row_lock') AND NOT EXISTS(SELECT 1 FROM pg_namespace WHERE nspname='c02_internal')")=='t'
   checks[case+'_exact_committed_inverse_and_zero_unauthorized_native_credit']=True
 except Exception as ex:failure={'type':type(ex).__name__,'message':str(ex)[-3000:]}
 finally:
  if started:
   r=cmd([a.pg_bin/'pg_ctl','-D',cluster,'-m','fast','-w','stop']);checks['fixture_stopped']=r.returncode==0
  if failure is None:shutil.rmtree(base);checks['fixture_removed']=True
  receipt={'schema':'wolo.c02.helper-enrollment-inverse.isolated.v1','utc':datetime.now(timezone.utc).isoformat(),'version':locals().get('version'),'source_sha256':e.sha(Path(e.__file__).read_bytes()),'state_source_sha256':e.sha(Path(e.__file__).with_name('c02_helper_history_state.sql').read_bytes()),'test_source_sha256':e.sha(Path(__file__).read_bytes()),'historical_blobs':e.PINS,'matcher_source_sha256':e.MATCHER_SHA,'oracle_sha256':e.sha((a.out/'historical-shape.json').read_bytes()) if oracle else None,'generated_sources':sources,'checks':checks,'failure':failure,'all_passed':failure is None and all(checks.values()),'production_connection_or_mutation':False,'previous_8_17_20_suites_rerun':False,'limits':['Two full original historical migrations plus the exact native14 operation/wrapper subset use declared minimal FK prerequisites; not full 13+14 composition','Explicit-empty ACL is tested as captured metadata; no system catalog is edited','All records and roles are isolated synthetic fixtures; no bank/reviewer/funding acceptance','Source output retains unconditional HOLD; live grants require separate owner and producer-exclusion admission']}
  if failure:receipt['failed_fixture_preserved']=str(base)
  raw=(json.dumps(receipt,sort_keys=True,indent=2)+'\n').encode();pth=a.out/('receipt-'+str(time.time_ns())+'.json')
  with pth.open('xb') as h:h.write(raw);h.flush();os.fsync(h.fileno())
  pth.chmod(0o600);print(json.dumps({'pass':receipt['all_passed'],'checks':len(checks),'failure':failure,'receipt':str(pth),'sha256':e.sha(raw)}))
 return 0 if receipt['all_passed'] else 1
if __name__=='__main__':raise SystemExit(main())

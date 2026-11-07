#!/usr/bin/env python3
"""C03 real Nov7 HD+DE encrypted full-data owner rehearsal, Intel isolated only.

No network, HEL1, customer-facing service, existing DB, custody or funding.
Do not use the resulting receipt as C03, C06 or C07 formal acceptance.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import shlex
import stat
import subprocess
import sys
import tempfile

HOME=Path.home()
ROOT=HOME/".wolo-owner-authority/offhost-db-rehearsal-20261107"
KEY=HOME/".wolo-owner-authority/offhost-db-rehearsal-20261105/v2-age-identity.txt"
TOOL=HOME/".cache/aoe2war/c03-conservative-real-schema-source-20261107.py"
TOOL_SHA="1973728eba0e451f1c1f23271880d7c8c0884d48bda6b67b1b04769f5ba286a8"
BIN=HOME/".local/aoe2war-pg16-16.15/bin"
PINS={
 "hd":("aoe2hd_db.pgcustom.gzip1.age","2bbb68bb53ec54eb12717665b76b23b4a9f0df9b6d1d6f9e0c73e54e7cdde06f",909895303,190,60,58),
 "de":("aoe2de_db.pgcustom.age","e8f16dbac588588a5ad7b643b2711065fa9e58d0c58714a520725e283e1512b3",336456,52,21,21)
}
PROOF={
 "hd":("c07-hd-nov7-encrypted-real-restore-receipt.json","91c8411e80db0a6337bba3e3cdb21473464bdf62308d6b63dae4da6714a4dfd8"),
 "de":("c07-de-nonquiesced-offhost-restoration-20261107.json","d094e5cb26f6cc7b26b191ee3342eb51e20ec6dcb5e58ec33d9abcf36908c9a6")
}
RESULT=ROOT/"c03-fresh-hd-de-explicit-assets-full-public-owner-parity-20261107.json"
EXTRA_ASSET_TABLES={
 "hd":(
  "public.championship_challenge_participants",
  "public.championship_custody_seats",
  "public.oracle_market_proposals",
  "public.oracle_paper_positions",
  "public.user_gifts",
  "public.war_graph_watcher_attestations",
 ),
 "de":("public.user_gifts",),
}
EXTRA_ASSET_SEQUENCES={"hd":6,"de":1}
BASE_NAME_FINANCE={"hd":54,"de":20}
BASE_NAME_SEQUENCES={"hd":52,"de":20}
EXPECTED_SEQUENCES={"hd":180,"de":50}
EXPECTED_PUBLIC_FUNCTIONS={"hd":39,"de":0}
EXPECTED_SCHEMA_OWNER={"hd":"pg_database_owner","de":"c03_de_legacy"}


def need(cond,reason):
 if not cond:raise RuntimeError(reason)

def h(p):
 digest=hashlib.sha256()
 with p.open("rb") as stream:
  for block in iter(lambda:stream.read(1024*1024),b""):digest.update(block)
 return digest.hexdigest()

def private(p,expected_sha=None,expected_size=None):
 s=p.lstat()
 need(stat.S_ISREG(s.st_mode) and not p.is_symlink() and s.st_uid==os.getuid()
      and s.st_nlink==1 and stat.S_IMODE(s.st_mode)==0o600,
      "PRIVATE_FILE_BOUNDARY_"+p.name)
 if expected_size is not None:need(s.st_size==expected_size,"PRIVATE_SIZE_DRIFT_"+p.name)
 if expected_sha is not None:need(h(p)==expected_sha,"PRIVATE_SHA_DRIFT_"+p.name)

def call(args,timeout=45,**opts):
 opts.setdefault("stdout",subprocess.PIPE)
 opts.setdefault("stderr",subprocess.PIPE)
 return subprocess.run([str(v) for v in args],timeout=timeout,**opts)

def yes(p,reason):
 need(p.returncode==0,reason+"_RC_"+str(p.returncode))
 return p.stdout.decode("utf-8","replace").strip()

def main():
 need(sys.platform=="darwin" and platform.machine()=="x86_64" and os.geteuid()!=0,
      "INTEL_MAC_NONROOT_REQUIRED")
 st=ROOT.lstat()
 need(stat.S_ISDIR(st.st_mode) and not ROOT.is_symlink()
      and st.st_uid==os.getuid() and stat.S_IMODE(st.st_mode)==0o700,
      "OWNER_PRIVATE_OFFHOST_REHEARSAL_ROOT_REQUIRED")
 need(not RESULT.exists() and not RESULT.is_symlink(),"NO_REPLAY_OF_PREVIOUS_RECEIPT")
 private(KEY)
 private(TOOL,TOOL_SHA)
 spec=importlib.util.spec_from_file_location("c03_original_intel_source",TOOL)
 original=importlib.util.module_from_spec(spec)
 spec.loader.exec_module(original)
 for name in ("postgres","initdb","pg_ctl","createdb","pg_restore","psql"):
  tool=BIN/name
  need(tool.is_file() and os.access(tool,os.X_OK),"PRIVATE_PG16_TOOL_"+name)
 need("16." in yes(call([BIN/"pg_restore","--version"],timeout=12),"PG16_VERSION"),
      "NOT_PG16")
 age=Path("/usr/local/bin/age")
 need(age.exists() and age.is_file() and os.access(age,os.X_OK),"AGE_BINARY")
 archives={}
 for lane,(name,sha,size,total,finance,seq) in PINS.items():
  path=ROOT/name
  private(path,sha,size)
  receipt,receipt_sha=PROOF[lane]
  private(ROOT/receipt,receipt_sha)
  archives[lane]=path
 # Independently authenticate all encrypted bytes, never write cleartext.
 for lane,path in archives.items():
  auth=call([age,"-d","-i",KEY,path],stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,timeout=300)
  need(auth.returncode==0,"COMPLETE_AGE_AUTH_"+lane)
 print("PASS_COMPLETE_HD_DE_CIPHERTEXT_AUTHENTICATION",flush=True)
 user=os.getenv("USER")
 need(user and user.isidentifier(),"PRIVATE_OPERATOR_ACCOUNT")
 report={}
 os.umask(0o077)
 with tempfile.TemporaryDirectory(prefix="c03-real-data-socket-",dir="/tmp") as sock:
  need(len((sock+"/.s.PGSQL.54406").encode())<104,"SOCKET_PATH_TOO_LONG")
  with tempfile.TemporaryDirectory(prefix="c03-real-full-data-",dir=ROOT) as t:
   root=Path(t);data=root/"pgdata";log=root/"postgres.log"
   yes(call([BIN/"initdb","-A","trust","-U",user,"-D",data],timeout=100),
       "PRIVATE_INITDB")
   started=False
   port="54406"
   def sql(db,stmt,actor=None,allow_fail=False,timeout=35):
    p=call([BIN/"psql","-X","-qAt","-v","ON_ERROR_STOP=1",
      "-h",sock,"-p",port,"-U",actor or user,"-d",db,"-c",stmt],timeout=timeout)
    if not allow_fail:yes(p,"ISOLATED_SQL_"+db)
    return p
   def text(db,stmt,actor=None):
    return sql(db,stmt,actor).stdout.decode("utf-8","replace").strip()
   try:
    opts="-c listen_addresses='' -c unix_socket_directories="+shlex.quote(sock)
    opts+=" -c unix_socket_permissions=0700 -c fsync=off -p "+port
    yes(call([BIN/"pg_ctl","-D",data,"-o",opts,"-l",log,"-w","start"],timeout=55),
        "PRIVATE_PG16_START")
    started=True
    for lane,(name,sha,size,total,expected_finance,expected_seq) in PINS.items():
     db="c03_full_"+lane
     legacy="c03_"+lane+"_legacy"
     neutral="c03_"+lane+"_neutral"
     text("postgres","CREATE ROLE "+legacy+" LOGIN")
     text("postgres","CREATE ROLE "+neutral+" NOLOGIN")
     text("postgres","CREATE DATABASE "+db+" TEMPLATE template0")
     ageproc=subprocess.Popen([str(age),"-d","-i",str(KEY),str(archives[lane])],
        stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
     pgproc=subprocess.Popen([str(BIN/"pg_restore"),"--exit-on-error","--no-owner",
       "--no-acl","--no-comments","-h",sock,"-p",port,"-U",user,"-d",db],
       stdin=ageproc.stdout,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
     ageproc.stdout.close()
     print("STARTED_EXACT_NOV7_"+lane.upper()+"_FULL_DATA_RESTORE",flush=True)
     try:
      output,err=pgproc.communicate(timeout=1600)
      age_rc=ageproc.wait(timeout=90)
     except BaseException:
      if pgproc.poll() is None:pgproc.kill()
      if ageproc.poll() is None:ageproc.kill()
      pgproc.communicate(timeout=15)
      raise
     need(pgproc.returncode==0,"PRIVATE_FULL_PG16_RESTORE_"+lane+"_"+err.decode(errors="replace")[-200:])
     # An archive reader may close before age completes; all tags were
     # authenticated in an independent whole-archive pass above.
     need(age_rc in (0,-13,141),"AGE_PRODUCER_UNEXPECTED_EXIT_"+lane)
     all_tables=int(text(db,"SELECT count(*) FROM pg_tables WHERE schemaname='public'"))
     need(all_tables==total,"RESTORED_FULL_TABLE_CENSUS_DRIFT_"+lane)
     def q(database,statement):
      raw=text(database,statement)
      return [line for line in raw.splitlines() if line.strip()]
     base_finance=original.finance_identifiers(q,db)
     base_seq=original.sequence_identifiers(q,db)
     need(len(base_finance)==BASE_NAME_FINANCE[lane] and
          len(base_seq)==BASE_NAME_SEQUENCES[lane],
          "REAL_BASE_FINANCE_SCOPE_DRIFT_"+lane)
     extra=EXTRA_ASSET_TABLES[lane]
     quoted=",".join("'"+item.split(".",1)[1]+"'" for item in extra)
     extra_identifiers=original.check_exact_identifiers(q(db,
      "SELECT format('%I.%I',n.nspname,c.relname) FROM pg_class c "
      "JOIN pg_namespace n ON n.oid=c.relnamespace "
      "WHERE n.nspname='public' AND c.relkind IN ('r','p') "
      "AND c.relname IN ("+quoted+") ORDER BY 1;"))
     need(set(extra_identifiers)==set(extra) and not (set(extra_identifiers)&set(base_finance)),
          "UNEXPECTED_EXPLICIT_ASSET_TABLE_SCOPE_"+lane)
     extra_seq_identifiers=original.check_exact_identifiers(q(db,
      "SELECT DISTINCT format('%I.%I',ns.nspname,sc.relname) FROM pg_class sc "
      "JOIN pg_namespace ns ON ns.oid=sc.relnamespace "
      "JOIN pg_depend dep ON dep.objid=sc.oid AND dep.deptype IN ('a','i') "
      "JOIN pg_class parent ON parent.oid=dep.refobjid "
      "WHERE ns.nspname='public' AND sc.relkind='S' "
      "AND parent.relname IN ("+quoted+") ORDER BY 1;"))
     need(len(extra_seq_identifiers)==EXTRA_ASSET_SEQUENCES[lane] and
          not (set(extra_seq_identifiers)&set(base_seq)),
          "EXPLICIT_ASSET_SEQUENCE_SCOPE_DRIFT_"+lane)
     finance_names=original.check_exact_identifiers(sorted(
       set(base_finance)|set(extra_identifiers)))
     seq_names=original.check_exact_identifiers(sorted(
       set(base_seq)|set(extra_seq_identifiers)))
     need(len(finance_names)==expected_finance and len(seq_names)==expected_seq,
          "REAL_FINANCE_ASSET_UNION_SCOPE_DRIFT_"+lane)
     # Unlike the prior finance-only rehearsal, rebuild true owner state for
     # ALL 190/52 public tables and 180/50 public sequences before migration.
     # Actual live source inventory established all were legacy owned.
     all_tables=original.check_exact_identifiers(q(db,
      "SELECT format('%I.%I',n.nspname,c.relname) FROM pg_class c "
      "JOIN pg_namespace n ON n.oid=c.relnamespace "
      "WHERE n.nspname='public' AND c.relkind IN ('r','p') ORDER BY 1;"))
     all_sequences=original.check_exact_identifiers(q(db,
      "SELECT format('%I.%I',n.nspname,c.relname) FROM pg_class c "
      "JOIN pg_namespace n ON n.oid=c.relnamespace "
      "WHERE n.nspname='public' AND c.relkind='S' ORDER BY 1;"))
     public_func_commands=q(db,
      "SELECT format('ALTER FUNCTION %I.%I(%s) OWNER TO "+legacy+";',"
      "n.nspname,p.proname,pg_get_function_identity_arguments(p.oid)) "
      "FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace "
      "WHERE n.nspname='public' AND p.prokind='f' ORDER BY 1;")
     need(len(all_tables)==total and
          len(all_sequences)==EXPECTED_SEQUENCES[lane] and
          len(public_func_commands)==EXPECTED_PUBLIC_FUNCTIONS[lane],
          "FULL_PUBLIC_CATALOG_OWNER_MODEL_INPUT_DRIFT_"+lane)
     need(set(finance_names).issubset(set(all_tables)) and
          set(seq_names).issubset(set(all_sequences)),
          "FINANCE_SCOPE_NOT_SUBSET_OF_ALL_PUBLIC_OBJECTS_"+lane)
     first=finance_names[0]
     # Full post-restore rows exist; check database logical size and finance
     # table counts without exporting any production data or recipient rows.
     bytes_before=int(text(db,"SELECT pg_database_size(current_database())"))
     need(bytes_before>2000000000 if lane=="hd" else bytes_before>5000000,
          "FULL_RESTORED_DB_BYTES_MISSING_"+lane)
     text("postgres","ALTER DATABASE "+db+" OWNER TO "+legacy)
     if lane=="de":text(db,"ALTER SCHEMA public OWNER TO "+legacy)
     text(db,"GRANT CREATE,USAGE ON SCHEMA public TO "+legacy)
     for identifier in all_tables:text(db,"ALTER TABLE "+identifier+" OWNER TO "+legacy)
     for identifier in all_sequences:text(db,"ALTER SEQUENCE "+identifier+" OWNER TO "+legacy)
     for statement in public_func_commands:
      need(statement.startswith("ALTER FUNCTION public.") and
           statement.endswith(" OWNER TO "+legacy+";") and
           len(statement)<2000,"UNTRUSTED_FUNCTION_DDL_SHAPE_"+lane)
      text(db,statement)
     need(text(db,"SELECT count(*) FROM pg_tables WHERE schemaname='public' AND tableowner='"+legacy+"'")==str(total),
          "FULL_PUBLIC_TABLE_OWNER_MODEL_MISSING_"+lane)
     need(text(db,"SELECT count(*) FROM pg_sequences WHERE schemaname='public' AND sequenceowner='"+legacy+"'")==str(EXPECTED_SEQUENCES[lane]),
          "FULL_PUBLIC_SEQUENCE_OWNER_MODEL_MISSING_"+lane)
     need(text(db,"SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace "
          "WHERE n.nspname='public' AND pg_get_userbyid(p.proowner)='"+legacy+"'")==str(EXPECTED_PUBLIC_FUNCTIONS[lane]),
          "FULL_PUBLIC_FUNCTION_OWNER_MODEL_MISSING_"+lane)
     need(text(db,"SELECT has_table_privilege('"+legacy+"','"+first+"'::regclass,'INSERT,UPDATE,DELETE,TRUNCATE')::int")=="1",
          "LEGACY_OWNER_WRITE_NOT_MODELED_"+lane)
     text("postgres","ALTER DATABASE "+db+" OWNER TO "+neutral)
     text(db,"ALTER SCHEMA public OWNER TO "+neutral)
     text(db,"REVOKE CREATE ON SCHEMA public FROM PUBLIC, "+legacy)
     text(db,"GRANT USAGE ON SCHEMA public TO "+legacy)
     for identifier in finance_names:
      text(db,"ALTER TABLE "+identifier+" OWNER TO "+neutral)
      text(db,"GRANT SELECT ON TABLE "+identifier+" TO "+legacy)
     for identifier in seq_names:text(db,"ALTER SEQUENCE "+identifier+" OWNER TO "+neutral)
     ids=",".join("'"+x.replace("'","''")+"'" for x in finance_names)
     remaining=text(db,
      "SELECT count(*) FROM (SELECT unnest(ARRAY["+ids+"])::regclass rel) f "
      "WHERE has_table_privilege('"+legacy+"',rel,'INSERT,UPDATE,DELETE,TRUNCATE')")
     need(remaining=="0","FINANCE_WRITE_GRANTS_REMAIN_"+lane)
     for protected in extra:
      need(sql(db,"SELECT 1 FROM "+protected+" LIMIT 0",legacy).returncode==0,
           "ASSET_READ_NOT_PRESERVED_"+protected)
      need(sql(db,"UPDATE "+protected+" SET id=id WHERE false",legacy,allow_fail=True).returncode!=0,
           "ASSET_WRITE_WAS_NOT_FENCED_"+protected)
      need(sql(db,"INSERT INTO "+protected+" SELECT * FROM "+protected+" WHERE false",legacy,allow_fail=True).returncode!=0,
           "ASSET_INSERT_WAS_NOT_FENCED_"+protected)
     unprotected=[v for v in all_tables if v not in set(finance_names)]
     need(len(unprotected)==total-expected_finance,"UNPROTECTED_PUBLIC_CENSUS_DRIFT_"+lane)
     rest_ids=",".join("'"+x.replace("'","''")+"'" for x in unprotected)
     need(text(db,"SELECT count(*) FROM (SELECT unnest(ARRAY["+rest_ids+"])::regclass rel) x "
       "WHERE pg_get_userbyid((SELECT relowner FROM pg_class WHERE oid=x.rel))='"+legacy+"' "
       "AND has_table_privilege('"+legacy+"',rel,'INSERT,UPDATE,DELETE,TRUNCATE')")==str(len(unprotected)),
       "LEGITIMATE_UNPROTECTED_APP_OWNER_WRITES_LOST_"+lane)
     # Real read and ZERO-row write statements through actual PostgreSQL
     # permissions, not just has_table_privilege; never mutate user records.
     need(sql(db,"SELECT 1 FROM public.users LIMIT 0",legacy).returncode==0,
          "LEGACY_USERS_SELECT_DENIED_"+lane)
     need(sql(db,"UPDATE public.users SET id=id WHERE false",legacy).returncode==0,
          "LEGACY_USERS_NOOP_UPDATE_DENIED_"+lane)
     need(sql(db,"INSERT INTO public.users SELECT * FROM public.users WHERE false",legacy).returncode==0,
          "LEGACY_USERS_NOOP_INSERT_DENIED_"+lane)
     need(sql(db,"DELETE FROM public.users WHERE false",legacy).returncode==0,
          "LEGACY_USERS_NOOP_DELETE_DENIED_"+lane)
     need(text(db,"SELECT has_schema_privilege('"+legacy+"','public','CREATE')::int")=="0",
          "PUBLIC_SCHEMA_CREATE_ESCAPE_"+lane)
     for identifier in finance_names:
      need(text(db,"SELECT has_table_privilege('"+legacy+"','"+identifier+"'::regclass,'SELECT')::int")=="1",
           "APPROVED_FINANCE_SELECT_NOT_PRESERVED_"+lane)
     for category,statement in {
      "TRUNCATE":"TRUNCATE TABLE "+first,
      "TABLE_DDL":"ALTER TABLE "+first+" ADD COLUMN c03_forbidden INT",
      "PUBLIC_CREATE":"CREATE TABLE public.c03_forbidden (id INT)",
      "ROLE_ESCALATION":"SET ROLE "+neutral,
     }.items():
      need(sql(db,statement,legacy,allow_fail=True).returncode!=0,
           category+"_UNAUTHORIZED_SUCCESS_"+lane)
     need(text(db,"SELECT pg_has_role('"+legacy+"','"+neutral+"','MEMBER')::int")=="0",
          "ROLE_MEMBERSHIP_ESCAPE_"+lane)
     # Roll back the isolated rehearsal. Preserves actual restored financial
     # data and proves the controlled role mapping is reversible.
     for identifier in finance_names:text(db,"ALTER TABLE "+identifier+" OWNER TO "+legacy)
     for identifier in seq_names:text(db,"ALTER SEQUENCE "+identifier+" OWNER TO "+legacy)
     text(db,"GRANT CREATE ON SCHEMA public TO "+legacy)
     text(db,"ALTER SCHEMA public OWNER TO "+EXPECTED_SCHEMA_OWNER[lane])
     text("postgres","ALTER DATABASE "+db+" OWNER TO "+legacy)
     need(text(db,"SELECT count(*) FROM pg_tables WHERE schemaname='public' AND tableowner='"+legacy+"'")==str(total),
          "FULL_TABLE_OWNER_ROLLBACK_INCOMPLETE_"+lane)
     need(text(db,"SELECT count(*) FROM pg_sequences WHERE schemaname='public' AND sequenceowner='"+legacy+"'")==str(EXPECTED_SEQUENCES[lane]),
          "FULL_SEQUENCE_OWNER_ROLLBACK_INCOMPLETE_"+lane)
     need(text(db,"SELECT pg_get_userbyid(nspowner) FROM pg_namespace WHERE nspname='public'")==EXPECTED_SCHEMA_OWNER[lane],
          "REAL_PUBLIC_SCHEMA_OWNER_ROLLBACK_DRIFT_"+lane)
     need(text(db,"SELECT has_table_privilege('"+legacy+"','"+first+"'::regclass,'INSERT,UPDATE,DELETE,TRUNCATE')::int")=="1",
          "ISOLATED_ROLLBACK_NOT_PROVEN_"+lane)
     need(int(text(db,"SELECT count(*) FROM pg_tables WHERE schemaname='public'"))==total,
          "DATA_SCHEMA_DRIFT_AFTER_OWNER_REHEARSAL_"+lane)
     report[lane]={
      "original_full_archive_sha256":sha,
      "actual_complete_age_authenticated":True,
      "actual_full_pg16_restore_exit_zero":True,
      "restored_public_tables":all_tables,
      "finance_named_tables_tested":len(finance_names),
      "finance_sequences_tested":len(seq_names),
      "explicit_new_asset_tables_fenced":list(extra),
      "explicit_new_asset_sequences_fenced":len(extra_seq_identifiers),
      "physical_new_asset_noop_update_insert_denied":True,
      "all_real_public_table_owners_modeled":len(all_tables),
      "all_real_public_sequence_owners_modeled":len(all_sequences),
      "all_real_public_function_owners_modeled":len(public_func_commands),
      "unprotected_operational_tables_owner_writable":len(unprotected),
      "users_zero_row_select_insert_update_delete_physically_passed":True,
      "real_public_schema_owner_rollback_verified":True,
      "new_known_asset_semantic_scope_fully_fenced":True,
      "other_161_unclassified_public_tables_still_not_finance_classified":True,
      "nonpublic_auth_schema_runtime_ownership_modeled":False,
      "full_restored_db_bytes_before_migration":bytes_before,
      "finance_write_denied_after_no_login_owner_migration":True,
      "finance_select_preserved":True,
      "schema_and_role_escape_denied":True,
      "isolated_owner_rollback_verified":True,
      "live_production_db_mutated":False,
     }
     print("PASS_FULL_DATA_OWNER_MIGRATION_AND_ROLLBACK_"+lane.upper(),flush=True)
   finally:
    if started:
     stopped=call([BIN/"pg_ctl","-D",data,"-m","immediate","-w","stop"],timeout=60)
     need(stopped.returncode==0,"PRIVATE_PG16_SHUTDOWN_FAILED")
 data={
  "schema":"aoe2war.central.c03.nov7-asset60-21-full-public-owner-parity-with-operational-noop-write-rehearsal.v5",
  "utc":dt.datetime.now(dt.timezone.utc).isoformat(),
  "status":"PASS_ISOLATED_60_21_ASSET_FULL_PUBLIC_OWNER_PARITY_NOT_PRODUCTION",
  "actual_offhost":"INTEL_MAC_NONROOT",
  "source_rehearsal_helpers_sha256":TOOL_SHA,
  "hd_de_sources_not_jointly_quiesced":True,
  "full_prod_nonfinance_ownership_recreated":False,
  "full_public_schema_table_sequence_function_ownership_recreated":True,
  "nonpublic_auth_role_and_service_operation_not_fully_recreated":True,
  "old_24_10_scope_insufficient":True,
  "new_payout_transfer_table_scope_required":True,
  "semantic_money_column_candidate_scope_required":True,
  "full_financial_codepath_classification_verified":False,
  "actual_production_writer_fence_proven":False,
  "formal_c03_c06_c07_gates_accepted":False,
  "funded_release_authorized":False,
  "production_changed":False,
  "lanes":report
 }
 raw=(json.dumps(data,sort_keys=True,indent=2)+"\n").encode()
 fd=os.open(RESULT,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600)
 with os.fdopen(fd,"wb") as output:output.write(raw);output.flush();os.fsync(output.fileno())
 print("PASS_ISOLATED_NOV7_HD_DE_FULL_DATA_PROTECTION_REHEARSAL")
 print("PRIVATE_C03_REAL_DATA_RECEIPT_SHA256",hashlib.sha256(raw).hexdigest())
 print("FINANCIAL_GATE_ACCEPTED",False)
 return 0

if __name__=="__main__":
 try:sys.exit(main())
 except Exception as exc:
  print("HOLD_INTEL_C03_FULL_DATA_OWNER_REHEARSAL",type(exc).__name__,str(exc)[:260])
  sys.exit(3)

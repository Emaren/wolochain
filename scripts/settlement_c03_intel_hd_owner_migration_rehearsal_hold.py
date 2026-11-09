#!/usr/bin/env python3
"""C03 Intel FileVault exact restored-HD owner/DML simulation. ALWAYS UNFUNDED.

Run only on a stopped COW CLONE of the restored C07 HD postgres data, never
the accepted C07 restore data itself or production. This reproduces the
legacy account as owner of 190/180 objects before moving the 29 identified
finance candidate tables to a locked NOLOGIN role. Explicitly NOT the
complete production role/ACL/writer graph and never a C03 gate close.
"""
from __future__ import annotations
from datetime import datetime,timezone
import hashlib,json,os,platform,re,stat,subprocess,sys
from pathlib import Path

FINANCE=(
"bet_auto_executions","bet_auto_presets","bet_counter_actions",
"bet_market_financial_adjustments","bet_market_founder_bonuses",
"bet_market_integrity_incidents","bet_market_wallets","bet_markets",
"bet_stake_intents","bet_stake_legs","bet_stake_tickets","bet_wagers",
"betting_bot_configs","bounty_claims","bounty_payouts",
"championship_transfer_groups","championship_transfer_seats",
"marketplace_payments","marketplace_tax_payments","pending_wolo_claims",
"pending_wolo_claims_repair_backup_20260610",
"scheduled_match_replay_claims","scheduled_match_settlement_allocations",
"scheduled_match_settlements","trophy_payout_allocations","trophy_payouts",
"war_graph_payout_events","warrior_claims","wolo_indexed_transfers")
EXP_TABLES=190
EXP_SEQS=180
KEYWORDS="(claim|escrow|payout|payment|wolo|withdraw|deposit|bet|balance|refund|settle|wallet|liabil|reserv|ledger|transfer)"
ROOT=Path.home()/".wolo-owner-authority/c03-isolated-hd-writer-rehearsal-20261109"
PG=Path.home()/".local/aoe2war-pg16-16.15/bin"
MODE="wolo.c03.intel-restored-hd-owner-rehearsal-partial-hold.v1"
class Hold(Exception):pass
def need(condition,reason):
 if not condition:raise Hold(reason)
def sh(args,timeout=80):
 p=subprocess.run([str(a) for a in args],capture_output=True,text=True,timeout=timeout)
 need(p.returncode==0,"ISOLATED_PG16_COMMAND_FAILED")
 return p.stdout.strip()
def psql(sock,query,*,fail=True):
 p=subprocess.run([str(PG/"psql"),"-X","-qAt","-v","ON_ERROR_STOP=1",
    "-h",str(sock),"-p","54514","-U","tonyblum","-d","c07_hd_isolated","-c",query],
    capture_output=True,text=True,timeout=45)
 if fail:need(p.returncode==0,"ISOLATED_C03_SQL_FAILED")
 return p
def main():
 need(sys.platform=="darwin" and platform.machine()=="x86_64"
      and os.geteuid()==os.getuid()!=0,"NOT_INTEL_NONROOT")
 need(sh(["fdesetup","status"],12)=="FileVault is On.","FILEVAULT_OFF")
 need(ROOT.is_dir() and not ROOT.is_symlink()
      and stat.S_IMODE(ROOT.stat().st_mode)==0o700
      and ROOT.stat().st_uid==os.getuid(),"PRIVATE_COW_CLONE_MISSING")
 data=ROOT/"pgdata"
 need((data/"PG_VERSION").read_text().strip()=="16","NOT_PG16_CLONE")
 need(not (data/"postmaster.pid").exists(),"COW_CLONE_ALREADY_RUNNING")
 need(not (ROOT/"c03-partial-owner-rehearsal-receipt.json").exists(),
      "REHEARSAL_ALREADY_DONE")
 need(len(FINANCE)==29 and len(set(FINANCE))==29,"BAD_FINANCE_SCOPE")
 sock=ROOT/"socket"
 sock.mkdir(mode=0o700,exist_ok=False)
 started=False
 try:
  opts="-c listen_addresses='' -c unix_socket_directories="+str(sock)
  opts+=" -c unix_socket_permissions=0700 -p 54514"
  sh([PG/"pg_ctl","-D",data,"-o",opts,"-l",ROOT/"postgres.log",
      "-w","start"],100)
  started=True
  q="""SELECT relkind,relname FROM pg_class c
        JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname='public' AND relkind IN ('r','S')
        AND relname ~* '"""+KEYWORDS+"""' ORDER BY relkind,relname"""
  names=psql(sock,q).stdout.strip().splitlines()
  candidates={line.split("|",1)[1] for line in names if line.startswith("r|")}
  need(candidates==set(FINANCE),"FINANCE_TABLE_CENSUS_DRIFT")
  total=psql(sock,"SELECT relkind,count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND relkind IN ('r','S') GROUP BY relkind ORDER BY relkind").stdout.strip()
  need(total in ("S|180\nr|190","r|190\nS|180"),"PUBLIC_SCHEMA_COUNT_DRIFT")
  roles=psql(sock,"SELECT rolname FROM pg_roles WHERE rolname IN ('aoe2hd_user','aoe2war_finance_owner')").stdout.strip()
  need(roles=="","REHEARSAL_ROLE_ALREADY_PRESENT")
  all_table_names=psql(sock,"SELECT relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND relkind='r' ORDER BY relname").stdout.strip().splitlines()
  need(len(all_table_names)==190,"C03_RESTORE_OWNER_BASELINE")
  sequences=psql(sock,"SELECT relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND relkind='S' ORDER BY relname").stdout.strip().splitlines()
  need(len(sequences)==180,"C03_RESTORE_SEQUENCE_BASELINE")
  def ident(name):
   need(re.fullmatch(r"[a-z_][a-z0-9_]*",name) is not None,
        "UNSAFE_SQL_IDENTIFIER")
   return '"'+name+'"'
  sql=["BEGIN;","CREATE ROLE aoe2hd_user LOGIN NOINHERIT;",
       "CREATE ROLE aoe2war_finance_owner NOLOGIN NOINHERIT;",
       "REVOKE CREATE ON SCHEMA public FROM PUBLIC;"]
  for t in all_table_names:
   sql.append("ALTER TABLE public."+ident(t)+" OWNER TO aoe2hd_user;")
  for s in sequences:
   sql.append("ALTER SEQUENCE public."+ident(s)+" OWNER TO aoe2hd_user;")
  for t in FINANCE:
   # Explicitly recreate old DML grants before owner change. Revocation must
   # be effective even when an explicit old owner ACL survives the transfer.
   sql.append("GRANT ALL PRIVILEGES ON TABLE public."+ident(t)+" TO aoe2hd_user;")
   sql.append("ALTER TABLE public."+ident(t)+" OWNER TO aoe2war_finance_owner;")
   sql.append("REVOKE ALL PRIVILEGES ON TABLE public."+ident(t)+" FROM aoe2hd_user;")
  finseq=[s for s in sequences if s.startswith(tuple(t+"_" for t in FINANCE))]
  for s in finseq:
   sql.append("ALTER SEQUENCE public."+ident(s)+" OWNER TO aoe2war_finance_owner;")
   sql.append("REVOKE ALL PRIVILEGES ON SEQUENCE public."+ident(s)+" FROM aoe2hd_user;")
  sql.append("COMMIT;")
  transaction="\n".join(sql)
  psql(sock,transaction)
  # NO default permission should be held by the former legacy owner on finance
  # objects even if original owner ACL bits were explicitly present.
  q="""SELECT c.relname,pg_get_userbyid(c.relowner),
   has_table_privilege('aoe2hd_user',c.oid,'INSERT'),
   has_table_privilege('aoe2hd_user',c.oid,'UPDATE'),
   has_table_privilege('aoe2hd_user',c.oid,'DELETE'),
   has_table_privilege('aoe2hd_user',c.oid,'TRUNCATE')
   FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
   WHERE n.nspname='public' AND c.relkind='r' AND c.relname IN
   ("""+",".join("'"+x+"'" for x in FINANCE)+""") ORDER BY c.relname"""
  statuses=psql(sock,q).stdout.strip().splitlines()
  need(len(statuses)==29,"EXACT_FINANCE_OWNER_COVERAGE_NOT_29")
  need(all(len(line.split("|"))==6 and line.split("|")[1]=="aoe2war_finance_owner"
        and line.split("|")[2:]==["f","f","f","f"] for line in statuses),
       "EXPLICIT_OWNER_GRANT_SURVIVED")
  seqsql="""SELECT c.relname,pg_get_userbyid(c.relowner),
   has_sequence_privilege('aoe2hd_user',c.oid,'USAGE'),
   has_sequence_privilege('aoe2hd_user',c.oid,'UPDATE')
   FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
   WHERE n.nspname='public' AND c.relkind='S' AND
   pg_get_userbyid(c.relowner)='aoe2war_finance_owner' ORDER BY c.relname"""
  seqs=psql(sock,seqsql).stdout.strip().splitlines()
  need(len(seqs)>=27 and all(x.split("|")[2:]==["f","f"] for x in seqs),
       "EX_LEGACY_OWNER_CAN_MUTATE_FINANCE_SEQUENCE")
  denied=psql(sock,"BEGIN;SET LOCAL ROLE aoe2hd_user; DELETE FROM public.pending_wolo_claims WHERE false;",fail=False)
  need(denied.returncode!=0 and "permission denied" in denied.stderr,
       "LEGACY_OWNER_FINANCE_DELETE_NOT_DENIED")
  sql="""SELECT
    has_table_privilege('aoe2hd_user','public.users','UPDATE') AS users_legacy_writable,
    has_schema_privilege('aoe2hd_user','public','CREATE') AS legacy_schema_create,
    has_table_privilege('aoe2war_finance_owner','public.pending_wolo_claims','INSERT') AS finance_owner_insert"""
  flags=psql(sock,sql).stdout.strip().split("|")
  need(flags==["t","f","t"],"PARTIAL_FENCE_SHAPE_DRIFT")
  report={
   "schema":MODE,"observed_utc":datetime.now(timezone.utc).isoformat(),
   "source_sha256":hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
   "isolation":"FileVault_x86_64_unix_socket_only_APFS_COW_clone_from_C07",
   "source_pg16_schema_tables":190,"source_pg16_sequences":180,
   "scope_exact_finance_tables":29,
   "migrated_finance_sequences":len(seqs),
   "finance_names_sha256":hashlib.sha256("\n".join(FINANCE).encode()).hexdigest(),
   "legacy_owner_finance_table_DML_denied":True,
   "legacy_owner_finance_sequence_mutation_denied":True,
   "physical_old_owner_claim_delete_sqlstate_denied":True,
   "old_owner_users_table_still_writable":True,
   "legacy_schema_create_denied":True,"new_finance_owner_is_NOLOGIN":True,
   "source_pg_owner_grants_reconstructed_from_live":False,
   "source_nonfinance_runtime_connections_and_steam_tested":False,
   "production_sql_role_modified":False,
   "financial_signer_activated":False,
   "c03_financial_writer_gate_closed":False,
   "c06_c07_final_financial_backup_gate_closed":False,
   "funded_permit_authorized":False
  }
 finally:
  if started:
   sh([PG/"pg_ctl","-D",data,"-m","fast","-w","stop"],80)
 with open(ROOT/"c03-partial-owner-rehearsal-receipt.json","xb") as f:
  b=(json.dumps(report,sort_keys=True,indent=2)+"\n").encode()
  os.fchmod(f.fileno(),0o600);f.write(b);f.flush();os.fsync(f.fileno())
 print("PASS_C03_INTEL_REAL_RESTORED_OWNER_MIGRATION_PARTIAL_SCOPE",len(statuses),len(seqs))
 print("PASS_C03_OLD_OWNER_ACTUAL_CLAIM_DELETE_HARD_DENIED")
 print("ROOT_PRIVATE_RECEIPT_SHA256",hashlib.sha256(b).hexdigest())
 print("HOLD_C03_USERS_AND_ORIGINAL_PG_GRANTS_AND_STEAM_NOT_FENCED")
if __name__=="__main__":
 try:main()
 except (Hold,FileNotFoundError,PermissionError,subprocess.SubprocessError) as exc:
  print("HOLD_C03_RESTORED_HD_OWNER_FENCE",str(exc) if isinstance(exc,Hold) else "HOST_IO_FAILURE")
  sys.exit(3)

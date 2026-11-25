#!/usr/bin/env python3
"""C04 physical legacy private archive full-data restore, never payment authority.

Runs ONLY as unprivileged owner on FileVault Intel x86_64 Mac.
Restores PgCustom pre-data+data (FK post-data excluded for 12-table subset).
No network listeners, no live database changes, no owner private key export.
"""
from __future__ import annotations
import hashlib,json,os,platform,stat,subprocess,sys
from datetime import datetime,timezone
from pathlib import Path

ROOT=Path.home()/'.wolo-owner-authority/c04-historical-quarantine-20261109'
CIPHER=ROOT/'c04-original-hd-12-financial-tables.pgcustom.age'
AGE=Path('/usr/local/bin/age')
KEY=Path.home()/'.wolo-owner-authority/c06-filevault-recovery/c06-recovery-ed25519'
PG=Path.home()/'.local/aoe2war-pg16-16.15/bin'
EXPECTED_SHA='d0f785629b6ff09d356126329ab211fb0d50426922b37c5549cc3c62ba6efc8f'
EXPECTED_SIZE=1805482
TABLES=(
 'pending_wolo_claims','pending_wolo_claims_repair_backup_20260610',
 'bet_market_founder_bonuses','bet_wagers','bet_markets',
 'bet_market_wallets','bet_market_financial_adjustments',
 'bet_market_integrity_incidents','wolo_indexed_transfers',
 'scheduled_match_settlements','trophy_payouts','bounty_claims',
)
class Hold(Exception):pass
def check(condition,message):
 if not condition:raise Hold(message)
def run(args,timeout=90,stdin=None):
 p=subprocess.run([str(a) for a in args],input=stdin,capture_output=True,
                  timeout=timeout)
 check(p.returncode==0,'ISOLATED_PG16_TOOL_OR_SQL_FAILED')
 return p.stdout
def main():
 check(sys.platform=='darwin' and platform.machine()=='x86_64'
       and os.geteuid()==os.getuid()!=0,'INTEL_NONROOT_ONLY')
 check(run(['/usr/bin/fdesetup','status'],12).strip()==b'FileVault is On.',
       'FILEVAULT_REQUIRED')
 check(ROOT.is_dir() and not ROOT.is_symlink()
       and stat.S_IMODE(ROOT.stat().st_mode)==0o700
       and ROOT.stat().st_uid==os.geteuid(),'PRIVATE_ROOT_REQUIRED')
 check(CIPHER.is_file() and not CIPHER.is_symlink(),'CIPHERTEXT_MISSING')
 s=CIPHER.lstat()
 check(s.st_size==EXPECTED_SIZE and s.st_nlink==1 and
       s.st_uid==os.geteuid() and stat.S_IMODE(s.st_mode)==0o600,
       'OWNER_CIPHER_FILE_IDENTITY_CHANGED')
 check(hashlib.sha256(CIPHER.read_bytes()).hexdigest()==EXPECTED_SHA,
       'ENCRYPTED_ARCHIVE_SHA256_DRIFT')
 check(AGE.is_file() and KEY.is_file(),'INTEL_RECOVERY_IDENTITY_MISSING')
 check(len(TABLES)==12 and len(set(TABLES))==12,'ARCHIVE_TABLE_SCOPE_DRIFT')
 for tool in ('initdb','pg_ctl','createdb','pg_restore','psql'):
  check((PG/tool).is_file(),'POSTGRES16_BINARY_MISSING')
 data=ROOT/'pgdata'
 sock=ROOT/'socket'
 receipt=ROOT/'c04-legacy-historic-source-restore-receipt.json'
 check(not data.exists() and not sock.exists() and not receipt.exists(),
       'ISOLATED_RESTORE_ALREADY_OCCURRED')
 sock.mkdir(mode=0o700)
 started=False
 db='c04_legacy_private'
 port='54516'
 try:
  run([PG/'initdb','-A','trust','-U','tonyblum','-D',data],180)
  flags="-c listen_addresses='' -c unix_socket_directories="+str(sock)
  flags+=" -c unix_socket_permissions=0700 -p "+port
  run([PG/'pg_ctl','-D',data,'-o',flags,'-l',ROOT/'postgres.log',
      '-w','start'],120)
  started=True
  run([PG/'createdb','-h',sock,'-p',port,'-U','tonyblum',
       '-T','template0',db],60)
  decrypt=subprocess.Popen([str(AGE),'-d','-i',str(KEY),str(CIPHER)],
            stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
  try:
   restored=subprocess.run([str(PG/'pg_restore'),'--exit-on-error',
      '--no-owner','--no-acl','--section=pre-data','--section=data',
      '-h',str(sock),'-p',port,'-U','tonyblum','-d',db],
      stdin=decrypt.stdout,capture_output=True,timeout=1800)
   decrypt.stdout.close()
   arc=decrypt.wait(timeout=35)
  except BaseException:
   decrypt.kill();decrypt.wait(timeout=12);raise
  check(arc==0 and restored.returncode==0,
        'FULL_AUTHENTICATED_AGE_AND_PGCUSTOM_DATA_RESTORE_FAILED')
  def sql(q):
   return run([PG/'psql','-X','-qAt','-v','ON_ERROR_STOP=1',
    '-h',sock,'-p',port,'-U','tonyblum','-d',db,'-c',q],45).decode().strip()
  names=sql("SELECT tablename FROM pg_catalog.pg_tables WHERE schemaname='public' ORDER BY tablename").splitlines()
  check(set(names)==set(TABLES),'RESTORED_TABLE_LIST_NOT_EXACT')
  agg=sql("""SELECT status,count(*),coalesce(sum(amount_wolo),0)
     FROM public.pending_wolo_claims GROUP BY status ORDER BY status""")
  counts=sql("""SELECT count(*),coalesce(sum(amount_wolo),0)
       FROM public.pending_wolo_claims WHERE status='claimed'
       AND NULLIF(BTRIM(COALESCE(payout_tx_hash,'')),'') IS NULL""")
  check(agg=='claimed|1312|16163045\npending|948|993289\nrescinded|193|1569682',
        'RESTORED_ORIGINAL_CLAIM_STATUS_SCOPE_DRIFT')
  check(counts=='69|120443','HASHLESS_UNKNOWN_CLAIM_SCOPE_DRIFT')
  c04ids=sql("""SELECT id,status,claim_kind,amount_wolo,
          coalesce(payout_tx_hash,'') FROM public.pending_wolo_claims
          ORDER BY id""")
  check(len(c04ids.splitlines())==2453,'ALL_ORIGINAL_CLAIM_IDS_NOT_RESTORED')
  check(sql("SELECT CASE WHEN current_setting('listen_addresses')='' THEN 1 ELSE 0 END")=='1',
        'ISOLATED_TCP_LISTENER_ENABLED')
  rowcounts={}
  for table in TABLES:
   check(table.replace('_','').isalnum(),'UNSAFE_IDENTIFIER')
   rowcounts[table]=int(sql('SELECT count(*) FROM public."'+table+'"'))
  report={
   'schema':'wolo.c04.intel-filevault-12-historic-table-actual-restoration.v1',
   'verified_utc':datetime.now(timezone.utc).isoformat(),
   'archive_cipher_sha256':EXPECTED_SHA,'archive_cipher_bytes':EXPECTED_SIZE,
   'executed_source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
   'actual_restored_12_table_row_counts':rowcounts,
   'all_2453_legacy_claim_identity_commitment_sha256':
      hashlib.sha256((c04ids+'\n').encode()).hexdigest(),
   'claimed_hashless_unknown_rows':69,'claimed_hashless_unknown_wolo':120443,
   'pending_legacy_rows':948,'pending_legacy_wolo':993289,
   'claimed_with_hash_rows':1243,'rescinded_rows':193,
   'no_password_or_private_key_exported':True,'full_age_authenticated':True,
   'full_pgcustom_predata_data_restored':True,
   'postdata_fk_indexes_constraints_restored':False,
   'tcp_disabled':True,'production_modified':False,
   'all_legacy_claims_adjudicated':False,
   'old_8092_8093_live_mask_independently_verified_here':False,
   'native_funded_admission_verified_here':False,
   'c04_formal_gate_closed':False,'funded_release_permitted':False
  }
 finally:
  if started:
   run([PG/'pg_ctl','-D',data,'-m','fast','-w','stop'],90)
 b=(json.dumps(report,indent=2,sort_keys=True)+'\n').encode()
 fd=os.open(receipt,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
 with os.fdopen(fd,'wb') as f:f.write(b);f.flush();os.fsync(f.fileno())
 print('PASS_C04_PRIVATE_12_TABLE_FULL_HISTORIC_DATA_RESTORED',len(TABLES))
 print('PASS_C04_ALL_LEGACY_CLAIMS',len(c04ids.splitlines()),counts.replace('|','/'))
 print('ROOT_PRIVATE_C04_INTEL_RESTORE_RECEIPT_SHA256',hashlib.sha256(b).hexdigest())
 print('HOLD_C04_FINAL_GOVERNANCE_AND_SOURCE_PERIMETER_ACCEPTANCE')
if __name__=='__main__':
 try:main()
 except (Hold,FileNotFoundError,PermissionError,subprocess.SubprocessError) as err:
  print('HOLD_C04_INTEL_RESTORED_HISTORIC_SOURCE',str(err) if isinstance(err,Hold) else 'HOST_ERROR')
  sys.exit(3)

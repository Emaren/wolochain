"""C04 byte-identical physically executed encrypted legacy evidence boundary."""
from pathlib import Path
import hashlib
import re
import subprocess
import unittest

ROOT=Path(__file__).resolve().parents[1]
RUN=ROOT/'scripts'
SOURCES={
 'settlement_c04_legacy_12table_public_key_age_quarantine_capture.sh':
 'd2d1a615c358a92181cbacb858ed35e1d2162a019aeda10db6abab7cc20ad75e',
 'settlement_c04_intel_filevault_legacy12_restore_hold.py':
 'a6ddb19fb1c946e62effa966945da5ee2ef967058870ef62ea6c9876305f7c62',
 'settlement_c04_legacy_30table_public_key_age_quarantine_capture.sh':
 '4066ad25ee253246cbca3dcb8f69b82abe39a7c33afbf8869a9cffc9de1bb600',
 'settlement_c04_intel_filevault_legacy30_restore_hold.py':
 '5aa8a30dac7c82a0c81e832f376efe327d8aca5a659728c6b4e619d45231b977',
}
class HistoricalQuarantineSource(unittest.TestCase):
 def test_all_physically_executed_source_sha(self):
  for name,expected in SOURCES.items():
   self.assertEqual(hashlib.sha256((RUN/name).read_bytes()).hexdigest(),
                    expected,name)
 def test_all_archival_scripts_fail_closed_and_encrypt_only(self):
  for suffix,n in [('12',12),('30',30)]:
   s=(RUN/f'settlement_c04_legacy_{suffix}table_public_key_age_quarantine_capture.sh').read_text()
   self.assertEqual(len(re.findall(r'--table=public\.',s)),n)
   for required in (
    'set -o pipefail','umask 077','pg_dump','-Fc -Z3',
    '/usr/bin/age -R "$m1" -R "$intel" -o "$part"',
    'HOLD_C04_LEGACY_PAYMENT_NOT_FENCED',
    'C04_FINANCIAL_LISTENER_OPEN','-p LoadState --value',
    'sha256','os.O_NOFOLLOW','os.O_EXCL',
    "'c04_formal_gate_closed':False",
    "'financial_release_authorized':False",
    "'historical_claim_rows_status_changed':False",
   ):self.assertIn(required,s)
   r=subprocess.run(['bash','-n',str(RUN/f'settlement_c04_legacy_{suffix}table_public_key_age_quarantine_capture.sh')],
                    capture_output=True,timeout=7)
   self.assertEqual(r.returncode,0,r.stderr)
 def test_30_table_full_source_scope_includes_mixed_users_and_claims(self):
  s=(RUN/'settlement_c04_legacy_30table_public_key_age_quarantine_capture.sh').read_text()
  for required in ('--table=public.users','--table=public.pending_wolo_claims ',
       '--table=public.trophy_payout_allocations',
       '--table=public.scheduled_match_settlement_allocations',
       '--table=public.wolo_indexed_transfers'):
   self.assertIn(required,s)
 def test_intel_restores_reject_nonfilevault_or_untrusted_archive(self):
  for suffix,n in [('12',12),('30',30)]:
   s=(RUN/f'settlement_c04_intel_filevault_legacy{suffix}_restore_hold.py').read_text()
   for required in (
     "platform.machine()=='x86_64'",'FileVault is On.',
     'EXPECTED_SHA','EXPECTED_SIZE','--exit-on-error',
     "'--section=pre-data','--section=data'",
     'decrypt.wait(timeout=35)',"arc==0 and restored.returncode==0",
     'RESTORED_TABLE_LIST_NOT_EXACT',
     'HASHLESS_UNKNOWN_CLAIM_SCOPE_DRIFT','ALL_ORIGINAL_CLAIM_IDS_NOT_RESTORED',
     'tcp_disabled',"'c04_formal_gate_closed':False",
     "'funded_release_permitted':False",
   ):self.assertIn(required,s)
   self.assertIn(f'len(TABLES)=={n}',s)
 def test_source_never_transfers_value_or_unmasks_legacy(self):
  for name in SOURCES:
   s=(RUN/name).read_text()
   for forbidden in ('wolochaind tx','systemctl start',
       'systemctl unmask','DROP TABLE','ALTER ROLE',
       'DELETE FROM public.pending_wolo_claims',
       'UPDATE public.pending_wolo_claims','8092/settlement',
       'PRIVATE_KEY_EXPORTED true'):
    self.assertNotIn(forbidden,s)
if __name__=='__main__':unittest.main()

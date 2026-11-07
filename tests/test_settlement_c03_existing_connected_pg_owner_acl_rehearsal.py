"""C03 existing backend physical PG16 permission-cache source regression.

Runs only static fail-closed checks in CI; physical test is done on Intel,
using the exact SHA-pinned private disposable server receipt.
"""
import hashlib
import importlib.util
from pathlib import Path
from unittest.mock import patch
import unittest
P=Path(__file__).resolve().parents[1]/'scripts/settlement_c03_existing_connected_pg_owner_acl_rehearsal.py'
spec=importlib.util.spec_from_file_location('c03_backend_acl',P)
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

class PreconnectedPrivilegeDenialTests(unittest.TestCase):
 def test_physical_controller_exact_executed_source(self):
  self.assertEqual(hashlib.sha256(P.read_bytes()).hexdigest(),
      'c0a0c4b77229214e90a9065d2b91db0a599fde9424c3d64829c9e4cb00aef6d7')

 def test_only_intel_nonroot_with_own_private_root(self):
  with patch.object(m.sys,'platform','linux'):
   with self.assertRaises(RuntimeError):m.main()
  with patch.object(m.platform,'machine',return_value='arm64'):
   with self.assertRaises(RuntimeError):m.main()
  with patch.object(m.os,'geteuid',return_value=0):
   with self.assertRaises(RuntimeError):m.main()

 def test_real_backend_persists_across_owner_transition(self):
  s=P.read_text()
  for proof in ('SELECT pg_backend_pid();','PID_BEFORE','PID_AFTER',
     'PID_RESTORED','EXISTING_PG_SESSION_REPLACED',
     'BACKEND_CHANGE_DURING_ROLLBACK','same_backend_pid_before_during_after'):
   self.assertIn(proof,s)
  self.assertIn('ALTER TABLE public.finance OWNER TO c03_neutral',s)
  self.assertIn('ALTER TABLE public.finance OWNER TO c03_legacy',s)
  self.assertIn('GRANT SELECT ON public.finance TO c03_legacy',s)

 def test_same_backend_acl_invalidation_and_reconnect(self):
  s=P.read_text()
  self.assertIn('FINANCE_FENCED',s)
  self.assertIn('FINANCE_INSERT_FENCED',s)
  self.assertIn('EXISTING_BACKEND_FINANCIAL_DML_NOT_DENIED_',s)
  self.assertIn('EXISTING_BACKEND_INSERT_NOT_DENIED_',s)
  self.assertIn('NEW_CONNECTION_FINANCIAL_DML_NOT_DENIED',s)
  self.assertIn('rc=="42501"',s)
  self.assertIn('"finance_owner_switch_to_neutral_nologin":True',s)
  self.assertIn('actor="c03_legacy",check=False',s)
  self.assertIn('FINANCE_RESTORED',s)

 def test_protect_nonfinance_and_zero_changes(self):
  s=P.read_text()
  self.assertIn('UPDATE public.users SET id=id WHERE false;',s)
  self.assertIn('UPDATE public.finance SET id=id WHERE false;',s)
  self.assertIn('INSERT INTO public.finance SELECT * FROM public.finance WHERE false;',s)
  self.assertIn('SELECT count(*) FROM public.finance',s)
  self.assertIn('table_row_counts_remained_zero',s)
  self.assertIn('SAME_BACKEND_NONFINANCE_WRITE_LOST',s)
  self.assertIn('ZERO_ROW_TEST_MUTATED_DATA',s)
  for token in ('"live_c03_finance_writer_fenced":False',
                '"coordinated_c06_backup_captured":False',
                '"formal_c03_c06_c07_accepted":False',
                '"funded_release_authorized":False'):
   self.assertIn(token,s)

 def test_socket_only_no_production_network_or_services(self):
  s=P.read_text()
  self.assertIn("listen_addresses=''",s)
  self.assertIn('unix_socket_permissions=0700',s)
  self.assertIn('TemporaryDirectory',s)
  self.assertIn('os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_WRONLY',s)
  self.assertIn('"16."',s)
  self.assertIn('RESULT.exists()',s)
  for unsafe in ('root@hel1','pg_terminate_backend','systemctl restart',
                 'http://','https://','8094','8095','/var/lib/postgresql'):
   self.assertNotIn(unsafe,s)

if __name__=='__main__':unittest.main()

"""C03 payout/transfer source-scope protection. Real SQL stays READ ONLY."""
from __future__ import annotations
import importlib.util
from pathlib import Path
from unittest.mock import patch
import unittest
P=Path(__file__).resolve().parents[1]/'scripts/settlement_c03_expanded_finance_universe_hold.py'
spec=importlib.util.spec_from_file_location('c03payout',P)
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

def fixture(db='aoe2hd_db'):
 x=m.EXPECTED[db]
 base=[f'wolo_ledger_{i}' for i in range(x['tables']-len(x['newly_included']))]
 all_names=base+list(x['newly_included'])
 rows=[f"META|{db}|{x['owner']}|{x['schema_owner']}|1|1"]
 rows += [f'TABLE|{name}|{x["owner"]}' for name in all_names]
 rows += [f'EXTRA|{name}' for name in x['newly_included']]
 rows += [f'SEQUENCE|public.wolo_sequence_{i}|{x["owner"]}|{all_names[i%len(all_names)]}'
          for i in range(x['sequences'])]
 rows += [f'TRIGGER|{all_names[0]}|wolo_trig_{i}|public.wolo_func_{i}|postgres|0'
          for i in range(x['triggers'])]
 rows += [f'VIEW|aoe2war_public_v1.wolo_view_{i}|postgres' for i in range(x['views'])]
 return '\n'.join(rows)+'\n'

class ExpandedFinanceAudit(unittest.TestCase):
 def test_exact_hd_de_realistic_fixture(self):
  for db in m.EXPECTED:
   with self.subTest(db=db):
    r=m.parse(fixture(db),db)
    self.assertEqual(r['finance_related_tables'],m.EXPECTED[db]['tables'])
    self.assertEqual(r['attached_sequences'],m.EXPECTED[db]['sequences'])
    self.assertEqual(r['newly_included_tables'],sorted(m.EXPECTED[db]['newly_included']))
    self.assertTrue(r['legacy_can_create_public_objects'])

 def test_readonly_transaction_and_expanded_query(self):
  for db in m.EXPECTED:
   s=m.query(db)
   self.assertIn('REPEATABLE READ READ ONLY',s)
   self.assertIn('ROLLBACK;',s)
   self.assertIn('payout|transfer',s)
   self.assertNotIn('ALTER TABLE ',s)
   self.assertNotIn('REVOKE ',s)
   self.assertNotIn('INSERT INTO ',s)
  with self.assertRaises(m.Hold):m.query('postgres')

 def test_missing_extra_or_exact_expected_payment_name_rejected(self):
  raw=fixture()
  for bad in [
   raw.replace('EXTRA|bounty_payouts\n',''),
   raw.replace('TABLE|bounty_payouts|aoe2hd_user\n',''),
   raw.replace('EXTRA|bounty_payouts','EXTRA|bounty_disbursements'),
   raw.replace('TABLE|bounty_payouts','TABLE|bounty_disbursements'),
   raw+'EXTRA|unrecognized_payout',
  ]:
   with self.assertRaises(m.Hold):m.parse(bad,'aoe2hd_db')

 def test_owner_schema_roles_and_escapes_refused(self):
  raw=fixture()
  for bad in [
   raw.replace('META|aoe2hd_db|aoe2hd_user','META|aoe2hd_db|postgres'),
   raw.replace('pg_database_owner','postgres'),
   raw.replace('pg_database_owner|1|1','pg_database_owner|1|0'),
   raw.replace('pg_database_owner|1|1','pg_database_owner|0|1'),
   raw.replace('TABLE|bounty_payouts|aoe2hd_user','TABLE|bounty_payouts|postgres'),
   raw.replace('SEQUENCE|public.wolo_sequence_0|aoe2hd_user','SEQUENCE|public.wolo_sequence_0|postgres'),
   raw.replace('public.wolo_func_0|postgres|0','public.wolo_func_0|postgres|1'),
   raw.replace('TRIGGER|wolo_ledger_0','TRIGGER|unknown_table'),
   raw.replace('SEQUENCE|public.wolo_sequence_0|aoe2hd_user|wolo_ledger_0',
               'SEQUENCE|public.wolo_sequence_0|aoe2hd_user|external_table'),
  ]:
   with self.assertRaises(m.Hold):m.parse(bad,'aoe2hd_db')

 def test_counts_and_duplication_refused(self):
  raw=fixture()
  for bad in [
   raw.replace('SEQUENCE|public.wolo_sequence_0|aoe2hd_user|wolo_ledger_0\n',''),
   raw.replace('TRIGGER|wolo_ledger_0|wolo_trig_0|public.wolo_func_0|postgres|0\n',''),
   raw.replace('VIEW|aoe2war_public_v1.wolo_view_0|postgres\n',''),
   raw+'TABLE|wolo_ledger_0|aoe2hd_user\n',
   raw.replace('TABLE|bounty_payouts','TABLE|bounty_payouts;DROP'),
  ]:
   with self.assertRaises(m.Hold):m.parse(bad,'aoe2hd_db')

 def test_nonroot_and_failure_fail_closed(self):
  with patch.object(m.os,'geteuid',return_value=501):
   with self.assertRaises(m.Hold):m.observe('aoe2hd_db')
  class Fake:
   returncode=0
   stderr=''
   stdout=fixture()
  with patch.object(m.os,'geteuid',return_value=0),\
       patch.object(m.subprocess,'run',return_value=Fake()) as call:
   self.assertEqual(m.observe('aoe2hd_db')['finance_related_tables'],30)
   self.assertEqual(call.call_args.args[0][:4],['runuser','-u','postgres','--'])

if __name__=='__main__':unittest.main()

"""C03 semantic financial column candidate omission must always hold."""
from __future__ import annotations
import importlib.util
from pathlib import Path
from unittest.mock import patch
import unittest
P=Path(__file__).resolve().parents[1]/'scripts/settlement_c03_semantic_finance_columns_hold.py'
spec=importlib.util.spec_from_file_location('c03semantic',P)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

def fixture(db='aoe2hd_db'):
 return '\n'.join(f'{name}|amount_wolo,tx_hash'
                  for name in m.EXPECTED[db])+'\n'

class SemanticCoverageHoldTests(unittest.TestCase):
 def test_exact_scope_is_nonempty_and_source_bound(self):
  self.assertEqual(len(m.EXPECTED['aoe2hd_db']),24)
  self.assertEqual(len(m.EXPECTED['aoe2de_db']),9)
  for db in m.EXPECTED:
   out=m.parse(fixture(db),db)
   self.assertFalse(out['all_candidates_finance_classified'])
   self.assertFalse(out['all_candidates_fenced'])
 def test_query_is_read_only(self):
  for db in m.EXPECTED:
   sql=m.query(db)
   self.assertIn('REPEATABLE READ READ ONLY',sql)
   self.assertIn('ROLLBACK;',sql)
   for bad in ('ALTER TABLE','DELETE FROM','INSERT INTO','GRANT '):
    self.assertNotIn(bad,sql)
  with self.assertRaises(m.Hold):m.query('postgres')
 def test_missing_extra_duplicate_and_forged_tables_refused(self):
  raw=fixture()
  for bad in (
   raw.replace('bounty_events|amount_wolo,tx_hash\n',''),
   raw+'new_coin_money|amount_wolo\n',
   raw+'bounty_events|amount_wolo,tx_hash\n',
   raw.replace('bounty_events','wolo_bounty_events'),
   raw.replace('bounty_events','bounty_events; DROP'),
  ):
   with self.assertRaises(m.Hold):m.parse(bad,'aoe2hd_db')
 def test_no_unbounded_columns_or_forged_schema(self):
  raw=fixture()
  for bad in (
   raw.replace('amount_wolo,tx_hash','amount_wolo,tx_hash,tx_hash'),
   raw.replace('amount_wolo,tx_hash','nonmoney_column,tx_hash'),
   raw+'x'*33000,
  ):
   with self.assertRaises(m.Hold):m.parse(bad,'aoe2hd_db')
 def test_local_root_and_fail_closed_even_on_success(self):
  with patch.object(m.os,'geteuid',return_value=501):
   with self.assertRaises(m.Hold):m.inspect('aoe2hd_db')
  class P:
   returncode=0;stderr='';stdout=fixture()
  with patch.object(m.os,'geteuid',return_value=0),\
       patch.object(m.subprocess,'run',return_value=P()) as proc:
   self.assertEqual(m.inspect('aoe2hd_db')['money_column_bearing_table_count'],24)
   self.assertEqual(proc.call_args.args[0][:4],['runuser','-u','postgres','--'])
if __name__=='__main__':unittest.main()

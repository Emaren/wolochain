"""C03 Intel-only expanded finance+payout schema owner DDL rehearsal guard."""
from __future__ import annotations
import importlib.util
from pathlib import Path
from unittest.mock import patch
import unittest
P=Path(__file__).resolve().parents[1]/'scripts/settlement_c03_intel_expanded_schema_owner_rehearsal.py'
spec=importlib.util.spec_from_file_location('c03_intel_expanded',P)
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

class ExpandedIntelSchemaTests(unittest.TestCase):
 def test_separate_exact_archive_pins_and_expanded_counts(self):
  self.assertEqual(m.PINS['hd'][2],30)
  self.assertEqual(m.PINS['de'][2],11)
  self.assertEqual(m.SEQ_PINS,{'hd':29,'de':11})
  for lane in ('hd','de'):
   self.assertEqual(len(m.PINS[lane][1]),64)
  self.assertNotEqual(m.PINS['hd'][1],m.PINS['de'][1])
 def test_all_seven_missing_payout_identifiers_mandatory(self):
  self.assertEqual(len(m.PAYOUT_TABLES['hd']),6)
  self.assertEqual(len(m.PAYOUT_TABLES['de']),1)
  for lane in ('hd','de'):
   for name in m.PAYOUT_TABLES[lane]:
    self.assertRegex(name,r'^public\.[a-z_]+$')
    self.assertRegex(name,r'payout|transfer')
    self.assertRegex(name,m.FINANCE)
 def test_platform_root_and_unsafe_catalog_denials(self):
  with patch.object(m.sys,'platform','linux'),self.assertRaises(m.Hold):
   m.admission()
  with patch.object(m.os,'geteuid',return_value=0),self.assertRaises(m.Hold):
   m.admission()
  with self.assertRaises(m.Hold):
   m.check_exact_identifiers(['public.payouts;drop'])
  with self.assertRaises(m.Hold):
   m.check_exact_identifiers(['public.payouts','public.payouts'])
 def test_source_guards_stay_nonfinancial_and_offhost(self):
  src=P.read_text()
  self.assertIn("listen_addresses='' ",src)
  self.assertIn('MISSING_EXPANDED_PAYOUT_OR_TRANSFER_TABLE',src)
  self.assertIn('EXPANDED_SEQUENCE_COUNT_DRIFT',src)
  self.assertIn('prior24Hd10DeRehearsalsInsufficientForC03',src)
  self.assertIn('financialReleaseAuthorized',src)
  for bad in ('root@hel1','pg_terminate_backend','DROP DATABASE aoe2hd_db',
              '8094','8092','PrivateKey','--approve-funded'):
   self.assertNotIn(bad,src)

if __name__=='__main__':unittest.main()

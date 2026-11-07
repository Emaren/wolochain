"""C03 conservative owner test has mandatory 54/20 candidate scope, Intel only."""
from __future__ import annotations
import importlib.util
from pathlib import Path
from unittest.mock import patch
import unittest

P=Path(__file__).resolve().parents[1]/"scripts/settlement_c03_intel_conservative_owner_rehearsal.py"
spec=importlib.util.spec_from_file_location("c03_intel_conservative",P)
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
class IntelConservativeSource(unittest.TestCase):
 def test_exact_pinned_sources(self):
  self.assertEqual(m.PINS['hd'][2],54)
  self.assertEqual(m.PINS['de'][2],20)
  self.assertEqual(m.SEQ_PINS,{'hd':52,'de':20})
  self.assertEqual(len(m.PINS['hd'][1]),64)
  self.assertEqual(len(m.PINS['de'][1]),64)
  self.assertNotEqual(m.PINS['hd'][1],m.PINS['de'][1])
 def test_semantic_or_finance_name_query(self):
  s=P.read_text()
  self.assertIn('EXISTS (',s)
  self.assertIn('pg_attribute',s)
  self.assertIn('SEMANTIC=',s)
  self.assertIn('EXPANDED_SEQUENCE_COUNT_DRIFT',s)
  self.assertIn('FINANCE_TABLE_COUNT_DRIFT',s)
  self.assertIn('prior30Hd11DeRehearsalsInsufficientForC03',s)
  self.assertIn('full_app_money_codepath_categorization_proven',s)
 def test_intel_only_nonroot_not_production(self):
  with patch.object(m.sys,'platform','linux'),self.assertRaises(m.Hold):
   m.admission()
  with patch.object(m.os,'geteuid',return_value=0),self.assertRaises(m.Hold):
   m.admission()
  src=P.read_text()
  self.assertIn("listen_addresses='' ",src)
  for banned in ("root@hel1","pg_terminate_backend",
                 "DROP DATABASE aoe2hd_db","--approve-funded",
                 "8092","8094","--force-production"):
   self.assertNotIn(banned,src)
 def test_quote_catalog_identifiers_no_sql_injection(self):
  good=['public.marketplace_payments','public."Capitalized"']
  self.assertEqual(m.check_exact_identifiers(good),good)
  for bad in ("public.marketplace_payments;DROP","pg_catalog.escrow","public.",
              "public.missing-space x",):
   with self.subTest(bad=bad),self.assertRaises(m.Hold):
    m.check_exact_identifiers([bad])
if __name__=="__main__":unittest.main()

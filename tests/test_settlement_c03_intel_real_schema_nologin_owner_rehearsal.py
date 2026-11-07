"""C03 real-schema INTEL-only owner rehearsal remains strictly nonfinancial."""
import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import patch

P=Path(__file__).resolve().parents[1]/"scripts/settlement_c03_intel_real_schema_nologin_owner_rehearsal.py"
spec=importlib.util.spec_from_file_location("c03_real_schema",P)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class SourceTests(unittest.TestCase):
 def test_expected_exact_archives_and_counts(self):
  self.assertEqual(m.PINS["hd"][2],24)
  self.assertEqual(m.PINS["de"][2],10)
  self.assertEqual(len(m.PINS["hd"][1]),64)
  self.assertEqual(len(m.PINS["de"][1]),64)
  self.assertNotEqual(m.PINS["hd"][1],m.PINS["de"][1])
 def test_wrong_arch_or_nonroot_or_wrong_system_fails(self):
  with patch.object(m.sys,"platform","linux"),self.assertRaisesRegex(m.Hold,"INTEL_DARWIN_NONROOT_ONLY"):
   m.admission()
  with patch.object(m.os,"geteuid",return_value=0),self.assertRaisesRegex(m.Hold,"INTEL_DARWIN_NONROOT_ONLY"):
   m.admission()
 def test_identities_need_catalog_safe_quoting(self):
  self.assertEqual(m.check_exact_identifiers(["public.normal","public.\"Capitalized\"","public.\"odd.\"\"table\""]),["public.normal","public.\"Capitalized\"","public.\"odd.\"\"table\""])
  for bad in ("public.x; DROP TABLE y","pg_catalog.fake","public.","public.not-a-table","'public.exploit'"):
   with self.subTest(bad=bad),self.assertRaises(m.Hold):
    m.check_exact_identifiers([bad])
 def test_repeated_or_empty_identifier_rejected(self):
  for case in ([],["public.same","public.same"],[""]):
   with self.subTest(case=case),self.assertRaises(m.Hold):
    m.check_exact_identifiers(case)
 def test_catalog_output_size_bounded(self):
  with self.assertRaises(m.Hold):m.check_sql_output("x"*200000)
  self.assertEqual(m.check_sql_output("public.foo\npublic.bar\n"),["public.foo","public.bar"])
 def test_controller_contains_no_live_financial_execution(self):
  source=P.read_text()
  self.assertIn("listen_addresses='' ",source)
  self.assertIn("productionDatabasesConnected",source)
  self.assertIn("financialReleaseAuthorized",source)
  self.assertNotIn("root@hel1",source)
  self.assertNotIn("8094",source)
  self.assertNotIn("8092",source)
  self.assertNotIn("DROP DATABASE aoe2hd_db",source)
  self.assertNotIn("pg_terminate_backend",source)
if __name__=="__main__":unittest.main()

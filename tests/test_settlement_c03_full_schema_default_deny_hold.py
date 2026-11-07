"""C03 all-public-table default-deny audit: fail closed rather than name regex release."""
from __future__ import annotations
import importlib.util
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import unittest
P=Path(__file__).resolve().parents[1]/"scripts/settlement_c03_full_schema_default_deny_hold.py"
spec=importlib.util.spec_from_file_location("c03_full_schema",P)
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

def fixture(db="aoe2hd_db"):
 x=m.EXPECTED[db]
 name_count=30 if db=="aoe2hd_db" else 11
 semantic_count=x["name_or_semantic"]-name_count
 num_other=x["total"]-x["name_or_semantic"]-len(x["explicit"])
 rows=[f'META|{db}|{x["legacy_owner"]}']
 rows.extend(f'TABLE|wolo_ledger_{i}|{x["legacy_owner"]}|1|0|0|1|id,label'
             for i in range(name_count))
 rows.extend(f'TABLE|fin_extra_{i}|{x["legacy_owner"]}|0|1|0|1|id,amount_wolo'
             for i in range(semantic_count))
 rows.extend(f'TABLE|{n}|{x["legacy_owner"]}|0|0|1|1|id,label'
             for n in x["explicit"])
 rows.extend(f'TABLE|profile_{i}|postgres|0|0|0|0|id,label'
             for i in range(num_other))
 return "\n".join(rows)+"\n"

class FullSchemaC03Tests(unittest.TestCase):
 def test_both_full_schemas_complete_but_still_held(self):
  for db in m.EXPECTED:
   with self.subTest(db=db):
    r=m.parse(fixture(db),db)
    self.assertEqual(r["total_public_tables"],m.EXPECTED[db]["total"])
    self.assertEqual(r["name_or_semantic_candidates"],m.EXPECTED[db]["name_or_semantic"])
    self.assertEqual(r["new_explicit_review_candidates"],sorted(m.EXPECTED[db]["explicit"]))
    self.assertEqual(r["unclassified_count"],(130 if db=="aoe2hd_db" else 31))
    self.assertFalse(r["all_nonfinance_tables_classified"])
    self.assertFalse(r["exhaustive_app_writer_coverage_proven"])
    self.assertEqual(len(r["catalog_schema_sha256"]),64)

 def test_query_transaction_read_only_and_safe_scope(self):
  for db in m.EXPECTED:
   q=m.query(db)
   self.assertIn("REPEATABLE READ READ ONLY",q)
   self.assertIn("ROLLBACK;",q)
   self.assertIn("pg_catalog.pg_class",q)
   self.assertIn("pg_catalog.pg_attribute",q)
   self.assertIn("championship_custody_seats" if db=="aoe2hd_db" else "user_gifts",q)
   self.assertNotIn("ALTER TABLE ",q)
   self.assertNotIn("DROP TABLE ",q)
  with self.assertRaises(m.Hold):m.query("postgres")

 def test_all_seven_explicit_asset_funding_tables_required(self):
  for db in m.EXPECTED:
   s=fixture(db)
   for name in m.EXPECTED[db]["explicit"]:
    with self.subTest(db=db,name=name):
     removed=s.replace(f'TABLE|{name}|{m.EXPECTED[db]["legacy_owner"]}|0|0|1|1|id,label\n',"")
     with self.assertRaises(m.Hold):m.parse(removed,db)

 def test_unclassified_new_table_or_missing_table_never_passes(self):
  x=fixture()
  with self.assertRaises(m.Hold):m.parse(x+"TABLE|new_thing|postgres|0|0|0|0|id,name\n","aoe2hd_db")
  with self.assertRaises(m.Hold):m.parse(x.replace("TABLE|profile_0|postgres|0|0|0|0|id,label\n",""),"aoe2hd_db")
  with self.assertRaises(m.Hold):m.parse(x+"TABLE|profile_0|postgres|0|0|0|0|id,label\n","aoe2hd_db")

 def test_bypass_owner_or_semantic_coverage_drift_stops(self):
  x=fixture()
  for bad in [
   x.replace('META|aoe2hd_db|aoe2hd_user','META|aoe2hd_db|postgres'),
   x.replace('TABLE|wolo_ledger_0|aoe2hd_user','TABLE|wolo_ledger_0|postgres'),
   x.replace('TABLE|wolo_ledger_0|aoe2hd_user|1|0|0|1',
             'TABLE|wolo_ledger_0|aoe2hd_user|1|0|0|0'),
   x.replace('TABLE|fin_extra_0|aoe2hd_user|0|1|0|1|id,amount_wolo',
             'TABLE|fin_extra_0|aoe2hd_user|0|0|0|1|id,amount_wolo'),
   x.replace('TABLE|profile_0|postgres|0|0|0|0|id,label',
             'TABLE|profile_0|postgres|0|0|0|0|id,amount_wolo'),
   x.replace('TABLE|profile_0|postgres','TABLE|profile_0;drop|postgres'),
   x.replace('TABLE|user_gifts|aoe2hd_user|0|0|1|1',
             'TABLE|user_gifts|aoe2hd_user|0|0|0|1'),
  ]:
   with self.subTest(bad=bad[:75]),self.assertRaises(m.Hold):
    m.parse(bad,"aoe2hd_db")

 def test_no_untrusted_principal_or_financial_release(self):
  with patch.object(m.os,"geteuid",return_value=501):
   with self.assertRaises(m.Hold):m.inspect("aoe2hd_db")
  with patch.object(m.os,"geteuid",return_value=0),\
       patch.object(m.subprocess,"run",return_value=SimpleNamespace(
           returncode=0,stdout=fixture(),stderr="")) as proc:
   self.assertEqual(m.inspect("aoe2hd_db")["conservative_review_candidates"],60)
   self.assertEqual(proc.call_args.args[0][:4],
                    ["runuser","-u","postgres","--"])
  script=P.read_text()
  self.assertNotIn("root@hel1",script)
  self.assertNotIn("pg_terminate_backend",script)
  self.assertNotIn("authorize=True",script)

if __name__=="__main__":unittest.main()

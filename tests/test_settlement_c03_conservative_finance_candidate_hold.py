"""Strict C03 conservative name-plus-money-column risk inventory; always HOLD."""
from __future__ import annotations
import importlib.util
from pathlib import Path
from unittest.mock import patch
import unittest

P=Path(__file__).resolve().parents[1]/"scripts/settlement_c03_conservative_finance_candidate_hold.py"
spec=importlib.util.spec_from_file_location("c03conservative",P)
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

def fixture(db="aoe2hd_db"):
 e=m.EXPECTED[db]
 names=[f"wolo_money_{i}" for i in range(e["name"])]
 names += [f"marketplace_{i}" for i in range(e["semantic_only"])]
 rows=[f"META|{db}|{e['role']}|1|1"]
 rows += [f"TABLE|{n}|{e['role']}|{int(n.startswith('wolo_'))}|{int(n.startswith('marketplace_'))}" for n in names]
 rows += [f"COUNT|{k}|{e[k]}" for k in ("sequences","triggers","views","security_definers")]
 return "\n".join(rows)+"\n"

class ConservativeGuard(unittest.TestCase):
 def test_hd_de_valid_source_still_unaccepted(self):
  for db in m.EXPECTED:
   x=m.parse(fixture(db),db)
   self.assertEqual(x["conservative_tables"],m.EXPECTED[db]["all"])
   self.assertFalse(x["protected_table_scope_exhaustive"])
   self.assertFalse(x["writer_fence_proven"])
 def test_query_readonly_and_allowlisted(self):
  for db in m.EXPECTED:
   s=m.query(db)
   self.assertIn("REPEATABLE READ READ ONLY",s)
   self.assertIn("ROLLBACK;",s)
   self.assertIn("pg_catalog.pg_attribute",s)
   for mut in ("ALTER TABLE ","REVOKE ","UPDATE public.","INSERT INTO"):
    self.assertNotIn(mut,s)
  with self.assertRaises(m.Hold):m.query("postgres")
 def test_missing_semantic_and_duplicate_rows_stop(self):
  x=fixture()
  for v in (
   x.replace("TABLE|marketplace_0|aoe2hd_user|0|1\n",""),
   x+"TABLE|marketplace_0|aoe2hd_user|0|1\n",
   x.replace("TABLE|marketplace_0|aoe2hd_user|0|1",
             "TABLE|marketplace_0|postgres|0|1"),
   x.replace("COUNT|sequences|52","COUNT|sequences|51"),
   x.replace("META|aoe2hd_db|aoe2hd_user|1|1",
             "META|aoe2hd_db|aoe2hd_user|0|1"),
   x.replace("TABLE|marketplace_0|aoe2hd_user|0|1",
             "TABLE|marketplace_0|aoe2hd_user|1|1"),
  ):
   with self.subTest(v=v[:50]),self.assertRaises(m.Hold):
    m.parse(v,"aoe2hd_db")
 def test_untrusted_extra_can_not_establish_acceptance(self):
  x=fixture()+"TABLE|marketplace_999|aoe2hd_user|0|1\n"
  with self.assertRaises(m.Hold):m.parse(x,"aoe2hd_db")
 def test_root_only(self):
  with patch.object(m.os,"geteuid",return_value=501):
   with self.assertRaises(m.Hold):m.inspect("aoe2hd_db")
  class Result:
   returncode=0;stderr="";stdout=fixture()
  with patch.object(m.os,"geteuid",return_value=0),\
       patch.object(m.subprocess,"run",return_value=Result()) as r:
   self.assertEqual(m.inspect("aoe2hd_db")["conservative_tables"],54)
   self.assertEqual(r.call_args.args[0][:4],["runuser","-u","postgres","--"])
if __name__=="__main__":unittest.main()

import copy,hashlib,importlib.util,json,os,tempfile,unittest
from pathlib import Path
SRC=Path(__file__).resolve().parents[1]/"scripts/settlement_c05_semantic33_readonly_hold.py"
spec=importlib.util.spec_from_file_location("semantic33_guard",SRC)
s=importlib.util.module_from_spec(spec);spec.loader.exec_module(s)
def fixture(db):
 return {"schema":s.VERSION,"database":db,
    "tables":{name:"0" for name in s.EXPECTED[db]}}
class SemanticCensusTests(unittest.TestCase):
 def setUp(self):self.hd=fixture("hd");self.de=fixture("de")
 def test_exact_33_observed_tables(self):
  self.assertEqual(len(s.EXPECTED["hd"]),24)
  self.assertEqual(len(s.EXPECTED["de"]),9)
  self.assertEqual(set(s.EXPECTED["hd"]),set(s.accounting.SEMANTIC_C05_TABLES["hd"]))
  self.assertEqual(set(s.EXPECTED["de"]),set(s.accounting.SEMANTIC_C05_TABLES["de"]))
  self.assertEqual(len(s.accounting.COVERAGE),52)
 def test_source_sql_is_read_only(self):
  for db in ("hd","de"):
   query=s.sql(db)
   self.assertIn("REPEATABLE READ READ ONLY",query)
   self.assertIn("SET LOCAL lock_timeout='1000ms'",query)
   self.assertIn("ROLLBACK;",query)
   for table in s.EXPECTED[db]:
    self.assertIn("public."+table,query)
   for bad in ("UPDATE public.","DELETE FROM ","ALTER TABLE ","INSERT INTO ","DATABASE_URL","pg_sleep"):
    self.assertNotIn(bad,query)
 def test_table_count_valid(self):
  self.hd["tables"]["staking_positions"]="4"
  self.hd["tables"]["trophy_events"]="923"
  out=s.validate(self.hd,"hd")
  self.assertEqual(out["total_table_count"],24)
  self.assertEqual(out["total_records"],927)
  self.assertEqual(out["nonempty_count"],2)
  self.assertFalse(out["all_money_column_outcomes_reconciled"])
 def test_new_table_denied(self):
  self.hd["tables"]["new_bank_outflow"]="1"
  with self.assertRaises(s.Hold):s.validate(self.hd,"hd")
 def test_missing_table_denied(self):
  self.hd["tables"].pop("staking_positions")
  with self.assertRaises(s.Hold):s.validate(self.hd,"hd")
 def test_wrong_db_denied(self):
  with self.assertRaises(s.Hold):s.validate(self.hd,"de")
 def test_noncanonical_count_denied(self):
  self.hd["tables"]["staking_positions"]="04"
  with self.assertRaises(s.Hold):s.validate(self.hd,"hd")
 def test_negative_denied(self):
  self.hd["tables"]["staking_positions"]="-1"
  with self.assertRaises(s.Hold):s.validate(self.hd,"hd")
 def test_float_denied(self):
  self.hd["tables"]["staking_positions"]=4.0
  with self.assertRaises(s.Hold):s.validate(self.hd,"hd")
 def test_duplicate_json_key_denied(self):
  with self.assertRaises(s.Hold):s.decoded('{"a":1,"a":2}')
 def test_nonfinite_json_denied(self):
  with self.assertRaises(s.Hold):s.decoded('{"a":NaN}')
 def test_private_file_roundtrip(self):
  with tempfile.TemporaryDirectory() as temp:
   p=Path(temp);p.chmod(0o700)
   f=p/"in.json";f.write_text(json.dumps(self.hd));f.chmod(0o600)
   digest=hashlib.sha256(f.read_bytes()).hexdigest()
   self.assertEqual(s.private_read(f,digest),self.hd)
 def test_hash_mismatch_denied(self):
  with tempfile.TemporaryDirectory() as temp:
   p=Path(temp);p.chmod(0o700)
   f=p/"in.json";f.write_text(json.dumps(self.hd));f.chmod(0o600)
   with self.assertRaises(s.Hold):s.private_read(f,"0"*64)
 def test_world_readable_denied(self):
  with tempfile.TemporaryDirectory() as temp:
   p=Path(temp);p.chmod(0o700)
   f=p/"in.json";f.write_text(json.dumps(self.hd));f.chmod(0o644)
   with self.assertRaises(s.Hold):
    s.private_read(f,hashlib.sha256(f.read_bytes()).hexdigest())
 def test_symlink_denied(self):
  with tempfile.TemporaryDirectory() as temp:
   p=Path(temp);p.chmod(0o700)
   f=p/"in.json";f.write_text(json.dumps(self.hd));f.chmod(0o600)
   sym=p/"sym.json";sym.symlink_to(f)
   with self.assertRaises(s.Hold):
    s.private_read(sym,hashlib.sha256(f.read_bytes()).hexdigest())
 def test_no_source_funding_claim(self):
  self.assertFalse(s.validate(self.de,"de")["fenced_and_role_isolated"])
  self.assertFalse(s.validate(self.hd,"hd")["all_money_column_outcomes_reconciled"])
if __name__=="__main__":unittest.main()

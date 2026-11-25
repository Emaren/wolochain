import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest

SRC=Path(__file__).resolve().parents[1]/"scripts/settlement_c05_seven_surface_readonly_hold.py"
SPEC=importlib.util.spec_from_file_location("surface_guard",SRC)
g=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(g)

def fixture(db):
 result={"schema":g.SCHEMA,"database":db,"surfaces":{}}
 for name,_,__,unit,____,_____ in g.DB_SPECS[db]:
  result["surfaces"][name]={"unit":unit,"buckets":[]}
 return result
def bucket(status,rows="1",nominal="1",hash_present="0",hash_missing="1",retries="0"):
 return dict(status=status,rows=rows,nominal=nominal,hash_present=hash_present,
             hash_missing=hash_missing,retries=retries)
class Safety(unittest.TestCase):
 def setUp(self):
  self.hd=fixture("hd")
  self.de=fixture("de")
  self.hd["surfaces"]["trophy_payouts"]["buckets"]=[
   bucket("dry_run","172","1935","0","172"),
   bucket("paid","340","3850","340","0","4")]
  self.hd["surfaces"]["championship_transfer_groups"]["buckets"]=[
   bucket("changed:blocked","8","0","0","8")]
  self.hd["surfaces"]["championship_transfer_seats"]["buckets"]=[
   bucket("blocked","9","0","0","9")]
 def test_seven_actual_tables(self):
  self.assertEqual(len(g.HD),6)
  self.assertEqual(len(g.DE),1)
  self.assertEqual(len(g.validate(self.hd,"hd")),6)
  self.assertEqual(len(g.validate(self.de,"de")),1)
 def test_source_sql_read_only(self):
  for db in ("hd","de"):
   q=g.sql(db)
   self.assertEqual(q.count("BEGIN TRANSACTION"),1)
   self.assertIn("READ ONLY",q)
   self.assertIn("statement_timeout='9000ms'",q)
   self.assertIn("COMMIT;",q)
   self.assertNotIn("INSERT INTO",q)
   self.assertNotIn("DELETE FROM",q)
   self.assertNotIn("UPDATE public",q)
   self.assertNotIn("ALTER TABLE",q)
   self.assertNotIn("DROP TABLE",q)
   for name,*_ in g.DB_SPECS[db]:self.assertIn("public."+name,q)
 def test_de_has_no_hd_tables(self):
  q=g.sql("de")
  self.assertNotIn("public.championship_transfer_seats",q)
 def test_invalid_db(self):
  with self.assertRaises(g.Reject):g.sql("other")
 def test_missing_surface_denied(self):
  self.hd["surfaces"].pop("bounty_payouts")
  with self.assertRaises(g.Reject):g.validate(self.hd,"hd")
 def test_extra_surface_denied(self):
  self.hd["surfaces"]["unreviewed_wallet"]={"unit":"wolo","buckets":[]}
  with self.assertRaises(g.Reject):g.validate(self.hd,"hd")
 def test_wrong_unit_denied(self):
  self.hd["surfaces"]["trophy_payout_allocations"]["unit"]="wolo"
  with self.assertRaises(g.Reject):g.validate(self.hd,"hd")
 def test_wrong_db_denied(self):
  with self.assertRaises(g.Reject):g.validate(self.hd,"de")
 def test_paid_label_not_finality(self):
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp);root.chmod(0o700)
   h=root/"hd.json";d=root/"de.json"
   rawh=(json.dumps(self.hd)+"\n").encode();rawd=(json.dumps(self.de)+"\n").encode()
   h.write_bytes(rawh);d.write_bytes(rawd);h.chmod(0o600);d.chmod(0o600)
   r=g.classify(h,d,hashlib.sha256(rawh).hexdigest(),hashlib.sha256(rawd).hexdigest())
   self.assertEqual(r["protected_surface_count"],7)
   self.assertEqual(r["trophy_paid_labeled_rows"],340)
   self.assertEqual(r["trophy_dry_run_labeled_rows"],172)
   self.assertTrue(r["dry_run_exposure_unresolved_and_not_excluded"])
   self.assertEqual(r["dry_run_nominal_wolo_unclassified"],"1935")
   self.assertEqual(r["status"],"HOLD_C04_C05_NONFINAL_SEVEN_FINANCIAL_SURFACES")
   for k in ("paid_hashes_authenticated_on_chain","global_liability_inventory_complete",
             "financial_release_authorized","payout_retry_authorized","same_height_bank_proof_authenticated"):
    self.assertFalse(r[k])
 def test_duplicate_status_denied(self):
  x=self.hd["surfaces"]["trophy_payouts"]["buckets"]
  x.append(copy.deepcopy(x[0]))
  with self.assertRaises(g.Reject):g.validate(self.hd,"hd")
 def test_hash_census_denied(self):
  self.hd["surfaces"]["trophy_payouts"]["buckets"][1]["hash_missing"]="1"
  with self.assertRaises(g.Reject):g.validate(self.hd,"hd")
 def test_noncanonical_number_denied(self):
  self.hd["surfaces"]["trophy_payouts"]["buckets"][0]["rows"]="0172"
  with self.assertRaises(g.Reject):g.validate(self.hd,"hd")
 def test_negative_number_denied(self):
  self.hd["surfaces"]["trophy_payouts"]["buckets"][0]["rows"]="-172"
  with self.assertRaises(g.Reject):g.validate(self.hd,"hd")
 def test_nft_seat_amount_must_remain_zero(self):
  self.hd["surfaces"]["championship_transfer_seats"]["buckets"][0]["nominal"]="1"
  with self.assertRaises(g.Reject):g.validate(self.hd,"hd")
 def test_duplicate_json_denied(self):
  with self.assertRaises(g.Reject):g.strictly_decode(b'{"a":1,"a":2}')
 def test_digest_mismatch_denied(self):
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp);root.chmod(0o700)
   p=root/"hd.json";p.write_text(json.dumps(self.hd));p.chmod(0o600)
   with self.assertRaises(g.Reject):g.securely_read(p,"0"*64)
 def test_world_readable_denied(self):
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp);root.chmod(0o700)
   p=root/"hd.json";p.write_text(json.dumps(self.hd));p.chmod(0o644)
   with self.assertRaises(g.Reject):g.securely_read(p,hashlib.sha256(p.read_bytes()).hexdigest())
 def test_private_parent_denied(self):
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp);root.chmod(0o755)
   p=root/"hd.json";p.write_text(json.dumps(self.hd));p.chmod(0o600)
   with self.assertRaises(g.Reject):g.securely_read(p,hashlib.sha256(p.read_bytes()).hexdigest())
 def test_symlink_denied(self):
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp);root.chmod(0o700)
   p=root/"hd.json";p.write_text(json.dumps(self.hd));p.chmod(0o600)
   link=root/"link.json";link.symlink_to(p)
   with self.assertRaises(g.Reject):g.securely_read(link,hashlib.sha256(p.read_bytes()).hexdigest())
 def test_sql_snapshot_no_credential_path(self):
  for db in ("hd","de"):
   x=g.sql(db).lower()
   for bad in ("database_url","password","copy ","dblink","curl ","pg_sleep","listen ","notify "):
    self.assertNotIn(bad,x)
if __name__=="__main__":unittest.main()

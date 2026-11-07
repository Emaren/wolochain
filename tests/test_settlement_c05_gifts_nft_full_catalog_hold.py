import copy,hashlib,importlib.util,json,unittest
from pathlib import Path
SRC=Path(__file__).resolve().parents[1]/"scripts/settlement_c05_gifts_nft_full_catalog_hold.py"
sp=importlib.util.spec_from_file_location("gift_full_catalog_guard",SRC)
g=importlib.util.module_from_spec(sp);sp.loader.exec_module(g)
def fixture(db):
 names=list(g.HD_RISK if db=="hd" else g.DE_RISK)
 expected=g.EXPECTED[db]
 names+=["synthetic_"+str(n).zfill(4) for n in range(expected-len(names))]
 names=sorted(names)
 assert len(names)==expected
 doc={"schema":g.VERSION,
 "database":"aoe2hd_db" if db=="hd" else "aoe2de_db",
 "catalog":names,"gifts":[],
 "chain_finality_authenticated":False,"financial_release_authorized":False}
 if db=="hd":
  doc.update({"oracle_bonds":[],
   "custody_seats":{"rows":"9","nft_id_present":"9","class_id_present":"9"},
   "funding_participants":{"rows":"14","funding_linked":"14"},
   "watcher_provenance":[{"finality_status":"trusted_final","rows":"450","trusted_labeled_rows":"450"}],
   "paper_positions":{"rows":"4","nominal_paper_marks":"2000"}})
 return doc
class SourceTests(unittest.TestCase):
 def setUp(self):
  self.h=fixture("hd");self.d=fixture("de")
  self.h["gifts"]=[{"kind":"WOLO","status":"pending","rows":"2",
    "nominal_amount":"100100","accepted_rows":"0"}]
 def held(self):
  with self.assertRaises(g.Hold):g.validate(self.h,"hd")
 def test_provenance_flags_never_authorize(self):
  out=g.validate(self.h,"hd")
  self.assertEqual(out["public_base_table_count"],190)
  self.assertEqual(out["gift_pending_wolo_rows"],2)
  self.assertEqual(out["gift_pending_nominal_wolo"],"100100")
  self.assertEqual(out["nft_ids_recorded"],9)
  self.assertEqual(out["funding_participant_links_recorded"],14)
  self.assertEqual(out["oracle_paper_marks_not_wolo"],"2000")
  self.assertFalse(out["nft_chain_ownership_authenticated"])
  self.assertEqual(g.validate(self.d,"de")["public_base_table_count"],52)
 def test_exact_source_read_only(self):
  for db in ("hd","de"):
   sql=g.sql(db)
   self.assertIn("REPEATABLE READ READ ONLY",sql)
   self.assertIn("SET LOCAL statement_timeout='9000ms'",sql)
   self.assertIn("SET LOCAL lock_timeout='1000ms'",sql)
   self.assertIn("ROLLBACK;",sql)
   self.assertIn("public.user_gifts",sql)
   for bad in ("UPDATE public.","DELETE FROM ","INSERT INTO ","ALTER TABLE ","DATABASE_URL","TRUNCATE "):
    self.assertNotIn(bad,sql)
 def test_no_selectable_other_db(self):
  with self.assertRaises(g.Hold):g.sql("wolo-mainnet")
 def test_catalog_count_drift(self):
  self.h["catalog"].pop();self.held()
 def test_missing_nft_table(self):
  self.h["catalog"].remove("championship_custody_seats")
  self.h["catalog"].append("synthetic_x")
  self.h["catalog"].sort()
  self.held()
 def test_duplicate_catalog_entry(self):
  self.h["catalog"][1]=self.h["catalog"][0];self.held()
 def test_chain_finality_spoof(self):
  self.h["chain_finality_authenticated"]=True;self.held()
 def test_financial_authorization_spoof(self):
  self.h["financial_release_authorized"]=True;self.held()
 def test_gift_pending_cannot_be_negative(self):
  self.h["gifts"][0]["nominal_amount"]="-100100";self.held()
 def test_gift_pending_cannot_be_float(self):
  self.h["gifts"][0]["nominal_amount"]=100100.0;self.held()
 def test_gift_pending_cannot_be_noncanonical(self):
  self.h["gifts"][0]["nominal_amount"]="0100100";self.held()
 def test_duplicate_gift_status_denied(self):
  self.h["gifts"].append(copy.deepcopy(self.h["gifts"][0]));self.held()
 def test_nft_count_mismatch(self):
  self.h["custody_seats"]["rows"]="8";self.held()
 def test_funding_count_mismatch(self):
  self.h["funding_participants"]["funding_linked"]="15";self.held()
 def test_watcher_count_mismatch(self):
  self.h["watcher_provenance"][0]["trusted_labeled_rows"]="451";self.held()
 def test_double_count_watcher_group(self):
  self.h["watcher_provenance"].append(copy.deepcopy(self.h["watcher_provenance"][0]));self.held()
 def test_negative_paper_marks_denied(self):
  self.h["paper_positions"]["nominal_paper_marks"]="-2000";self.held()
 def test_oracle_bond_missing_field(self):
  self.h["oracle_bonds"]=[{"rows":"1","status":"pending"}];self.held()
 def test_wrong_database(self):
  with self.assertRaises(g.Hold):g.validate(self.d,"hd")
 def test_unauthorized_extra_key(self):
  self.h["owner_signed"]=True;self.held()
if __name__=="__main__":unittest.main()

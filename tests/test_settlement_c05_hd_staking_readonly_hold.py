import copy,hashlib,importlib.util,json,os,tempfile,unittest
from pathlib import Path
SRC=Path(__file__).resolve().parents[1]/"scripts/settlement_c05_hd_staking_readonly_hold.py"
spec=importlib.util.spec_from_file_location("staking_guard",SRC)
g=importlib.util.module_from_spec(spec);spec.loader.exec_module(g)

def fixture():
 return {"schema":g.VERSION,"database":"aoe2hd_db",
   "chain_finality_authenticated":False,"financial_release_authorized":False,
   "positions":[
    {"status":"active","rows":"3","principal_wolo":"5356076",
     "pending_rewards_wolo":"0","reward_carry_uwolo":"1357679"},
    {"status":"inactive","rows":"1","principal_wolo":"0",
     "pending_rewards_wolo":"0","reward_carry_uwolo":"1109"}],
   "events":[
    {"status":"CONFIRMED","event_type":"STAKE","rows":"60",
     "nominal_wolo":"5423414","hash_present":"60","hash_missing":"0"},
    {"status":"PENDING_CHAIN","event_type":"STAKE","rows":"1",
     "nominal_wolo":"1000","hash_present":"0","hash_missing":"1"}]}
class StakingGuardTests(unittest.TestCase):
 def setUp(self):self.p=fixture()
 def observed(self):return g.classify(self.p,"a"*64)
 def denied(self):
  with self.assertRaises(g.Hold):self.observed()
 def test_snapshot_output_always_financial_hold(self):
  r=self.observed()
  self.assertEqual(r["status"],"HOLD_STAKING_ACCOUNTING_AND_CHAIN_FINALITY_UNPROVEN")
  self.assertEqual(r["live_active_principal_wolo"],"5356076")
  self.assertEqual(r["live_active_staking_positions"],3)
  self.assertEqual(r["pending_chain_event_nominal_wolo"],"1000")
  self.assertFalse(r["pending_event_additive_to_staked_principal_proven"])
  self.assertFalse(r["pending_chain_event_can_be_safely_retried"])
  self.assertFalse(r["financial_release_authorized"])
 def test_source_sql_is_bounded_select_only(self):
  s=g.sql()
  self.assertIn("REPEATABLE READ READ ONLY",s)
  self.assertIn("SET LOCAL statement_timeout='9000ms'",s)
  self.assertIn("FROM public.staking_positions",s)
  self.assertIn("FROM public.staking_events",s)
  self.assertIn("ROLLBACK",s)
  for bad in ("UPDATE public.","ALTER TABLE","DELETE FROM","INSERT INTO","COPY ","dblink","DATABASE_URL"):
   self.assertNotIn(bad,s)
 def test_no_duplicate_status(self):
  self.p["positions"].append(copy.deepcopy(self.p["positions"][0]));self.denied()
 def test_extra_status(self):
  self.p["positions"][0]["status"]="hidden";self.denied()
 def test_missing_event_hash_accounting(self):
  self.p["events"][1]["hash_missing"]="0";self.denied()
 def test_duplicate_event_status(self):
  self.p["events"].append(copy.deepcopy(self.p["events"][0]));self.denied()
 def test_no_automatic_chain_confirmation(self):
  self.p["chain_finality_authenticated"]=True;self.denied()
 def test_no_financial_authority(self):
  self.p["financial_release_authorized"]=True;self.denied()
 def test_overflow_halt(self):
  self.p["positions"][0]["principal_wolo"]=str(1<<128);self.denied()
 def test_noncanonical_decimal_halt(self):
  self.p["positions"][0]["principal_wolo"]="05356076";self.denied()
 def test_negative_denied(self):
  self.p["positions"][0]["principal_wolo"]="-1";self.denied()
 def test_float_denied(self):
  self.p["positions"][0]["principal_wolo"]=5356076.0;self.denied()
 def test_ambiguous_unhashed_stake(self):
  self.p["events"][0]["hash_missing"]="1";self.p["events"][0]["hash_present"]="59"
  r=self.observed()
  self.assertEqual(r["confirmed_labeled_missing_hash_rows"],1)
  self.assertFalse(r["all_staking_liabilities_disjoint_proven"])
 def test_unexpected_field_denied(self):
  self.p["can_pay"]=True;self.denied()
 def test_unknown_event_status_denied(self):
  self.p["events"][0]["status"]="SENT_UNCONFIRMED";self.denied()
 def test_unknown_event_type_denied(self):
  self.p["events"][0]["event_type"]="FEE";self.denied()
 def test_duplicate_json_field_denied(self):
  with self.assertRaises(g.Hold):g.decode(b'{"a":1,"a":2}')
 def test_input_digest_enforced(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp);p.chmod(0o700)
   f=p/"in.json";f.write_text(json.dumps(self.p));f.chmod(0o600)
   with self.assertRaises(g.Hold):g.read(f,"0"*64)
 def test_input_owner_private_enforced(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp);p.chmod(0o755)
   f=p/"in.json";f.write_text(json.dumps(self.p));f.chmod(0o600)
   with self.assertRaises(g.Hold):g.read(f,hashlib.sha256(f.read_bytes()).hexdigest())
 def test_world_readable_denied(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp);p.chmod(0o700)
   f=p/"in.json";f.write_text(json.dumps(self.p));f.chmod(0o644)
   with self.assertRaises(g.Hold):g.read(f,hashlib.sha256(f.read_bytes()).hexdigest())
 def test_private_input_valid(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp);p.chmod(0o700)
   f=p/"in.json";f.write_text(json.dumps(self.p));f.chmod(0o600)
   digest=hashlib.sha256(f.read_bytes()).hexdigest()
   self.assertEqual(g.read(f,digest),self.p)
if __name__=="__main__":unittest.main()

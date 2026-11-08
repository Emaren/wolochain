import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stdout
from scripts import settlement_c04_unique_candidate_refund_overlap_hold as c

def evidence():
    return {"schema":c.INPUT_SCHEMA,"database":"aoe2hd_db",
      "financial_release_authorized":False,
      "claim_count":69,"nominal_ambiguous_wolo":"120443",
      "unique_wallet_amount_candidate_claims":1,
      "unique_bet_payout_candidate_claims":1,
      "unique_candidate_hash_already_claimed_count":1,
      "unique_candidate_hash_on_wager_count":1,
      "unique_bet_payout_candidate_prior_other_market_void_refund_count":1,
      "local_index_is_independent_bank_proof":False,
      "candidate_can_discharge_original_claim":False}

class C04DoubleAttribution(unittest.TestCase):
    def setUp(self):self.d=evidence()

    def fail(self):
        with self.assertRaises(c.Hold):c.classify(self.d)

    def test_exact_other_market_refund_is_hard_hold(self):
        x=c.classify(self.d)
        self.assertEqual(x["status"],"HOLD_C04_UNIQUE_TRANSFER_ALREADY_ATTRIBUTED_TO_OTHER_MARKET_REFUND")
        self.assertEqual(x["unique_bet_payout_candidate_attributed_to_different_market_void_refund_count"],1)
        self.assertFalse(x["claim_discharge_authorized"])
        self.assertFalse(x["retry_authorized"])
        self.assertFalse(x["financial_release_authorized"])

    def test_no_conflict_still_not_payment_finality(self):
        self.d["unique_bet_payout_candidate_prior_other_market_void_refund_count"]=0
        x=c.classify(self.d)
        self.assertEqual(x["status"],"HOLD_C04_UNIQUE_TRANSFER_NOT_PAYMENT_FINALITY")
        self.assertFalse(x["claim_discharge_authorized"])

    def test_any_forged_release_authorization_denied(self):
        self.d["financial_release_authorized"]=True;self.fail()

    def test_forged_independent_chain_proof_denied(self):
        self.d["local_index_is_independent_bank_proof"]=True;self.fail()

    def test_forged_customer_payment_discharge_denied(self):
        self.d["candidate_can_discharge_original_claim"]=True;self.fail()

    def test_69_count_population_drift_denied(self):
        self.d["claim_count"]=68;self.fail()

    def test_amount_nominal_drift_denied(self):
        self.d["nominal_ambiguous_wolo"]="120444";self.fail()

    def test_noncanonical_float_count_denied(self):
        self.d["unique_wallet_amount_candidate_claims"]=1.0;self.fail()

    def test_refund_conflict_cannot_exceed_prior_claim_references(self):
        self.d["unique_candidate_hash_already_claimed_count"]=0;self.fail()

    def test_refund_conflict_cannot_exceed_wager_references(self):
        self.d["unique_candidate_hash_on_wager_count"]=0;self.fail()

    def test_unknown_or_extra_keys_denied(self):
        self.d["arbitrary_customer_data"]="secret";self.fail()

    def test_readonly_sql_has_correct_economic_linkage_predicates(self):
        s=c.SQL.lower()
        self.assertIn("repeatable read read only",s)
        self.assertIn("rollback;",s)
        self.assertIn("prior.claim_kind='bet_refund'",s)
        self.assertIn("wager.status='void'",s)
        self.assertIn("prior.source_market_id is distinct from u.source_market_id",s)
        self.assertIn("prior.source_market_id=wager.market_id",s)
        self.assertIn("prior.amount_wolo=u.amount_wolo",s)
        self.assertIn("wager.payout_wolo=u.amount_wolo",s)
        for forbidden in ("insert into ","update public.","delete from ",
                          "pg_terminate_backend(","alter role ","returning "):
            self.assertNotIn(forbidden,s)

    def test_private_input_sha_and_mode_required(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"evidence.json"
            path.write_text(json.dumps(self.d))
            digest=hashlib.sha256(path.read_bytes()).hexdigest()
            path.chmod(0o644)
            with self.assertRaises(c.Hold):c.private_read(path,digest)
            path.chmod(0o600)
            self.assertEqual(c.private_read(path,digest),self.d)
            with self.assertRaises(c.Hold):c.private_read(path,"0"*64)
            sym=Path(tmp)/"alias";sym.symlink_to(path)
            with self.assertRaises(c.Hold):c.private_read(sym,digest)

    def test_cli_emits_readonly_sql_only(self):
        with redirect_stdout(out:=io.StringIO()):
            code=c.main(["--emit-hd-sql"])
        self.assertEqual(code,3)
        self.assertIn("READ ONLY",out.getvalue())

    def test_cli_readonly_classification_is_exit_three(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"evidence.json"
            path.write_text(json.dumps(self.d));path.chmod(0o600)
            digest=hashlib.sha256(path.read_bytes()).hexdigest()
            with redirect_stdout(out:=io.StringIO()):
                code=c.main(["--classify","--input",str(path),"--input-sha256",digest])
            self.assertEqual(code,3)
            self.assertFalse(json.loads(out.getvalue())["financial_release_authorized"])

    def test_cli_bad_sha_stops_instead_of_releasing(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"evidence.json"
            path.write_text(json.dumps(self.d));path.chmod(0o600)
            with redirect_stdout(out:=io.StringIO()):
                code=c.main(["--classify","--input",str(path),"--input-sha256","0"*64])
            self.assertEqual(code,2)
            self.assertEqual(json.loads(out.getvalue())["status"],"STOP")

if __name__=="__main__":unittest.main()

import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stdout
from scripts import settlement_c05_pending_gift_claim_nominal_collision_hold as c

def evidence():
    return {
      "schema":c.INPUT_SCHEMA,"database":"aoe2hd_db","pending_gifts":2,
      "amount_buckets":[
        {"amount_wolo":"100000","gifts":1,"claims":0,"claimed":0,
         "hash_bearing":0,"refund_claims":0,"payout_claims":0,
         "within_day":0,"within_30_days":0},
        {"amount_wolo":"100","gifts":1,"claims":24,"claimed":24,
         "hash_bearing":24,"refund_claims":20,"payout_claims":4,
         "within_day":0,"within_30_days":13}],
      "economic_identity_proven":False,"chain_payment_finality_proven":False,
      "gift_discharge_authorized":False,"financial_release_authorized":False}

class C05GiftNominalCollision(unittest.TestCase):
    def setUp(self):self.d=evidence()

    def deny(self):
        with self.assertRaises(c.Hold):c.classify(self.d)

    def test_exact_live_snapshot_holds_without_gift_payment(self):
        result=c.classify(self.d)
        self.assertEqual(result["status"],
          "HOLD_C05_SAME_RECIPIENT_AMOUNT_IS_NOT_GIFT_PAYOUT_IDENTITY")
        self.assertEqual(result["gift_100_same_user_nominal_claims"],24)
        self.assertEqual(result["gift_100_same_user_nominal_hashed_claims"],24)
        self.assertEqual(result["gift_100_same_user_nominal_bet_refunds"],20)
        self.assertEqual(result["gift_100_same_user_nominal_bet_payouts"],4)
        self.assertEqual(result["bounty_100000_gift_nominal_match_claims"],0)
        for key in ("source_nominal_match_is_unique_economic_payout",
                    "gift_paid_or_discharge_proven",
                    "gift_cancellation_proven","funded_retry_authorized",
                    "financial_release_authorized","production_modified"):
            self.assertIs(result[key],False)

    def test_order_independence(self):
        self.d["amount_buckets"].reverse()
        self.assertEqual(c.classify(self.d)["pending_gift_count"],2)

    def test_claim_population_drift(self):
        self.d["amount_buckets"][1]["claims"]=25;self.deny()

    def test_claim_hash_count_drift(self):
        self.d["amount_buckets"][1]["hash_bearing"]=23;self.deny()

    def test_bet_refund_count_drift(self):
        self.d["amount_buckets"][1]["refund_claims"]=21;self.deny()

    def test_bet_payout_count_drift(self):
        self.d["amount_buckets"][1]["payout_claims"]=3;self.deny()

    def test_claim_time_proximity_drift(self):
        self.d["amount_buckets"][1]["within_day"]=1;self.deny()

    def test_100000_bounty_duplicate_claim(self):
        self.d["amount_buckets"][0]["claims"]=1;self.deny()

    def test_new_pending_wo_lo_gift(self):
        self.d["pending_gifts"]=3;self.deny()

    def test_nominal_amount_substitution(self):
        self.d["amount_buckets"][0]["amount_wolo"]="100001";self.deny()

    def test_duplicate_amount_bucket(self):
        self.d["amount_buckets"][1]["amount_wolo"]="100000";self.deny()

    def test_extra_source_fields(self):
        self.d["raw_recipient"]="do_not_include";self.deny()

    def test_fake_entitlement_or_released_payment_stop(self):
        for k in ("economic_identity_proven","chain_payment_finality_proven",
                  "gift_discharge_authorized","financial_release_authorized"):
            self.d=evidence();self.d[k]=True;self.deny()

    def test_noncanonical_numeric_data_stop(self):
        for val in (True,-1,24.0,"24",None):
            self.d=evidence()
            self.d["amount_buckets"][1]["claims"]=val
            self.deny()

    def test_impossible_counter_bound_stop(self):
        self.d["amount_buckets"][1]["hash_bearing"]=25;self.deny()
        self.d=evidence()
        self.d["amount_buckets"][1]["within_day"]=20;self.deny()

    def test_sql_is_anonymous_repeatable_read_only(self):
        source=c.SQL.lower()
        for required in ("repeatable read read only","lock_timeout",
                         "current_database()='aoe2hd_db'","rollback;",
                         "p.claimed_by_user_id=g.user_id",
                         "p.amount_wolo=g.amount","p.claim_kind='bet_refund'",
                         "p.claim_kind='bet_payout'"):
            self.assertIn(required,source)
        for forbidden in ("insert into ","update public.","delete from ",
                          "pg_terminate_backend(","alter role ","returning ",
                          "'user_id'","'payout_tx_hash'","'note'"):
            self.assertNotIn(forbidden,source)

    def test_private_evidence_requires_sha_and_0600(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/"evidence.json"
            p.write_text(json.dumps(self.d));p.chmod(0o600)
            digest=hashlib.sha256(p.read_bytes()).hexdigest()
            self.assertEqual(c.load_private(p,digest),self.d)
            with self.assertRaises(c.Hold):c.load_private(p,"0"*64)
            p.chmod(0o644)
            with self.assertRaises(c.Hold):c.load_private(p,digest)
            p.chmod(0o600)
            alias=Path(temp)/"alias"
            alias.symlink_to(p)
            with self.assertRaises(OSError):c.load_private(alias,digest)

    def test_cli_sql_returns_nonpermitting_exit_three(self):
        with redirect_stdout(buf:=io.StringIO()):
            rc=c.main(["--emit-hd-sql"])
        self.assertEqual(rc,3)
        self.assertIn("READ ONLY",buf.getvalue())

    def test_cli_exact_evidence_returns_hold_three(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/"evidence.json"
            p.write_text(json.dumps(self.d));p.chmod(0o600)
            digest=hashlib.sha256(p.read_bytes()).hexdigest()
            with redirect_stdout(buf:=io.StringIO()):
                rc=c.main(["--classify","--input",str(p),
                           "--input-sha256",digest])
            self.assertEqual(rc,3)
            self.assertFalse(json.loads(buf.getvalue())["financial_release_authorized"])

    def test_cli_broken_evidence_returns_stop_two(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/"evidence.json"
            p.write_text(json.dumps(self.d));p.chmod(0o600)
            with redirect_stdout(buf:=io.StringIO()):
                rc=c.main(["--classify","--input",str(p),
                           "--input-sha256","0"*64])
            self.assertEqual(rc,2)
            self.assertEqual(json.loads(buf.getvalue())["status"],"STOP")

if __name__=="__main__":
    unittest.main()

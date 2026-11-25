import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stdout
from scripts import settlement_c05_bounty_assignment_publication_hold as c

def evidence():
    return {
      "schema":c.SOURCE_SCHEMA,"database":"aoe2hd_db",
      "gift_nominal_wolo":"100000","pending_100k_gifts":1,
      "linked_opportunities":1,"unlinked_gifts":0,
      "linked_unassigned_opportunities":1,
      "linked_assigned_to_gift_recipient":0,
      "linked_assigned_to_other_recipient":0,
      "linked_reward_null":1,"linked_reward_matches_gift":0,
      "linked_reward_conflicts":0,
      "linked_unpublished":1,"linked_published":0,
      "linked_available_status":1,"linked_other_status":0,
      "linked_expired":0,"related_bounty_events":0,
      "related_bounty_events_with_tx_hash":0,
      "independent_bounty_entitlement_authenticated":False,
      "chain_payment_finality_authenticated":False,
      "financial_release_authorized":False,
    }

class C05BountyAssignmentPublication(unittest.TestCase):
    def setUp(self):self.d=evidence()

    def deny(self):
        with self.assertRaises(c.Hold):c.classify(self.d)

    def test_actual_known_source_is_explicit_financial_hard_hold(self):
        result=c.classify(self.d)
        self.assertEqual(result["status"],
            "HOLD_C05_BOUNTY_GIFT_HAS_NO_ASSIGNEE_NO_REWARD_AND_NOT_PUBLISHED")
        self.assertEqual(result["source_assigned_recipient_count"],0)
        self.assertEqual(result["source_reward_valuation_present_count"],0)
        self.assertEqual(result["source_published_count"],0)
        self.assertFalse(result["financial_release_authorized"])
        self.assertFalse(result["customer_retry_authorized"])

    def test_cannot_claim_entitlement_or_finality(self):
        self.d["independent_bounty_entitlement_authenticated"]=True;self.deny()
        self.d=evidence()
        self.d["chain_payment_finality_authenticated"]=True;self.deny()
        self.d=evidence()
        self.d["financial_release_authorized"]=True;self.deny()

    def test_reward_valuation_drift_stop(self):
        self.d["linked_reward_null"]=0
        self.d["linked_reward_matches_gift"]=1;self.deny()

    def test_reward_conflict_drift_stop(self):
        self.d["linked_reward_null"]=0
        self.d["linked_reward_conflicts"]=1;self.deny()

    def test_unpublished_to_published_requires_review(self):
        self.d["linked_unpublished"]=0
        self.d["linked_published"]=1;self.deny()

    def test_user_assigned_requires_review(self):
        self.d["linked_unassigned_opportunities"]=0
        self.d["linked_assigned_to_gift_recipient"]=1;self.deny()

    def test_other_user_assigned_requires_review(self):
        self.d["linked_unassigned_opportunities"]=0
        self.d["linked_assigned_to_other_recipient"]=1;self.deny()

    def test_new_bounty_event_requires_review(self):
        self.d["related_bounty_events"]=1;self.deny()

    def test_bounty_event_hash_cannot_exceed_event_count(self):
        self.d["related_bounty_events_with_tx_hash"]=1;self.deny()

    def test_unknown_source_status_requires_review(self):
        self.d["linked_available_status"]=0
        self.d["linked_other_status"]=1;self.deny()

    def test_missing_source_opportunity_stop(self):
        self.d["linked_opportunities"]=0
        self.d["unlinked_gifts"]=1;self.deny()

    def test_extra_or_missing_100k_gift_stop(self):
        self.d["pending_100k_gifts"]=2;self.deny()
        self.d["pending_100k_gifts"]=0;self.deny()

    def test_impossible_assignee_partition_stop(self):
        self.d["linked_assigned_to_other_recipient"]=1;self.deny()

    def test_impossible_reward_partition_stop(self):
        self.d["linked_reward_matches_gift"]=1;self.deny()

    def test_float_fake_and_negative_aggregate_stop(self):
        self.d["linked_unassigned_opportunities"]=1.0;self.deny()
        self.d["linked_unassigned_opportunities"]=-1;self.deny()

    def test_new_field_and_source_version_stop(self):
        self.d["claim_id"]=123;self.deny()
        self.d=evidence()
        self.d["schema"]="wolo.c05.bounty-100k-gift-assignment-source-readonly.v2"
        self.deny()

    def test_bounded_readonly_sql_and_no_customer_identity_output(self):
        s=c.SQL.lower()
        self.assertIn("repeatable read read only",s)
        self.assertIn("lock_timeout",s)
        self.assertIn("rollback;",s)
        self.assertIn("assigned_user_id=user_id",s)
        self.assertIn("b.published_at",s)
        self.assertIn("b.reward_wolo",s)
        self.assertIn("related_bounty_events",s)
        self.assertIn("current_database()='aoe2hd_db'",s)
        for forbidden in ("insert into ","update public.","delete from ",
                          "pg_terminate_backend(","alter role ","returning ",
                          "'recipient_id'","'user_id'","'tx_hash'"):
            self.assertNotIn(forbidden,s)

    def test_private_receipt_enforces_sha_mode_and_symlinks(self):
        with tempfile.TemporaryDirectory() as root:
            p=Path(root)/"private.json"
            p.write_text(json.dumps(self.d));p.chmod(0o600)
            sha=hashlib.sha256(p.read_bytes()).hexdigest()
            self.assertEqual(c.private_read(p,sha),self.d)
            with self.assertRaises(c.Hold):c.private_read(p,"0"*64)
            p.chmod(0o644)
            with self.assertRaises(c.Hold):c.private_read(p,sha)
            p.chmod(0o600)
            alias=Path(root)/"alias";alias.symlink_to(p)
            with self.assertRaises(c.Hold):c.private_read(alias,sha)

    def test_cli_emits_sql_but_never_payment(self):
        with redirect_stdout(buf:=io.StringIO()):
            code=c.main(["--emit-hd-sql"])
        self.assertEqual(code,3)
        self.assertIn("READ ONLY",buf.getvalue())
        self.assertNotIn("payment_authorized",buf.getvalue())

    def test_cli_classification_is_exit_three_hold(self):
        with tempfile.TemporaryDirectory() as root:
            p=Path(root)/"private.json"
            p.write_text(json.dumps(self.d));p.chmod(0o600)
            sha=hashlib.sha256(p.read_bytes()).hexdigest()
            with redirect_stdout(buf:=io.StringIO()):
                code=c.main(["--classify","--input",str(p),"--input-sha256",sha])
            self.assertEqual(code,3)
            self.assertEqual(json.loads(buf.getvalue())["financial_release_authorized"],False)

    def test_cli_bad_evidence_is_stop(self):
        with tempfile.TemporaryDirectory() as root:
            p=Path(root)/"private.json"
            p.write_text(json.dumps(self.d));p.chmod(0o600)
            with redirect_stdout(buf:=io.StringIO()):
                code=c.main(["--classify","--input",str(p),"--input-sha256","0"*64])
            self.assertEqual(code,2)
            self.assertEqual(json.loads(buf.getvalue())["status"],"STOP")

if __name__=="__main__":
    unittest.main()

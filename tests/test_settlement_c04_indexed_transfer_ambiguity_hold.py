import copy
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch
from scripts import settlement_c04_indexed_transfer_ambiguity_hold as c


def fixture():
    return {
        "schema":c.SOURCE_SCHEMA,"database":"aoe2hd_db",
        "financial_release_authorized":False,
        "index_not_independent_consensus_finality":True,
        "window_before_attempt_days":1,"near_after_attempt_days":7,
        "far_after_attempt_days":30,
        "index_rows":4300,"index_wolo_uwolo_rows":4300,
        "index_max_height":"2813553",
        "index_latest_utc_day":"2026-11-04",
        "groups":[
            {"kind":"bet_payout","claims":15,"nominal_wolo":"109504",
             "wallet_count":15,"attempted":13,
             "any_candidate_claims":9,"exactly_one_candidate_claims":1,
             "unique_near_attempt_claims":0,"unique_before_window_claims":0,"unique_after_window_claims":1,"unique_missing_time_claims":0,"multiple_candidate_claims":8,"near_attempt_claims":4,
             "thirty_day_claims":4,"all_candidate_rows":691},
            {"kind":"bet_refund","claims":3,"nominal_wolo":"6801",
             "wallet_count":3,"attempted":3,
             "any_candidate_claims":1,"exactly_one_candidate_claims":0,
             "unique_near_attempt_claims":0,"unique_before_window_claims":0,"unique_after_window_claims":0,"unique_missing_time_claims":0,"multiple_candidate_claims":1,"near_attempt_claims":1,
             "thirty_day_claims":1,"all_candidate_rows":43},
            {"kind":"founders_bonus","claims":51,"nominal_wolo":"4138",
             "wallet_count":51,"attempted":50,
             "any_candidate_claims":51,"exactly_one_candidate_claims":0,
             "unique_near_attempt_claims":0,"unique_before_window_claims":0,"unique_after_window_claims":0,"unique_missing_time_claims":0,"multiple_candidate_claims":51,"near_attempt_claims":49,
             "thirty_day_claims":49,"all_candidate_rows":5412},
        ]}

class TransferCandidatesTests(unittest.TestCase):
    def setUp(self):self.d=fixture()

    def held(self):
        with self.assertRaises(c.Hold):
            c.validate(self.d)

    def test_real_observation_preserves_financial_hard_hold(self):
        out=c.validate(self.d)
        self.assertEqual(out["status"],
                         "HOLD_C04_INDEX_MATCHES_NOT_INDEPENDENT_PAYMENT_FINALITY")
        self.assertFalse(out["candidate_transfer_is_payment_proof"])
        self.assertFalse(out["retry_authorized"])
        self.assertFalse(out["funded_release_authorized"])
        self.assertFalse(out["independent_comet_bank_and_inclusion_proven"])
        self.assertEqual(sum(x["claims"] for x in out["groups"].values()),69)

    def test_readonly_sql_no_address_or_identity_output(self):
        s=c.SQL.lower()
        self.assertIn("begin transaction isolation level repeatable read read only",s)
        self.assertIn("statement_timeout",s)
        self.assertIn("rollback;",s)
        self.assertIn("amount_uwolo=c.nominal*1000000",s)
        self.assertIn("lower(btrim(t.recipient_address))=c.wallet",s)
        self.assertIn("jsonb_build_object",s)
        for forbidden in ("returning ","delete from ","update public.",
                          "insert into ","alter table ","pg_terminate_backend(",
                          "t.recipient_address as recipient","c.id as claim_id"):
            self.assertNotIn(forbidden,s)

    def test_69_claim_population_drift_denied(self):
        self.d["groups"][0]["claims"]=14;self.held()

    def test_69_claim_amount_drift_denied(self):
        self.d["groups"][2]["nominal_wolo"]="4139";self.held()

    def test_unique_candidate_after_window_is_not_near_proof(self):
        out=c.validate(self.d)
        self.assertEqual(out["groups"]["bet_payout"]["unique_candidate_after_attempt_window"],1)
        self.assertEqual(out["groups"]["bet_payout"]["unique_candidate_near_attempt"],0)
        self.assertFalse(out["candidate_transfer_is_payment_proof"])

    def test_unique_window_partition_cannot_forge_near_match(self):
        self.d["groups"][0]["unique_near_attempt_claims"]=1
        self.held()

    def test_unique_window_partition_must_cover_all_unique_matches(self):
        self.d["groups"][0]["unique_after_window_claims"]=0
        self.held()

    def test_unavailable_attempt_time_cannot_be_forged(self):
        self.d["groups"][0]["unique_missing_time_claims"]=1
        self.held()

    def test_unique_missing_timestamp_can_coexist_with_recorded_attempt(self):
        self.d["groups"][0]["attempted"]=15
        self.d["groups"][0]["unique_after_window_claims"]=0
        self.d["groups"][0]["unique_missing_time_claims"]=1
        out=c.validate(self.d)
        self.assertEqual(out["groups"]["bet_payout"]["unique_candidate_time_unavailable"],1)
        self.assertFalse(out["claim_discharge_authorized"])

    def test_bad_source_version_is_stop(self):
        self.d["schema"]="wolo.c04.indexed-transfer-candidate-readonly-census.v1"
        self.held()

    def test_missing_wallet_denied(self):
        self.d["groups"][0]["wallet_count"]=14;self.held()

    def test_unknown_kind_denied(self):
        self.d["groups"][0]["kind"]="unknown";self.held()

    def test_duplicate_kind_denied(self):
        self.d["groups"][1]["kind"]="bet_payout";self.held()

    def test_forged_financial_release_denied(self):
        self.d["financial_release_authorized"]=True;self.held()

    def test_forged_consensus_proof_denied(self):
        self.d["index_not_independent_consensus_finality"]=False;self.held()

    def test_false_unique_or_overlapping_groups_denied(self):
        self.d["groups"][0]["exactly_one_candidate_claims"]=2;self.held()

    def test_more_near_than_total_denied(self):
        self.d["groups"][1]["near_attempt_claims"]=2;self.held()

    def test_near_exceeds_recorded_attempts_denied(self):
        self.d["groups"][0]["attempted"]=3;self.held()

    def test_ambiguous_transfers_cannot_have_only_one_total(self):
        self.d["groups"][0]["all_candidate_rows"]=2;self.held()

    def test_noncanonical_float_counts_denied(self):
        self.d["groups"][0]["claims"]=15.0;self.held()

    def test_index_unsupported_denom_or_zero_denied(self):
        self.d["index_wolo_uwolo_rows"]=0;self.held()

    def test_timestamp_or_height_invalid_denied(self):
        self.d["index_max_height"]="NaN";self.held()

    def test_time_window_changed_denied(self):
        self.d["near_after_attempt_days"]=90;self.held()

    def test_private_file_rejects_world_readable_and_symlinks(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/"evidence.json";p.write_text(json.dumps(self.d))
            p.chmod(0o644)
            with self.assertRaises(c.Hold):c.private_read(p)
            p.chmod(0o600)
            self.assertEqual(json.loads(c.private_read(p)),self.d)
            link=Path(tmp)/"alias.json";link.symlink_to(p)
            with self.assertRaises(c.Hold):c.private_read(link)

    def test_classify_evidence_digest_rejects_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/"observation.json"
            p.write_text(json.dumps(self.d));p.chmod(0o600)
            out=io.StringIO()
            with redirect_stdout(out):
                rc=c.main(["--classify","--input",str(p),
                           "--input-sha256","0"*64])
            self.assertEqual(rc,2)
            self.assertEqual(json.loads(out.getvalue())["status"],"STOP")

    def test_classify_success_is_exit_three_not_pass(self):
        import hashlib
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/"observation.json"
            p.write_text(json.dumps(self.d));p.chmod(0o600)
            out=io.StringIO()
            with redirect_stdout(out):
                rc=c.main(["--classify","--input",str(p),
                           "--input-sha256",hashlib.sha256(p.read_bytes()).hexdigest()])
            self.assertEqual(rc,3)
            self.assertFalse(json.loads(out.getvalue())["funded_release_authorized"])

    def test_emit_sql_only_readonly_no_permits(self):
        out=io.StringIO()
        with redirect_stdout(out):rc=c.main(["--emit-hd-sql"])
        self.assertEqual(rc,3)
        self.assertIn("READ ONLY",out.getvalue())

if __name__=="__main__":unittest.main()

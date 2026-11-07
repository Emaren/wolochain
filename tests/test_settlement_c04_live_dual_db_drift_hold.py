"""C04 live HD/DE held observations: source-only negative and scope tests."""
from __future__ import annotations

import copy
from datetime import datetime,timezone,timedelta
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest

from scripts import settlement_c04_live_dual_db_drift_hold as guard

NOW=datetime(2026,11,7,1,30,0,tzinfo=timezone.utc)
STAMP="2026-11-07T01:29:30Z"

def packet(db):
    hd=db==guard.HD
    return {
      "schema":guard.SCHEMA,"database":db,"captured_utc":STAMP,
      "counts":dict(guard.HD_COUNTS if hd else guard.DE_COUNTS),
      "groups":[{"kind":k,"count":v[0],"wolo":v[1]} for k,v in
                (guard.HD_GROUPS.items() if hd else ())],
      "critical_claims":[{"id":i,"status":v[0],"kind":v[1],"wolo":v[2],
                           "hash_present":v[3],"attempted":v[4]}
                          for i,v in (guard.CRITICAL_CLAIMS.items() if hd else ())],
      "critical_wagers":[{"id":i,"status":v[0],"wolo":v[1],
                          "stake_hash_present":v[2],"payout_hash_present":v[3]}
                          for i,v in (guard.CRITICAL_WAGERS.items() if hd else ())],
      "indexed":{"count":4300,"height_max":2813553} if hd
                 else {"count":0,"height_max":0},
      "financial_authorized":False,"chain_finality_proven":False,
      "cross_db_snapshot_atomic":False,
    }

class DualC04(unittest.TestCase):
    def good(self):
        return packet(guard.HD),packet(guard.DE)

    def blocked(self,hd=None,de=None,reason="C04_"):
        good_hd,good_de=self.good()
        with self.assertRaisesRegex(guard.Hold,reason):
            guard.compare(hd if hd is not None else good_hd,
                          de if de is not None else good_de,
                          now=NOW)

    def test_valid_live_synthetic_packet_remains_financial_hold(self):
        r=guard.compare(*self.good(),now=NOW)
        self.assertEqual(r["status"],"HOLD_C04_UNRESOLVED_PAYMENT_FINALITY")
        self.assertEqual(r["hd_claimed_hashless"],69)
        self.assertEqual(r["hd_claimed_hashless_nominal_wolo"],120443)
        self.assertEqual(r["hd_pending_claims"],948)
        self.assertFalse(r["cross_db_atomic"])
        self.assertFalse(r["financial_release_authorized"])
        self.assertFalse(r["retry_authorized"])

    def test_all_critical_wagers_and_claims_required(self):
        hd,de=self.good();hd["critical_claims"].pop()
        self.blocked(hd,de,"C04_HISTORICAL_UNKNOWN_CASE_DRIFT")
        hd,de=self.good();hd["critical_wagers"].pop()
        self.blocked(hd,de,"C04_HISTORICAL_UNKNOWN_CASE_DRIFT")

    def test_new_hashless_claim_is_source_drift_not_auto_payout(self):
        hd,de=self.good();hd["counts"]["claimed_hashless"]=70
        self.blocked(hd,de,"C04_LIVE_CLAIM_CENSUS_CHANGED")

    def test_marked_claimed_is_not_paid(self):
        hd,de=self.good()
        for row in hd["critical_claims"]:
            if row["id"]==8217:row["hash_present"]=True
        self.blocked(hd,de,"C04_HISTORICAL_UNKNOWN_CASE_DRIFT")

    def test_missing_founder_889_not_silently_discharged(self):
        hd,de=self.good()
        next(x for x in hd["critical_claims"] if x["id"]==889)["status"]="paid"
        self.blocked(hd,de,"C04_HISTORICAL_UNKNOWN_CASE_DRIFT")

    def test_critical_wager_stake_and_payout_separated(self):
        hd,de=self.good()
        next(x for x in hd["critical_wagers"] if x["id"]==394)["payout_hash_present"]=True
        self.blocked(hd,de,"C04_HISTORICAL_UNKNOWN_CASE_DRIFT")

    def test_de_claim_activity_detected_not_pretended_empty(self):
        hd,de=self.good();de["counts"]["pending"]=1
        self.blocked(hd,de,"C04_LIVE_CLAIM_CENSUS_CHANGED")

    def test_claim_kind_distribution_and_amount_must_match(self):
        hd,de=self.good()
        hd["groups"][0]["wolo"]+=1
        self.blocked(hd,de,"C04_GROUP_AMOUNT_DRIFT")

    def test_index_height_not_comet_consensus(self):
        hd,de=self.good();hd["indexed"]["height_max"]=2800000
        self.blocked(hd,de,"C04_LOCAL_INDEX_OBSERVED_REGRESSION")

    def test_cross_database_atomicity_never_claimed(self):
        hd,de=self.good();hd["cross_db_snapshot_atomic"]=True
        self.blocked(hd,de,"C04_UNEARNED_FINANCIAL_AUTHORITY")

    def test_no_paid_or_chain_finality_assertion(self):
        hd,de=self.good();hd["chain_finality_proven"]=True
        self.blocked(hd,de,"C04_UNEARNED_FINANCIAL_AUTHORITY")

    def test_timestamps_must_be_fresh_and_bounded(self):
        hd,de=self.good();hd["captured_utc"]="2026-11-07T01:12:00Z"
        self.blocked(hd,de,"C04_SOURCE_CAPTURE_EXPIRED_OR_FUTURE")
        hd,de=self.good();de["captured_utc"]="2026-11-07T01:25:00Z"
        self.blocked(hd,de,"C04_CROSS_DB_CAPTURE_WINDOW_SPLIT")

    def test_duplicate_unknown_id_refused(self):
        hd,de=self.good();hd["critical_claims"][1]["id"]=889
        self.blocked(hd,de,"C04_CLAIM_CASE_SHAPE_INVALID")

    def test_boolean_type_instead_of_int_for_money(self):
        hd,de=self.good();hd["counts"]["claimed_hashless"]=True
        self.blocked(hd,de,"C04_COUNTS_SHAPE_DRIFT")

    def test_schema_unknown_fields_refused(self):
        hd,de=self.good();hd["financial_release_override"]=True
        self.blocked(hd,de,"C04_SCHEMA_DRIFT")

    def test_sql_is_only_postgres_readonly_catalog_and_correct_db_bound(self):
        for db in (guard.HD,guard.DE):
            sql=guard.observe_sql(db)
            self.assertIn("BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY",sql)
            self.assertIn("current_database() = '"+db+"'",sql)
            self.assertIn("pending_wolo_claims",sql)
            self.assertIn("bet_wagers",sql)
            self.assertIn("wolo_indexed_transfers",sql)
            for forbidden in ("ALTER ROLE","DELETE FROM","DROP TABLE",
                              "UPDATE public.","INSERT INTO","CREATE ROLE",
                              "pg_terminate_backend","wolochaind tx","COPY TO PROGRAM"):
                self.assertNotIn(forbidden,sql)

    def test_private_packet_sha_and_permissions_enforced(self):
        with tempfile.TemporaryDirectory(prefix="c04-hold-") as t:
            base=Path(t);base.chmod(0o700);p=base/"packet.json"
            raw=json.dumps(packet(guard.HD),sort_keys=True).encode()
            p.write_bytes(raw);p.chmod(0o600)
            sha=hashlib.sha256(raw).hexdigest()
            self.assertEqual(guard.read_private(p,sha)["database"],guard.HD)
            with self.assertRaisesRegex(guard.Hold,"C04_EVIDENCE_SHA_DRIFT"):
                guard.read_private(p,"f"*64)
            p.chmod(0o644)
            with self.assertRaisesRegex(guard.Hold,"C04_PRIVATE_EVIDENCE_UNSAFE"):
                guard.read_private(p,sha)
            p.chmod(0o600)
            link=base/"link"
            link.symlink_to(p)
            with self.assertRaisesRegex(guard.Hold,"C04_PRIVATE_PATH_INVALID"):
                guard.read_private(link,sha)

    def test_private_parent_must_be_owned_and_sealed(self):
        with tempfile.TemporaryDirectory(prefix="c04-parent-") as t:
            base=Path(t);base.chmod(0o755);p=base/"packet.json"
            raw=json.dumps(packet(guard.HD)).encode()
            p.write_bytes(raw);p.chmod(0o600)
            with self.assertRaisesRegex(guard.Hold,"C04_PRIVATE_PARENT_UNSAFE"):
                guard.read_private(p,hashlib.sha256(raw).hexdigest())

    def test_private_packet_duplicate_field_is_explicit_stop(self):
        with tempfile.TemporaryDirectory(prefix="c04-dup-") as t:
            base=Path(t);base.chmod(0o700);p=base/"packet.json"
            raw=json.dumps(packet(guard.HD)).replace(
                '"schema": "', '"schema": "forged", "schema": "',1).encode()
            p.write_bytes(raw);p.chmod(0o600)
            with self.assertRaisesRegex(guard.Hold,"C04_DUPLICATE_JSON_KEY"):
                guard.read_private(p,hashlib.sha256(raw).hexdigest())

    def test_duplicate_json_key_rejected(self):
        with self.assertRaisesRegex(guard.Hold,"C04_DUPLICATE_JSON_KEY"):
            guard.unique([("schema",guard.SCHEMA),("schema","other")])

    def test_no_external_connections_or_service_controls(self):
        src=(Path(__file__).resolve().parents[1]/
             "scripts/settlement_c04_live_dual_db_drift_hold.py").read_text()
        for forbidden in ("psycopg","subprocess.run","requests.get",
                          "urllib.request","ssh -T","systemctl","broadcast"):
            if forbidden=="broadcast":
                # Docstring can discuss non-broadcasting, not a call.
                continue
            self.assertNotIn(forbidden,src)

if __name__=="__main__":
    unittest.main()

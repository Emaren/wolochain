#!/usr/bin/env python3
"""Hermetic C05 source-identity HOLD contracts; no databases or network."""
import copy
from datetime import datetime, timedelta, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch

P=Path(__file__).resolve().parents[1]/"scripts/settlement_c05_active_winner_live_hold.py"
spec=importlib.util.spec_from_file_location("c05_live_hold",P)
c05=importlib.util.module_from_spec(spec)
spec.loader.exec_module(c05)
NOW=datetime(2026,11,7,2,15,tzinfo=timezone.utc)

def fake():
    values=[1000]*40+[13728]
    active_rows=[]
    live_rows=[]
    for i,wolo in enumerate(values):
        stake=f"{1000+i:064x}"
        active_rows.append({"wager_id":i+1,"market_id":i+200,
            "tx_hash":stake,"principal_uwolo":str(wolo*1_000_000)})
        live_rows.append({"id":i+1,"market_id":i+200,
            "wolo":wolo,"stake_hash":stake})
    active={"schema":c05.ACTIVE_SCHEMA,"wager_count":41,"entries":active_rows,
            "original_principal_uwolo":str(53728*1_000_000),
            "global_solvency_certified":False,
            "financial_release_authorized":False,
            "independent_canonical_consensus_trust_anchor_proven":False}
    winners={"schema":c05.WINNERS_SCHEMA,"records":[
            {"wager_id":100+i,"stake_tx_hash":f"{2000+i:064x}"}
            for i in range(25)],
            "financial_release_authorized":False,
            "disjoint_global_liability_bound_proven":False}
    live={"schema":c05.LIVE_SCHEMA,"database":"aoe2hd_db",
          "snapshot_utc":NOW.strftime("%Y-%m-%dT%H:%M:%SZ"),
          "total":41,"rows":live_rows,"independent_chain_finality":False,
          "financial_release_authorized":False}
    return active,winners,live

class FinancialHold(unittest.TestCase):
    def setUp(self):
        self.a,self.w,self.l=fake()
        rows=sorted([[r["wager_id"],r["market_id"],int(r["principal_uwolo"]),
                      r["tx_hash"]] for r in self.a["entries"]])
        self.patcher=patch.object(c05,"EXPECTED_ACTIVE_TUPLE_SHA256",c05.source_digest(rows))
        self.patcher.start()
        self.addCleanup(self.patcher.stop)
    def valid(self):
        return c05.classify(self.a,self.w,self.l,now=NOW)
    def hold(self,reason):
        with self.assertRaisesRegex(c05.Hold,reason):
            self.valid()
    def test_exact_complete_source_returns_hold_never_authority(self):
        report=self.valid()
        self.assertTrue(report["status"].startswith("HOLD_C05"))
        for k in ("financial_release_authorized","payout_retry_authorized",
                  "full_solvency_certified","independent_bank_proof_authenticated",
                  "claim_payment_finality_authenticated","production_mutated"):
            self.assertIs(report[k],False)
        self.assertEqual(report["active_wagers"],41)
        self.assertEqual(report["original_nominal_stake_wolo"],53728)
    def test_balanced_amount_swaps_are_detected(self):
        self.l["rows"][0]["wolo"]+=1
        self.l["rows"][1]["wolo"]-=1
        self.hold("C05_ACTIVE_INDIVIDUAL_SOURCE_DRIFT")
    def test_changed_market_same_amount_rejected(self):
        self.l["rows"][3]["market_id"]+=1
        self.hold("C05_ACTIVE_INDIVIDUAL_SOURCE_DRIFT")
    def test_missing_live_row_rejected(self):
        self.l["rows"].pop()
        self.hold("C05_LIVE_ACTIVE_COUNT_DRIFT")
    def test_duplicate_live_stake_hash_rejected(self):
        self.l["rows"][3]["stake_hash"]=self.l["rows"][2]["stake_hash"]
        self.hold("C05_LIVE_DUPLICATE_OR_UNORDERED")
    def test_duplicate_live_id_rejected(self):
        self.l["rows"][3]["id"]=self.l["rows"][2]["id"]
        self.hold("C05_LIVE_DUPLICATE_OR_UNORDERED")
    def test_winner_reuses_active_wager_id_fails(self):
        self.w["records"][0]["wager_id"]=self.a["entries"][1]["wager_id"]
        self.hold("C05_ACTIVE_VS_WINNER_SOURCE_COLLISION")
    def test_winner_reuses_active_stake_hash_fails(self):
        self.w["records"][0]["stake_tx_hash"]=self.a["entries"][1]["tx_hash"]
        self.hold("C05_ACTIVE_VS_WINNER_SOURCE_COLLISION")
    def test_historical_source_pin_is_required(self):
        with patch.object(c05,"EXPECTED_ACTIVE_TUPLE_SHA256","0"*64):
            self.hold("C05_HISTORICAL_ACTIVE_SOURCE_IDENTITY_DRIFT")
    def test_wrong_wallet_free_status_cannot_claim_bank_authority(self):
        self.l["independent_chain_finality"]=True
        self.hold("C05_LIVE_UNSUPPORTED_AUTHORITY")
    def test_timestamp_expired_fails(self):
        self.l["snapshot_utc"]=(NOW-timedelta(minutes=21)).strftime("%Y-%m-%dT%H:%M:%SZ")
        self.hold("C05_LIVE_OBSERVATION_EXPIRED_OR_FUTURE")
    def test_timestamp_from_future_fails(self):
        self.l["snapshot_utc"]=(NOW+timedelta(minutes=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
        self.hold("C05_LIVE_OBSERVATION_EXPIRED_OR_FUTURE")
    def test_untrusted_winner_global_release_rejected(self):
        self.w["disjoint_global_liability_bound_proven"]=True
        self.hold("C05_HISTORICAL_WINNER_AUTHORITY_DRIFT")
    def test_source_sql_is_strictly_read_only_fixed_hd(self):
        sql=c05.fixed_hd_sql()
        self.assertIn("REPEATABLE READ READ ONLY",sql)
        self.assertIn("statement_timeout='8s'",sql)
        self.assertIn("current_database()='aoe2hd_db'",sql)
        self.assertTrue(sql.strip().endswith("COMMIT;"))
        import re
        for word in ("INSERT","UPDATE","DELETE","TRUNCATE","GRANT","ALTER",
                     "DROP","REVOKE","pg_terminate_backend","COPY TO PROGRAM"):
            self.assertIsNone(re.search(r"\b"+word+r"\b",sql,re.IGNORECASE))
    def test_private_source_mode_and_digest_are_required(self):
        with tempfile.TemporaryDirectory(prefix="c05-identity-") as tmp:
            base=Path(tmp);base.chmod(0o700)
            p=base/"source.json";raw=b'{"a":1}'
            p.write_bytes(raw);p.chmod(0o600)
            sig=hashlib.sha256(raw).hexdigest()
            self.assertEqual(c05.read_private(p,sig),{"a":1})
            with self.assertRaisesRegex(c05.Hold,"C05_SOURCE_SHA_DRIFT"):
                c05.read_private(p,"0"*64)
            p.chmod(0o644)
            with self.assertRaisesRegex(c05.Hold,"C05_UNSAFE_SOURCE_FILE"):
                c05.read_private(p,sig)
            p.chmod(0o600)
            alias=base/"alias.json";alias.symlink_to(p)
            with self.assertRaisesRegex(c05.Hold,"C05_UNSAFE_SOURCE_PATH"):
                c05.read_private(alias,sig)
    def test_duplicate_json_key_rejected(self):
        with tempfile.TemporaryDirectory(prefix="c05-identity-") as tmp:
            base=Path(tmp);base.chmod(0o700)
            p=base/"dupe.json";raw=b'{"a":1,"a":2}'
            p.write_bytes(raw);p.chmod(0o600)
            with self.assertRaisesRegex(c05.Hold,"C05_DUPLICATE_JSON_KEY"):
                c05.read_private(p,hashlib.sha256(raw).hexdigest())
    def test_sql_cli_ends_hold(self):
        import contextlib,io
        out=io.StringIO()
        with contextlib.redirect_stdout(out):
            status=c05.main(["--emit-hd-sql"])
        self.assertEqual(status,3)
        self.assertIn("READ ONLY",out.getvalue())
    def test_missing_evidence_cli_stops(self):
        import contextlib,io
        out=io.StringIO()
        with contextlib.redirect_stdout(out):
            status=c05.main(["--classify"])
        self.assertEqual(status,2)
        self.assertIn('"status": "STOP"',out.getvalue())
        self.assertIn('"financial_release_authorized": false',out.getvalue())

if __name__=="__main__":
    unittest.main()

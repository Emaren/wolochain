"""Root-only financial observer drift watcher: HOLD not a release permit."""
import importlib.util
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

BASE=Path(__file__).resolve().parents[1]
P=BASE/"scripts/settlement_c03_observer_watchdog.py"
spec=importlib.util.spec_from_file_location("c03watch",P)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

def sample():
    return {
      "schema":"wolo.c03.physical-writer-universe-hold.v1",
      "status":"HOLD","paymentAuthorized":False,"backupAuthorized":False,
      "fenceAndQuiescenceProven":False,
      "databaseOwnershipChanged":False,"unitsModified":False,
      "discoveredUnitCount":2,"unscopedUnitCount":1,
      "census":{"systemdUnits":[
        {"unit":"aoe2hdbets-web-prod.service","active":True},
        {"unit":"traffic-v2-forward-ledger-aoe2hdbets.timer","active":True}],
        "legacyDbOwner":{
           "aoe2hd_db":{"finance_writer_capability":True,
                         "implicit_owner_or_schema_bypass":True,
                         "finance_relations_owned":24,
                         "legacy_database_owner":1},
           "aoe2de_db":{"finance_writer_capability":True,
                         "implicit_owner_or_schema_bypass":True,
                         "finance_relations_owned":10,
                         "legacy_database_owner":1}
        }}
    }

class MonitorTests(unittest.TestCase):
    def test_unenrolled_holds_without_source_or_key_trust(self):
        r=m.reduced_observation(sample(),3,None)
        self.assertEqual(r["status"],"HOLD_UNENROLLED")
        self.assertFalse(r["financialReleaseAuthorized"])
        self.assertFalse(r["backupCertified"])
        self.assertFalse(r["autoRemediation"])
        self.assertFalse(r["fundedPermitIssued"])

    def test_pinned_no_drift_and_extra_unit_drift(self):
        r=m.reduced_observation(sample(),3,None)
        enrollment={"unit_names_sha256":r["unitNamesSha256"]}
        self.assertEqual(m.reduced_observation(sample(),3,enrollment)["status"],
                         "HOLD_EXPECTED_UNCONTAINED")
        enrollment["unit_names_sha256"]="0"*64
        x=m.reduced_observation(sample(),3,enrollment)
        self.assertEqual(x["status"],"HOLD_UNIT_DRIFT")
        self.assertIs(x["driftDetected"],True)

    def test_any_release_or_strange_exit_fails(self):
        for flag in ("paymentAuthorized","backupAuthorized",
                     "fenceAndQuiescenceProven","databaseOwnershipChanged","unitsModified"):
            value=sample()
            value[flag]=True
            with self.subTest(flag=flag),self.assertRaises(m.Stop):
                m.reduced_observation(value,3,None)
        with self.assertRaises(m.Stop):
            m.reduced_observation(sample(),0,None)

    def test_bad_db_owner_and_dup_names_fail(self):
        x=sample()
        x["census"]["legacyDbOwner"]["aoe2hd_db"]["finance_writer_capability"]=False
        with self.assertRaises(m.Stop):
            m.reduced_observation(x,3,None)
        y=sample()
        y["census"]["systemdUnits"][1]["unit"]="aoe2hdbets-web-prod.service"
        with self.assertRaises(m.Stop):
            m.reduced_observation(y,3,None)

    def test_unbounded_census_and_inconsistent_counts_fail(self):
        for field,value in (("discoveredUnitCount",3),("unscopedUnitCount",5)):
            x=sample()
            x[field]=value
            with self.subTest(field=field),self.assertRaises(m.Stop):
                m.reduced_observation(x,3,None)

    def test_exact_source_pins_not_unvalidated_literals(self):
        self.assertEqual(set(m.PINNED),{
           "settlement_c03_physical_writer_universe_hold.py",
           "settlement_c03_db_owner_boundary_hold.py"})
        for name,expected in m.PINNED.items():
            actual=hashlib.sha256((BASE/"scripts"/name).read_bytes()).hexdigest()
            self.assertEqual(actual,expected)

    def test_nonroot_cannot_write_or_query_financial_host(self):
        with patch.object(m.os,"geteuid",return_value=501):
            with self.assertRaisesRegex(m.Stop,"ROOT_LOCAL"):
                m.once()

    def test_no_implicit_baseline_enrollment(self):
        with patch.object(m,"ENROLLMENT",Path("/unlikely/c03-enrollment-missing")):
            self.assertIsNone(m.read_enrollment())

    def test_immutable_receipt_creation_is_private(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            receipts=root/"receipts";receipts.mkdir(mode=0o700)
            r=m.reduced_observation(sample(),3,None)
            with patch.object(m,"DATA_ROOT",root),\
                 patch.object(m,"private_dir",return_value=None):
                a=m.write_receipt(r)
                b=m.write_receipt(r)
            files=list(receipts.iterdir())
            self.assertEqual(len(files),2)
            self.assertEqual(len(a),64)
            self.assertEqual(len(b),64)
            self.assertEqual({f.stat().st_mode&0o777 for f in files},{0o600})
            self.assertTrue(all(json.loads(f.read_text())["status"]=="HOLD_UNENROLLED" for f in files))

    def test_systemd_unit_is_read_only_and_never_stops_services(self):
        service=(BASE/"deploy/systemd/wolo-c03-observer.service").read_text()
        timer=(BASE/"deploy/systemd/wolo-c03-observer.timer").read_text()
        self.assertIn("NoNewPrivileges=yes",service)
        self.assertIn("ProtectSystem=strict",service)
        self.assertIn("RestrictAddressFamilies=AF_UNIX",service)
        self.assertIn("SuccessExitStatus=3",service)
        self.assertIn("OnUnitActiveSec=1h",timer)
        self.assertNotIn("systemctl stop",service)
        self.assertNotIn("wolochaind-mainnet.service",service)

    def test_plan_returns_financial_hold(self):
        self.assertEqual(m.main(["--mode","plan"]),3)

if __name__=="__main__":
    unittest.main()

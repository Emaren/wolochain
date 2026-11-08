"""C03 strict 67-unit read-only v2 watchdog, no financial authority.

Hermetic observable fixtures, source-hash pins, count drift, baseline
drift and legacy 57-item scope rejection. No production service or DB.
"""
import hashlib
import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import patch

BASE=Path(__file__).resolve().parents[1]
p=BASE/"scripts/settlement_c03_observer_watchdog_v2.py"
spec=importlib.util.spec_from_file_location("c03_watchdog_v2",p)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

NAMES=sorted(
    [f"aoe2war-readonly-runtime-{n:02d}.service" for n in range(24)]
    +[f"unreviewed-domain-{n:02d}.timer" for n in range(42)]
    +["tokenchain-indexer.service"]
)
assert len(NAMES)==67

def specimen():
    return {
        "schema":"wolo.c03.physical-writer-universe-hold.v1",
        "status":"HOLD","paymentAuthorized":False,
        "backupAuthorized":False,"fenceAndQuiescenceProven":False,
        "databaseOwnershipChanged":False,"unitsModified":False,
        "discoveredUnitCount":67,"unscopedUnitCount":43,
        "unprovenDomains":["tokenchain_indexer_direct_and_indirect_database_writers"],
        "census":{
            "systemdUnits":[{"unit":name,"active":False} for name in NAMES],
            "legacyDbOwner":{
                "aoe2hd_db":{"finance_writer_capability":True,
                  "implicit_owner_or_schema_bypass":True,
                  "finance_relations_owned":190,
                  "legacy_database_owner":1},
                "aoe2de_db":{"finance_writer_capability":True,
                  "implicit_owner_or_schema_bypass":True,
                  "finance_relations_owned":52,
                  "legacy_database_owner":1}
            }
        }
    }

class V2MonitorTests(unittest.TestCase):
    def test_exact_source_fingerprint_matches_merged_observer(self):
        for name,expected in m.PINNED.items():
            self.assertEqual(hashlib.sha256(
                (BASE/"scripts"/name).read_bytes()).hexdigest(),expected)
        self.assertEqual(len(m.PINNED),2)

    def test_separate_root_owner_dirs_and_schema(self):
        self.assertNotEqual(
            str(m.DATA_ROOT),"/var/lib/wolo-c03-observer")
        self.assertNotEqual(
            str(m.SOURCE_DIR),"/usr/local/libexec/wolo-c03-observer")
        self.assertNotEqual(
            str(m.ENROLLMENT),
            "/etc/wolochain-financial-maintenance/c03-observer-enrollment.json")
        self.assertIn("v2",m.SCHEMA)
        self.assertNotIn("v1",m.SCHEMA)

    def test_67_units_not_enrolled_is_hold(self):
        report=m.reduced_observation(specimen(),3,None)
        self.assertEqual(report["unitCount"],67)
        self.assertEqual(report["unscopedUnitCount"],43)
        self.assertTrue(report["extended67UnitRequired"])
        self.assertEqual(report["status"],"HOLD_UNENROLLED")
        for key in ("financialReleaseAuthorized","backupCertified",
                    "autoRemediation","fundedPermitIssued"):
            self.assertIs(report[key],False)

    def test_pinned_67_units_would_hold_without_drift(self):
        report=m.reduced_observation(specimen(),3,None)
        ent={"unit_names_sha256":report["unitNamesSha256"]}
        result=m.reduced_observation(specimen(),3,ent)
        self.assertEqual(result["status"],"HOLD_EXPECTED_UNCONTAINED")
        self.assertFalse(result["driftDetected"])
        ent["unit_names_sha256"]="0"*64
        drift=m.reduced_observation(specimen(),3,ent)
        self.assertEqual(drift["status"],"HOLD_UNIT_DRIFT")
        self.assertTrue(drift["driftDetected"])

    def test_old_57_unit_source_is_hard_stop(self):
        fixture=specimen()
        fixture["census"]["systemdUnits"]=fixture["census"]["systemdUnits"][:57]
        fixture["discoveredUnitCount"]=57
        fixture["unscopedUnitCount"]=33
        with self.assertRaisesRegex(m.Stop,"EXTENDED_67_UNIT_REVIEW_SCOPE_MISSING"):
            m.reduced_observation(fixture,3,None)

    def test_missing_external_service_review_is_hard_stop(self):
        fixture=specimen()
        fixture["unprovenDomains"]=[]
        with self.assertRaisesRegex(m.Stop,"EXTENDED_67_UNIT_REVIEW_SCOPE_MISSING"):
            m.reduced_observation(fixture,3,None)

    def test_scope_changes_fail_before_claiming_enrollment(self):
        fixture=specimen()
        fixture["unscopedUnitCount"]=42
        with self.assertRaises(m.Stop):
            m.reduced_observation(fixture,3,None)
        fixture=specimen()
        fixture["discoveredUnitCount"]=68
        with self.assertRaises(m.Stop):
            m.reduced_observation(fixture,3,None)

    def test_service_duplication_and_financial_release_fail(self):
        fixture=specimen()
        fixture["census"]["systemdUnits"][0]["unit"]=fixture["census"]["systemdUnits"][1]["unit"]
        with self.assertRaises(m.Stop):
            m.reduced_observation(fixture,3,None)
        for field in ("paymentAuthorized","backupAuthorized",
                      "fenceAndQuiescenceProven","databaseOwnershipChanged","unitsModified"):
            with self.subTest(field=field):
                fixture=specimen()
                fixture[field]=True
                with self.assertRaises(m.Stop):
                    m.reduced_observation(fixture,3,None)

    def test_nonroot_runtime_or_wrong_exit_fails(self):
        with patch.object(m.os,"geteuid",return_value=501):
            with self.assertRaises(m.Stop):
                m.once()
        with self.assertRaises(m.Stop):
            m.reduced_observation(specimen(),0,None)

    def test_plan_never_authorizes_any_funding(self):
        self.assertEqual(m.main(["--mode","plan"]),3)

    def test_real_source_never_contains_financial_actions(self):
        code=p.read_text()
        for forbidden in (
            "systemctl stop","systemctl restart","ALTER ROLE",
            "tx bank send","privileged_transfer",
            "DELETE FROM public.pending_wolo_claims",
            "GRANT ALL ON", "DROP TABLE", "INSERT INTO"):
            self.assertNotIn(forbidden,code)

if __name__=="__main__":unittest.main()

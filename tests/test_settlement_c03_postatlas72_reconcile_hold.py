"""Exact post-Atlas V1 62/V2 72 C03 topology-only review. No host/DB mutations."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
PATH=ROOT/"scripts/settlement_c03_postatlas72_reconcile_hold.py"
spec=importlib.util.spec_from_file_location("postatlas_c03",PATH)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
NAMES=json.loads((ROOT/"tests/fixtures/c03_postatlas72_unit_names_20261124.json").read_bytes())

def report(version):
    names=NAMES[version]
    count,unscoped=(62,38) if version=="v1" else (72,48)
    return {
      "schema":"wolo.c03.physical-writer-universe-hold.v1",
      "status":"HOLD","paymentAuthorized":False,"backupAuthorized":False,
      "fenceAndQuiescenceProven":False,"databaseOwnershipChanged":False,
      "unitsModified":False,"discoveredUnitCount":count,
      "unscopedUnitCount":unscoped,
      "unprovenDomains":["existing_owner_financial_writer"],
      "census":{"systemdUnits":[{"unit":x} for x in names],
        "legacyDbOwner":{n:{"finance_writer_capability":True,
          "implicit_owner_or_schema_bypass":True} for n in
          ("aoe2hd_db","aoe2de_db")}}
    }

class PostAtlas72Tests(unittest.TestCase):
    def setUp(self):
        self.v1,self.v2=report("v1"),report("v2")

    def test_genuine_five_exactly_reproduce_historical_digests(self):
        self.assertEqual(m.names_sha(NAMES["v1"]),m.V1_LIVE_SHA)
        self.assertEqual(m.names_sha(NAMES["v2"]),m.V2_LIVE_SHA)
        self.assertEqual(m.names_sha(set(NAMES["v1"])-m.FIVE),m.V1_HISTORIC_SHA)
        self.assertEqual(m.names_sha(set(NAMES["v2"])-m.FIVE),m.V2_HISTORIC_SHA)
        self.assertEqual(set(NAMES["v2"])-set(NAMES["v1"]),m.TOKENCHAIN)
        self.assertEqual(len(m.FIVE),5)

    def test_positive_source_contract_never_financial_release(self):
        r=m.reconcile(self.v1,self.v2)
        self.assertEqual(r["status"],m.STATUS)
        self.assertEqual(r["v1"]["current_count"],62)
        self.assertEqual(r["v2"]["current_count"],72)
        for key in ("financial_writer_exclusion_proven","c06_consistent_backup_certified",
                    "installed_enrollment_modified","v2_cutover_authorized",
                    "funding_authorized"):
            self.assertIs(r[key],False)
        self.assertTrue(r["requires_new_reviewed_source_and_owner_native_c03_cutover"])

    def test_v1_new_unit_swap_cannot_be_admitted(self):
        a=copy.deepcopy(self.v1)
        a["census"]["systemdUnits"][0]["unit"]="arbitrary-secret.service"
        with self.assertRaisesRegex(m.Hold,"UNREVIEWED_NEW_POST_ATLAS_NAME"):
            m.reconcile(a,self.v2)

    def test_v2_new_unit_swap_cannot_be_admitted(self):
        a=copy.deepcopy(self.v2)
        a["census"]["systemdUnits"][0]["unit"]="unknown-writer.service"
        with self.assertRaisesRegex(m.Hold,"UNREVIEWED_NEW_POST_ATLAS_NAME"):
            m.reconcile(self.v1,a)

    def test_unknown_sixth_unit_does_not_silently_rebaseline(self):
        a=copy.deepcopy(self.v2)
        a["census"]["systemdUnits"].append({"unit":"new-money.service"})
        a["discoveredUnitCount"]=73
        with self.assertRaisesRegex(m.Hold,"POST_ATLAS_UNIT_OR_UNSCOPED_COUNT_DRIFT"):
            m.reconcile(self.v1,a)

    def test_duplicate_name_refused(self):
        a=copy.deepcopy(self.v2)
        a["census"]["systemdUnits"][0]=a["census"]["systemdUnits"][1]
        with self.assertRaisesRegex(m.Hold,"DUPLICATE_UNIT_IDENTITY"):
            m.reconcile(self.v1,a)

    def test_unreviewed_count_refused(self):
        a=copy.deepcopy(self.v2)
        a["unscopedUnitCount"]=47
        with self.assertRaisesRegex(m.Hold,"POST_ATLAS_UNIT_OR_UNSCOPED_COUNT_DRIFT"):
            m.reconcile(self.v1,a)

    def test_payment_or_backup_true_refused(self):
        for name in ("paymentAuthorized","backupAuthorized","fenceAndQuiescenceProven",
                     "databaseOwnershipChanged","unitsModified"):
            a=copy.deepcopy(self.v2);a[name]=True
            with self.subTest(field=name),self.assertRaisesRegex(m.Hold,"ORIGINAL_AUDITOR_MUST_BE_FINANCE_HOLD"):
                m.reconcile(self.v1,a)

    def test_legacy_financial_owner_must_still_be_detected(self):
        a=copy.deepcopy(self.v1)
        a["census"]["legacyDbOwner"]["aoe2hd_db"]["finance_writer_capability"]=False
        with self.assertRaisesRegex(m.Hold,"FINANCIAL_WRITER_EXCLUSION_NOT_PROVEN_CANNOT_DOWNGRADE"):
            m.reconcile(a,self.v2)

    def test_missing_unproven_domain_refused(self):
        a=copy.deepcopy(self.v2);a["unprovenDomains"]=[]
        with self.assertRaisesRegex(m.Hold,"MISSING_UNPROVEN_WRITER_DOMAINS"):
            m.reconcile(self.v1,a)

    def test_wrong_report_schema_refused(self):
        a=copy.deepcopy(self.v1);a["schema"]="wolo.fake.ready.v1"
        with self.assertRaisesRegex(m.Hold,"ORIGINAL_AUDITOR_MUST_BE_FINANCE_HOLD"):
            m.reconcile(a,self.v2)

    def test_nonregular_report_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(m.Hold,"UNSAFE_AUDITOR_REPORT_FILE"):
                m.load(Path(directory))

    def test_duplicate_json_key_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/"report.json"
            p.write_bytes(b'{"status":"HOLD","status":"READY"}')
            with self.assertRaisesRegex(m.Hold,"DUPLICATE_AUDIT_JSON_KEY"):
                m.load(p)

    def test_symlink_report_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            r=Path(directory)
            (r/"real").write_text("{}")
            (r/"alias").symlink_to("real")
            with self.assertRaisesRegex(m.Hold,"UNSAFE_AUDITOR_REPORT_FILE"):
                m.load(r/"alias")

    def test_no_host_mutation_code_path(self):
        text=PATH.read_text()
        for pattern in ("systemctl start","systemctl stop","ALTER ROLE","DROP TABLE",
                        "subprocess.run(","os.unlink(","os.remove(","os.replace(",
                        "shutil.rmtree(","CREATE USER"):
            self.assertNotIn(pattern,text)

if __name__=="__main__":unittest.main()

"""C03 observer baseline is topology-only and may never certify finance."""
import importlib.util,json,hashlib
from pathlib import Path
import unittest
from unittest.mock import patch
SRC=Path(__file__).resolve().parents[1]/"scripts/settlement_c03_reviewed_topology_baseline_enrollment.py"
spec=importlib.util.spec_from_file_location("c03topology",SRC)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class AdmissionTests(unittest.TestCase):
 def sample(self):
  names=[f"synthetic-unit-{i:02d}.service" for i in range(m.UNIT_COUNT)]
  return {"status":"HOLD","paymentAuthorized":False,"backupAuthorized":False,
    "fenceAndQuiescenceProven":False,"unitsModified":False,
    "databaseOwnershipChanged":False,"unscopedUnitCount":12,
    "census":{"systemdUnits":[{"unit":x} for x in names]}}, names
 def test_schema_fixed_and_no_finance_rights(self):
  b=m.baseline()
  self.assertEqual(b["schema"],"wolo.c03.observer-baseline.v1")
  self.assertIs(b["enabled"],True)
  self.assertEqual(set(b),{"schema","enabled","source_hashes","unit_names_sha256"})
  self.assertEqual(b["source_hashes"],m.SOURCE_PINS)
 def test_expected_57_unit_census(self):
  fake,names=self.sample()
  digest=m.sha(m.canonical(sorted(names)))
  with patch.object(m,"UNIT_NAMES_SHA",digest):
   self.assertEqual(m.checked_census(fake),digest)
 def test_extra_or_missing_unit_fails(self):
  fake,names=self.sample()
  for delta in (-1,1):
   f,_=self.sample()
   f["census"]["systemdUnits"]=f["census"]["systemdUnits"][:m.UNIT_COUNT+delta] if delta<0 else f["census"]["systemdUnits"]+[{"unit":"unexpected.service"}]
   with self.subTest(delta=delta),self.assertRaises(m.Hold):m.checked_census(f)
 def test_duplicate_names_and_replaced_name_fail(self):
  fake,names=self.sample()
  fake["census"]["systemdUnits"][-1]=fake["census"]["systemdUnits"][0]
  with self.assertRaises(m.Hold):m.checked_census(fake)
  fake,names=self.sample()
  fake["census"]["systemdUnits"][0]={"unit":"new-unreviewed-financial-writer.service"}
  with self.assertRaises(m.Hold):m.checked_census(fake)
 def test_each_finance_boolean_cannot_be_weak_true_or_integer(self):
  for field in ("paymentAuthorized","backupAuthorized","fenceAndQuiescenceProven","unitsModified","databaseOwnershipChanged"):
   for not_false in (True,1,0,"false",None):
    fake,_=self.sample()
    fake[field]=not_false
    with self.subTest(field=field,value=repr(not_false)),self.assertRaises(m.Hold):m.checked_census(fake)
 def test_two_distinct_latest_receipts_required(self):
  good={"unitNamesSha256":m.UNIT_NAMES_SHA,"unitCount":m.UNIT_COUNT,
   "status":"HOLD_UNENROLLED","financialReleaseAuthorized":False,
   "sourceSha256":m.SOURCE_PINS}
  goodrows=[(Path("/root/001.json"),dict(good),"a"*64),(Path("/root/002.json"),dict(good),"b"*64)]
  self.assertEqual(m.recent_receipts(goodrows),["a"*64,"b"*64])
  with self.assertRaises(m.Hold):m.recent_receipts(goodrows[:1])
  bad=dict(good);bad["unitNamesSha256"]="f"*64
  with self.assertRaises(m.Hold):m.recent_receipts(goodrows+[(Path("/root/003.json"),bad,"c"*64)])
 def test_foreign_source_or_finance_release_receipt_rejected(self):
  good={"unitNamesSha256":m.UNIT_NAMES_SHA,"unitCount":m.UNIT_COUNT,
   "status":"HOLD_UNENROLLED","financialReleaseAuthorized":False,
   "sourceSha256":m.SOURCE_PINS}
  first=(Path("/root/001.json"),dict(good),"a"*64)
  for field,value in [("financialReleaseAuthorized",True),("status","PASS_RELEASE"),
                       ("sourceSha256",{}),("unitCount",56)]:
   bad=dict(good);bad[field]=value
   with self.subTest(field=field),self.assertRaises(m.Hold):
    m.recent_receipts([first,(Path("/root/002.json"),bad,"b"*64)])
 def test_no_nonroot_or_macos_install(self):
  with patch.object(m.os,"geteuid",return_value=501),self.assertRaisesRegex(m.Hold,"HEL1_ROOT_REQUIRED"):
   m.runtime()
  with patch.object(m.sys,"platform","darwin"),self.assertRaisesRegex(m.Hold,"HEL1_ROOT_REQUIRED"):
   m.runtime()
 def test_only_one_enrollment_file_is_named(self):
  self.assertEqual(m.TARGET.as_posix(),"/etc/wolochain-financial-maintenance/c03-observer-enrollment.json")
  self.assertEqual(m.MANIFEST.name,"C03_REVIEWED_TOPOLOGY_ONLY_BASELINE_20261106.json")
  self.assertNotIn("8092",SRC.read_text())
  self.assertNotIn("pg_terminate_backend",SRC.read_text())
 def test_both_public_and_original_production_pids_are_protected(self):
  self.assertEqual(m.PROTECTED_PIDS["aoe2hdbets-web-prod.service"],"1032308")
  self.assertEqual(m.PROTECTED_PIDS["aoe2hdbets-web.service"],"2625090")
  self.assertEqual(m.PROTECTED_PIDS["wolochaind-mainnet.service"],"1009")
if __name__=="__main__":unittest.main()

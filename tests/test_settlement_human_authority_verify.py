"""Actual Ed25519 signatures; no production credentials, DB, SSH or services."""
from __future__ import annotations
import base64
from copy import deepcopy
from datetime import datetime,timedelta,timezone
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT=Path(__file__).resolve().parents[1]/"scripts/settlement_human_authority_verify.py"
spec=importlib.util.spec_from_file_location("wolo_readonly_authority_test",SCRIPT)
a=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=a
spec.loader.exec_module(a)
NOW=datetime(2026,10,24,14,tzinfo=timezone.utc)
def iso(d): return d.isoformat().replace("+00:00","Z")

class HumanSignatureTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.temp=tempfile.TemporaryDirectory()
  root=Path(cls.temp.name)
  cls.registry={"schema":a.REGISTRY_SCHEMA,"version":1,"principals":[]}
  cls.keys={}
  for i,role in enumerate(sorted(a.ROLES)):
   keyfile=root/f"key_{i}"
   subprocess.run(["openssl","genpkey","-algorithm","Ed25519","-out",str(keyfile)],
                  check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
   pub=subprocess.check_output(["openssl","pkey","-in",str(keyfile),"-pubout"],
                               stderr=subprocess.DEVNULL).decode()
   cls.registry["principals"].append({"role":role,"person_id":f"test_person_{i}",
             "key_id":f"test_key_{i}","public_key_pem":pub})
   cls.keys[role]=keyfile
  cls.regraw=a.canonical(cls.registry)
  cls.evidence=b'{"synthetic":"read-only evidence"}'
  cls.procedure=b'{"synthetic":"nonproduction procedure"}'
  cls.capture=b'{"synthetic":"complete capture"}'
  cls.fence=b'{"synthetic":"retained fence receipt"}'
  cls.expected={"registry":a.sha(cls.regraw),"source":"a"*64,"scope":"b"*64,
                "host":"c"*64,"source_commit":"d"*40}
 @classmethod
 def tearDownClass(cls): cls.temp.cleanup()

 def sign(self,packet):
  packet["approvals"]=[]
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder)
   for p in self.registry["principals"]:
    (root/"msg").write_bytes(a.signed_message(packet["request"],p["role"],
                                             p["person_id"],p["key_id"]))
    subprocess.run(["openssl","pkeyutl","-sign","-rawin",
       "-inkey",str(self.keys[p["role"]]),"-in",str(root/"msg"),
       "-out",str(root/"sig")],check=True,capture_output=True)
    packet["approvals"].append({"role":p["role"],"person_id":p["person_id"],
       "key_id":p["key_id"],
       "signature_b64":base64.b64encode((root/"sig").read_bytes()).decode()})
  return packet

 def packet(self,phase="live_capture"):
  operation,duration,live=a.PHASES[phase]
  req={"schema":a.REQUEST_SCHEMA,"phase":phase,"operation":operation,
       "source_commit":self.expected["source_commit"],
       "tool_sha256":self.expected["source"],"scope_sha256":self.expected["scope"],
       "host_identity_sha256":self.expected["host"],
       "evidence_sha256":a.sha(self.evidence),
       "procedure_sha256":a.sha(self.procedure),
       "not_before":iso(NOW-timedelta(seconds=1)),
       "expires_at":iso(NOW+timedelta(seconds=duration-1)),
       "nonce":"1"*32,"max_total_bytes":4<<30,
       "capture_manifest_sha256":None if phase=="live_capture" else a.sha(self.capture),
       "prior_fence_receipt_sha256":None if phase=="live_capture" else a.sha(self.fence),
       "live_actions_allowed":live}
  return self.sign({"schema":a.PACKET_SCHEMA,"request":req,"approvals":[]})

 def check(self,pkt,**kw):
  return a.verify(pkt,kw.get("registry",self.registry),kw.get("raw",self.regraw),
      kw.get("ledger",{"schema":a.LEDGER_SCHEMA,"consumed":[]}),
      kw.get("expected",self.expected),kw.get("evidence",self.evidence),
      kw.get("procedure",self.procedure),kw.get("capture"),kw.get("fence"),
      now=kw.get("now",NOW))

 def reject(self,pkt,**kw):
  with self.assertRaises(a.Refusal):self.check(pkt,**kw)

 def test_valid_five_signatures_remain_nonauthorizing(self):
  r=self.check(self.packet())
  self.assertEqual(r["distinct_role_keys_cryptographically_verified"],5)
  self.assertFalse(r["producer_fence_authorized"])
  self.assertFalse(r["production_permit_issued"])
  self.assertFalse(r["real_human_identity_enrollment_verified"])
  self.assertFalse(r["nonce_atomically_consumed"])

 def test_signed_offline_phase_lineage(self):
  pkt=self.packet("offline_verify")
  r=self.check(pkt,capture=self.capture,fence=self.fence)
  self.assertEqual(r["phase"],"offline_verify")
  self.reject(pkt,capture=b"tampered",fence=self.fence)
  self.reject(pkt,capture=self.capture,fence=b"wrong receipt")
  self.reject(pkt,capture=self.capture)
  self.reject(pkt,capture=self.capture,fence=self.fence,evidence=b"tampered")

 def test_offline_cannot_escalate_to_live(self):
  pkt=self.packet("offline_verify")
  pkt["request"]["live_actions_allowed"]=True
  self.reject(self.sign(pkt),capture=self.capture,fence=self.fence)

 def test_missing_and_duplicate_signature_roles(self):
  pkt=self.packet();pkt["approvals"].pop();self.reject(pkt)
  pkt=self.packet();pkt["approvals"][-1]=deepcopy(pkt["approvals"][0]);self.reject(pkt)

 def test_forged_identity_and_invalid_signature(self):
  pkt=self.packet();pkt["approvals"][0]["person_id"]="untrusted";self.reject(pkt)
  pkt=self.packet();pkt["approvals"][0]["signature_b64"]=base64.b64encode(b"0"*64).decode()
  self.reject(pkt)

 def test_changed_request_source_and_host(self):
  for field,value in (("max_total_bytes",8<<30),("source_commit","e"*40),
                       ("host_identity_sha256","e"*64),("scope_sha256","e"*64),
                       ("evidence_sha256","e"*64),("operation","unapproved")):
   with self.subTest(field=field):
    pkt=self.packet();pkt["request"][field]=value;self.reject(self.sign(pkt))

 def test_distinct_people_and_registry_anchor(self):
  self.reject(self.packet(),raw=b"tampered registry")
  for field in ("person_id","public_key_pem","key_id"):
   reg=deepcopy(self.registry)
   reg["principals"][0][field]=reg["principals"][1][field]
   raw=a.canonical(reg)
   self.reject(self.packet(),registry=reg,raw=raw,
               expected={**self.expected,"registry":a.sha(raw)})

 def test_expiry_wrong_duration_and_clock(self):
  self.reject(self.packet(),now=NOW+timedelta(hours=1))
  pkt=self.packet();pkt["request"]["expires_at"]=iso(NOW+timedelta(minutes=31))
  self.reject(self.sign(pkt))
  pkt=self.packet("offline_verify")
  pkt["request"]["expires_at"]=iso(NOW+timedelta(hours=5))
  self.reject(self.sign(pkt),capture=self.capture,fence=self.fence)

 def test_replay_and_ledger_duplicated_nonce(self):
  pkt=self.packet()
  self.reject(pkt,ledger={"schema":a.LEDGER_SCHEMA,"consumed":["1"*32]})
  self.reject(pkt,ledger={"schema":a.LEDGER_SCHEMA,"consumed":["1"*32]*2})

 def test_signature_encoding(self):
  pkt=self.packet();pkt["approvals"][0]["signature_b64"]="!!!";self.reject(pkt)

 def test_closed_schema_and_boolean_budget(self):
  pkt=self.packet();pkt["request"]["max_total_bytes"]=True;self.reject(self.sign(pkt))
  pkt=self.packet();pkt["request"]["surprise"]="permission";self.reject(self.sign(pkt))

 def test_duplicate_json_fields(self):
  with self.assertRaises(a.Refusal):
   json.loads('{"phase":"x","phase":"y"}',object_pairs_hook=a.unique)

 def test_resume_is_separate_signed_phase(self):
  pkt=self.packet("resume")
  self.assertEqual(self.check(pkt,capture=self.capture,fence=self.fence)["phase"],"resume")
  pkt["request"]["phase"]="live_capture"
  self.reject(self.sign(pkt),capture=self.capture,fence=self.fence)

 def test_missing_capture_lineage_refused(self):
  self.reject(self.packet("offline_verify"))
  self.reject(self.packet("resume"))

if __name__=="__main__":unittest.main()

#!/usr/bin/env python3
"""Non-authorizing offline verifier for five distinct Ed25519 human approvals.

No production, network, database, wallet, or permit-writing API. A successful
cryptographic observation exits 3, never exit 0 / financial authorization.
"""
from __future__ import annotations
import argparse
import base64
import binascii
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile

DOMAIN=b"AOE2WAR-WOLO-FIVE-HUMAN-APPROVAL-V1\x00"
ROLES=frozenset(("owner","operator","chain_reviewer","finance_reviewer","recovery_witness"))
PHASES={
 "live_capture":("fence-drain-capture-hd-de",1800,True),
 "offline_verify":("isolated-restore-verify-sealed-archives",14400,False),
 "resume":("reviewed-resume-existing-hd-de-units",1800,True),
}
REQUEST_SCHEMA="wolo.five-human-approval-request.v1"
REGISTRY_SCHEMA="wolo.five-human-trust-registry.v1"
PACKET_SCHEMA="wolo.five-human-signed-packet.v1"
LEDGER_SCHEMA="wolo.five-human-consumed-nonces.v1"
HEX64=re.compile(r"[a-f0-9]{64}\Z")
HEX40=re.compile(r"[a-f0-9]{40}\Z")
HEX32=re.compile(r"[a-f0-9]{32}\Z")
ID=re.compile(r"[a-z][a-z0-9_-]{2,63}\Z")
MAX_READ=1<<20

class Refusal(ValueError): pass

def require(ok,reason):
 if not ok: raise Refusal(reason)

def sha(raw): return hashlib.sha256(raw).hexdigest()

def unique(pairs):
 out={}
 for key,value in pairs:
  require(key not in out,"DUPLICATE_JSON_FIELD")
  out[key]=value
 return out

def canonical(obj):
 return json.dumps(obj,sort_keys=True,separators=(",",":"),ensure_ascii=True).encode("ascii")

def read_file(path):
 path=Path(path)
 require(path.is_absolute(),"ABSOLUTE_INPUT_PATH_REQUIRED")
 before=path.lstat()
 require(stat.S_ISREG(before.st_mode) and before.st_nlink==1 and
         not path.is_symlink() and 0<before.st_size<=MAX_READ,"UNSAFE_INPUT")
 with os.fdopen(os.open(path,os.O_RDONLY|getattr(os,"O_NOFOLLOW",0)),"rb") as f:
  opened=os.fstat(f.fileno())
  require((opened.st_dev,opened.st_ino,opened.st_size,opened.st_mtime_ns)==
          (before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns),"INPUT_CHANGED")
  raw=f.read(MAX_READ+1)
  after=os.fstat(f.fileno())
 require(len(raw)==before.st_size and after.st_size==before.st_size and
         after.st_ctime_ns==before.st_ctime_ns and after.st_mtime_ns==before.st_mtime_ns,
         "INPUT_CHANGED")
 return raw

def parse_json(raw):
 try:
  result=json.loads(raw,object_pairs_hook=unique,
       parse_float=lambda _:(_ for _ in ()).throw(Refusal("FLOAT_FORBIDDEN")),
       parse_constant=lambda _:(_ for _ in ()).throw(Refusal("NONFINITE_FORBIDDEN")))
 except (UnicodeError,json.JSONDecodeError):
  raise Refusal("JSON_INVALID") from None
 require(type(result) is dict,"JSON_OBJECT_REQUIRED")
 return result

def utc(value):
 require(type(value) is str and value.endswith("Z"),"UTC_REQUIRED")
 try: t=datetime.fromisoformat(value[:-1]+"+00:00")
 except ValueError: raise Refusal("UTC_INVALID") from None
 require(t.utcoffset().total_seconds()==0,"UTC_REQUIRED")
 return t

def trusted_people(registry,raw,expected_sha):
 require(HEX64.fullmatch(expected_sha) and sha(raw)==expected_sha,"TRUST_ANCHOR_MISMATCH")
 require(type(registry) is dict and set(registry)=={"schema","version","principals"} and
         registry["schema"]==REGISTRY_SCHEMA and type(registry["version"]) is int and
         registry["version"]>=1,"TRUST_REGISTRY_INVALID")
 people=registry["principals"]
 require(type(people) is list and len(people)==5,"FIVE_PEOPLE_REQUIRED")
 by_role={}
 persons=set(); keys=set(); public_keys=set()
 for p in people:
  require(type(p) is dict and set(p)=={"role","person_id","key_id","public_key_pem"},
          "TRUST_ENTRY_INVALID")
  role=p["role"];person=p["person_id"];key=p["key_id"];pem=p["public_key_pem"]
  require(role in ROLES and type(person) is str and ID.fullmatch(person) and
          type(key) is str and ID.fullmatch(key) and type(pem) is str and
          pem.startswith("-----BEGIN PUBLIC KEY-----\n") and
          pem.endswith("-----END PUBLIC KEY-----\n") and len(pem)<2000,
          "TRUST_IDENTITY_INVALID")
  require(role not in by_role and person not in persons and key not in keys and
          pem not in public_keys,"HUMAN_ROLE_COLLISION")
  by_role[role]=p;persons.add(person);keys.add(key);public_keys.add(pem)
 require(set(by_role)==ROLES,"FIVE_ROLES_REQUIRED")
 return by_role

def signed_message(request,role,person,key):
 return DOMAIN+canonical({"role":role,"person_id":person,"key_id":key,"request":request})

def verify_ed25519(pem,signature,message):
 with tempfile.TemporaryDirectory(prefix="wolo-human-review-") as td:
  root=Path(td)
  (root/"key.pem").write_text(pem,encoding="ascii")
  (root/"sig").write_bytes(signature)
  (root/"msg").write_bytes(message)
  try:
   result=subprocess.run(["openssl","pkeyutl","-verify","-pubin","-rawin",
      "-inkey",str(root/"key.pem"),"-sigfile",str(root/"sig"),"-in",str(root/"msg")],
      stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=5)
  except (OSError,subprocess.TimeoutExpired):
   raise Refusal("OPENSSL_UNAVAILABLE") from None
 require(result.returncode==0,"SIGNATURE_INVALID")

def check_request(req,expected,evidence,procedure,capture,fence,used,now):
 fields={"schema","phase","operation","source_commit","tool_sha256","scope_sha256",
         "host_identity_sha256","evidence_sha256","procedure_sha256","not_before",
         "expires_at","nonce","capture_manifest_sha256","prior_fence_receipt_sha256",
         "max_total_bytes","live_actions_allowed"}
 require(type(req) is dict and set(req)==fields and
         req["schema"]==REQUEST_SCHEMA,"REQUEST_INVALID")
 phase=req["phase"]
 require(type(phase) is str and phase in PHASES,"PHASE_UNAPPROVED")
 action,maximum,live=PHASES[phase]
 require(req["operation"]==action and req["live_actions_allowed"] is live,"PHASE_ESCALATION")
 require(type(req["source_commit"]) is str and HEX40.fullmatch(req["source_commit"]) and
         req["source_commit"]==expected["source_commit"],"COMMIT_MISMATCH")
 for field,value in (("tool_sha256",expected["source"]),("scope_sha256",expected["scope"]),
                     ("host_identity_sha256",expected["host"]),
                     ("evidence_sha256",sha(evidence)),("procedure_sha256",sha(procedure))):
  require(type(req[field]) is str and HEX64.fullmatch(req[field]) and
          req[field]==value,"INDEPENDENT_EVIDENCE_MISMATCH")
 require(type(req["nonce"]) is str and HEX32.fullmatch(req["nonce"]) and
         req["nonce"] not in used,"NONCE_REUSED_OR_INVALID")
 begin=utc(req["not_before"]);end=utc(req["expires_at"])
 require(0<(end-begin).total_seconds()<=maximum and begin<=now<end,
         "EXPIRED_OR_OVERLONG_PHASE")
 require(type(req["max_total_bytes"]) is int and
         (1<<20)<=req["max_total_bytes"]<=(100<<30),"BYTE_BUDGET_INVALID")
 if phase=="live_capture":
  require(req["capture_manifest_sha256"] is None and
          req["prior_fence_receipt_sha256"] is None and capture is None and fence is None,
          "LIVE_PARENT_FORBIDDEN")
 else:
  require(capture is not None and fence is not None and
          type(req["capture_manifest_sha256"]) is str and
          type(req["prior_fence_receipt_sha256"]) is str and
          req["capture_manifest_sha256"]==sha(capture) and
          req["prior_fence_receipt_sha256"]==sha(fence),
          "CAPTURE_OR_FENCE_LINEAGE_INVALID")

def verify(packet,registry,registry_raw,ledger,expected,evidence,procedure,
           capture=None,fence=None,now=None):
 now=now or datetime.now(timezone.utc)
 require(now.tzinfo is not None,"UTC_CLOCK_REQUIRED")
 principal=trusted_people(registry,registry_raw,expected["registry"])
 require(type(ledger) is dict and set(ledger)=={"schema","consumed"} and
         ledger["schema"]==LEDGER_SCHEMA and type(ledger["consumed"]) is list and
         len(ledger["consumed"])<=100000 and
         all(type(n) is str and HEX32.fullmatch(n) for n in ledger["consumed"]) and
         len(ledger["consumed"])==len(set(ledger["consumed"])),"NONCE_LEDGER_INVALID")
 require(type(packet) is dict and set(packet)=={"schema","request","approvals"} and
         packet["schema"]==PACKET_SCHEMA,"PACKET_INVALID")
 req=packet["request"];approvals=packet["approvals"]
 check_request(req,expected,evidence,procedure,capture,fence,set(ledger["consumed"]),now)
 require(type(approvals) is list and len(approvals)==5,"FIVE_SIGNED_APPROVALS_REQUIRED")
 seen=set()
 for approval in approvals:
  require(type(approval) is dict and
          set(approval)=={"role","person_id","key_id","signature_b64"},"APPROVAL_INVALID")
  role=approval["role"]
  require(type(role) is str and role in principal and role not in seen,
          "DUPLICATE_OR_UNKNOWN_APPROVER")
  p=principal[role]
  require(approval["person_id"]==p["person_id"] and
          approval["key_id"]==p["key_id"],"APPROVER_IDENTITY_INVALID")
  try:
   require(type(approval["signature_b64"]) is str,"SIGNATURE_ENCODING_INVALID")
   signature=base64.b64decode(approval["signature_b64"],validate=True)
  except (ValueError,binascii.Error):
   raise Refusal("SIGNATURE_ENCODING_INVALID") from None
  require(len(signature)==64 and
          base64.b64encode(signature).decode()==approval["signature_b64"],
          "SIGNATURE_ENCODING_INVALID")
  verify_ed25519(p["public_key_pem"],signature,
       signed_message(req,role,p["person_id"],p["key_id"]))
  seen.add(role)
 require(seen==ROLES,"FIVE_SIGNED_APPROVALS_REQUIRED")
 return {"schema":"wolo.five-human-offline-verification.v1",
         "phase":req["phase"],"distinct_role_keys_cryptographically_verified":5,
         "trust_registry_digest_verified":True,
         "source_evidence_phase_and_expiry_verified":True,
         "nonce_replay_snapshot_checked":True,
         "real_human_identity_enrollment_verified":False,
         "nonce_atomically_consumed":False,
         "production_permit_issued":False,
         "producer_fence_authorized":False,
         "financial_release_authorized":False,
         "status":"CRYPTOGRAPHIC_EVIDENCE_VERIFIED_NONAUTHORIZING"}

def main(argv=None):
 ap=argparse.ArgumentParser(description=__doc__)
 for key in ("registry","packet","nonce-ledger","evidence","procedure"):
  ap.add_argument("--"+key,type=Path,required=True)
 for key in ("registry","source","scope","host"):
  ap.add_argument("--expected-"+key+"-sha256",required=True)
 ap.add_argument("--expected-source-commit",required=True)
 ap.add_argument("--capture-manifest",type=Path)
 ap.add_argument("--fence-receipt",type=Path)
 args=ap.parse_args(argv)
 try:
  expectation={k:getattr(args,"expected_"+k+"_sha256")
               for k in ("registry","source","scope","host")}
  require(all(type(d) is str and HEX64.fullmatch(d) for d in expectation.values()),
          "TRUST_EXPECTATION_INVALID")
  require(HEX40.fullmatch(args.expected_source_commit),"SOURCE_COMMIT_INVALID")
  expectation["source_commit"]=args.expected_source_commit
  raw=read_file(args.registry)
  result=verify(parse_json(read_file(args.packet)),parse_json(raw),raw,
      parse_json(read_file(args.nonce_ledger)),expectation,
      read_file(args.evidence),read_file(args.procedure),
      read_file(args.capture_manifest) if args.capture_manifest else None,
      read_file(args.fence_receipt) if args.fence_receipt else None)
  print(json.dumps(result,sort_keys=True))
  return 3
 except (Refusal,OSError) as error:
  print("HOLD: "+(str(error) if isinstance(error,Refusal) else "INPUT_UNAVAILABLE"))
  return 2

if __name__=="__main__":raise SystemExit(main())

#!/usr/bin/env python3
"""C03 topology-only one-use baseline enrollment. NEVER admits financial writes.

This permits unattended unit-*name* drift detection while preserving every
financial HARD HOLD. Requires independently reviewed, source-bound live census.
"""
from __future__ import annotations
import argparse
from datetime import datetime,timezone
import hashlib,json,os
from pathlib import Path
import re,stat,subprocess,sys

SCHEMA="wolo.c03.observer-baseline.v1"
UNIT_NAMES_SHA="83f15ae92e7420822f0c10ce3ad0d9e39eef2b913f6697bd750c36a91f80a1de"
UNIT_COUNT=57
SOURCE_DIR=Path("/usr/local/libexec/wolo-c03-observer")
ROOT=Path("/var/lib/wolo-c03-observer")
RECEIPTS=ROOT/"receipts"
TARGET=Path("/etc/wolochain-financial-maintenance/c03-observer-enrollment.json")
MANIFEST=ROOT/"C03_REVIEWED_TOPOLOGY_ONLY_BASELINE_20261106.json"
WATCHDOG_SHA="f2df45b3efe7868c130d864e348a3c50da8fcf21d06d67dd478f88994398b707"
SOURCE_PINS={
 "settlement_c03_physical_writer_universe_hold.py":"339540b550219b592554bbd0898447c3bf5f206f758bc8d8dea4e7500661c35b",
 "settlement_c03_db_owner_boundary_hold.py":"294a4427702d6fd9ab7265ea5e7e0ec1e7816f1c5194c6f37781591b1337cd87",
}
PROTECTED_PIDS={
 "aoe2hdbets-web-prod.service":"1032308",
 "aoe2hdbets-web.service":"2625090",
 "wolochaind-mainnet.service":"1009",
 "wolochain-mainnet-settlement.service":"1012",
 "wolochain-founder-rewards-settlement.service":"1010",
}
class Hold(ValueError):pass
def need(value,reason):
 if not value:raise Hold(reason)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def canonical(value):return json.dumps(value,sort_keys=True,separators=(",",":")).encode()
def dirproof(path):
 s=path.lstat()
 need(stat.S_ISDIR(s.st_mode) and not path.is_symlink() and s.st_uid==0
      and stat.S_IMODE(s.st_mode)==0o700,"PRIVATE_ROOT_DIR_INVALID:"+path.name)
def pinned(path,expected,mode):
 s=path.lstat()
 need(stat.S_ISREG(s.st_mode) and not path.is_symlink() and s.st_uid==0
      and s.st_nlink==1 and stat.S_IMODE(s.st_mode)==mode
      and sha(path.read_bytes())==expected,"PINNED_SOURCE_OR_MODE_DRIFT:"+path.name)
def cmd(argv,timeout=25):
 return subprocess.run(argv,capture_output=True,text=True,timeout=timeout,check=False)
def current_pids():
 for unit,expected in PROTECTED_PIDS.items():
  p=cmd(["systemctl","show",unit,"-p","MainPID,ActiveState"],timeout=7)
  lines=p.stdout.splitlines()
  need(p.returncode==0 and "MainPID="+expected in lines and "ActiveState=active" in lines,
       "PROTECTED_RUNTIME_CHANGED:"+unit)
def runtime():
 need(os.geteuid()==0 and sys.platform=="linux","HEL1_ROOT_REQUIRED")
 for path in (SOURCE_DIR,ROOT,RECEIPTS,TARGET.parent):dirproof(path)
 need(not TARGET.exists() and not TARGET.is_symlink(),"BASELINE_ALREADY_EXISTS")
 need(not MANIFEST.exists() and not MANIFEST.is_symlink(),"MANIFEST_ALREADY_EXISTS")
 pinned(SOURCE_DIR/"settlement_c03_observer_watchdog.py",WATCHDOG_SHA,0o600)
 for name,digest in SOURCE_PINS.items():pinned(SOURCE_DIR/name,digest,0o600)
 current_pids()
 n=cmd(["nginx","-T"],timeout=15)
 need(n.returncode==0 and n.stdout.count("proxy_pass http://127.0.0.1:3032;")==6,
      "PUBLIC_SELECTORS_NOT_EXACT_SIX")
 for port in ("8094","8095"):
  x=cmd(["ss","-H","-tln","sport = :"+port],timeout=5)
  need(x.returncode==0 and not x.stdout.strip(),"FINANCIAL_CANDIDATE_PORT_OPEN")
 service=cmd(["systemctl","show","wolo-c03-observer.service",
              "-p","ActiveState,Result,ExecMainStatus"],timeout=7)
 timer=cmd(["systemctl","show","wolo-c03-observer.timer",
            "-p","ActiveState,UnitFileState"],timeout=7)
 need("ActiveState=inactive" in service.stdout.splitlines() and
      "ActiveState=active" in timer.stdout.splitlines() and
      "UnitFileState=enabled" in timer.stdout.splitlines(),
      "OBSERVER_UNIT_OR_TIMER_NOT_ADMITTED")
def baseline():
 return {"schema":SCHEMA,"unit_names_sha256":UNIT_NAMES_SHA,
         "source_hashes":dict(SOURCE_PINS),"enabled":True}
def checked_census(observation):
 need(type(observation) is dict and observation.get("status")=="HOLD" and
      observation.get("paymentAuthorized") is False and
      observation.get("backupAuthorized") is False and
      observation.get("fenceAndQuiescenceProven") is False and
      observation.get("unitsModified") is False,"AUDITOR_FINANCE_HOLD_UNQUALIFIED")
 rows=observation.get("census",{}).get("systemdUnits")
 need(type(rows) is list and len(rows)==UNIT_COUNT,"UNIT_COUNT_CHANGED")
 names=[x.get("unit") for x in rows if type(x) is dict]
 need(len(names)==UNIT_COUNT and len(set(names))==len(names),"UNIT_NAMES_INVALID")
 digest=sha(canonical(sorted(names)))
 need(digest==UNIT_NAMES_SHA,"REVIEWED_UNIT_NAMES_CHANGED")
 need(observation.get("unscopedUnitCount",0)>0,"EXPECTED_UNCONTAINED_GRAPH_DISAPPEARED")
 need(observation.get("databaseOwnershipChanged") is False,"DB_OWNER_CHANGED")
 return digest
def source_census():
 p=cmd(["/usr/bin/python3","-B",str(SOURCE_DIR/
          "settlement_c03_physical_writer_universe_hold.py")],timeout=100)
 need(p.returncode==3 and not p.stderr.strip() and len(p.stdout)<300000,
      "READONLY_AUDITOR_NOT_HEALTHY")
 try:record=json.loads(p.stdout)
 except ValueError as e:raise Hold("SOURCE_CENSUS_JSON_UNAVAILABLE") from e
 return checked_census(record)
def receipts():
 data=[]
 for path in RECEIPTS.iterdir():
  if not path.name.endswith(".json"):continue
  s=path.lstat()
  need(stat.S_ISREG(s.st_mode) and not path.is_symlink() and
       s.st_uid==0 and stat.S_IMODE(s.st_mode)==0o600,
       "UNSAFE_PRIVATE_OBSERVER_RECEIPT")
  try:record=json.loads(path.read_text())
  except (ValueError,UnicodeError) as e:raise Hold("MALFORMED_OBSERVER_RECEIPT") from e
  data.append((path,record,sha(path.read_bytes())))
 return sorted(data,key=lambda x:x[0].name)
def recent_receipts(data):
 matching=[x for x in data if x[1].get("unitNamesSha256")==UNIT_NAMES_SHA and
           x[1].get("unitCount")==UNIT_COUNT and
           x[1].get("status")=="HOLD_UNENROLLED" and
           x[1].get("financialReleaseAuthorized") is False and
           x[1].get("sourceSha256")==SOURCE_PINS]
 need(len(matching)>=2,"TWO_QUALIFIED_STABLE_RECEIPTS_REQUIRED")
 need(data[-1] in matching and data[-2] in matching,
      "LATEST_OBSERVATIONS_DRIFTED")
 return [x[2] for x in matching[-2:]]
def write_once(path,payload):
 fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
 with os.fdopen(fd,"wb") as f:f.write(payload);f.flush();os.fsync(f.fileno())
 pinned(path,sha(payload),0o600)
def apply():
 runtime()
 before=receipts()
 evidence=recent_receipts(before)
 source_census()
 reviewed=baseline()
 raw=canonical(reviewed)+b"\n"
 write_once(TARGET,raw)
 try:
  s=cmd(["systemctl","start","wolo-c03-observer.service"],timeout=115)
  need(s.returncode==0,"ENROLLED_OBSERVER_EXECUTION_FAILED")
  afterwards=receipts()
  need(len(afterwards)==len(before)+1,"NEW_OBSERVATION_RECEIPT_COUNT")
  record=afterwards[-1][1]
  need(record.get("status")=="HOLD_EXPECTED_UNCONTAINED" and
       record.get("unitNamesSha256")==UNIT_NAMES_SHA and
       record.get("enrolled") is True and
       record.get("driftDetected") is False and
       record.get("financialReleaseAuthorized") is False and
       record.get("backupCertified") is False and
       record.get("autoRemediation") is False,
       "ENROLLED_REPORT_NOT_STRICT_FINANCIAL_HOLD")
  current_pids()
  record_sha=afterwards[-1][2]
  result={"status":"PASS_TOPOLOGY_DRIFT_BASELINE_ENROLLED_FINANCE_HARD_HOLD",
   "schema":"wolo.c03.topology-baseline-enrollment-receipt.v1",
   "utc":datetime.now(timezone.utc).isoformat(),
   "unitCount":UNIT_COUNT,"unitNamesSha256":UNIT_NAMES_SHA,
   "sourcePins":SOURCE_PINS,"previousReceiptSha256":evidence,
   "enrolledReceiptSha256":record_sha,"baselineSha256":sha(raw),
   "baselineIsFinancePermission":False,"financialReleaseAuthorized":False,
   "writerFenceProven":False,"backupCertified":False,"fundedPermitIssued":False}
  write_once(MANIFEST,canonical(result)+b"\n")
  return result
 except BaseException:
  # Remove only our freshly created, exact-sha file; never alter older keys.
  if TARGET.is_file() and not TARGET.is_symlink() and sha(TARGET.read_bytes())==sha(raw):
   TARGET.unlink()
  raise
def main():
 parser=argparse.ArgumentParser()
 parser.add_argument("--mode",choices=("inspect","apply"),default="inspect")
 args=parser.parse_args()
 try:
  if args.mode=="inspect":
   runtime();evidence=recent_receipts(receipts());source_census()
   result={"status":"PASS_REVIEWED_TOPOLOGY_ONLY_PREFLIGHT_FINANCE_HOLD",
           "unitCount":UNIT_COUNT,"unitNamesSha256":UNIT_NAMES_SHA,
           "pastReceipts":evidence,"financialReleaseAuthorized":False}
  else:result=apply()
  print(json.dumps(result,sort_keys=True))
  return 0
 except (Hold,ValueError,OSError,subprocess.SubprocessError) as exc:
  print(json.dumps({"status":"HOLD","reason":str(exc)[:140],
                    "financialReleaseAuthorized":False},sort_keys=True))
  return 2
if __name__=="__main__":sys.exit(main())

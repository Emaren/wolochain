#!/usr/bin/env python3
"""C03 observational-only 57->67 watchdog systemd handoff, root physical HOLD.

Never changes a financial writer, DB role, website, Wolo account or signer.
The existing hourly observation is stopped briefly and restored on failure.
This is NOT a financial release permit or a C03 full writer-fence closure.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys

OLD_DIR=Path("/usr/local/libexec/wolo-c03-observer")
NEW_DIR=Path("/usr/local/libexec/wolo-c03-observer-v2")
OLD_DATA=Path("/var/lib/wolo-c03-observer")
NEW_DATA=Path("/var/lib/wolo-c03-observer-v2")
OLD_ENROLL=Path("/etc/wolochain-financial-maintenance/c03-observer-enrollment.json")
NEW_ENROLL=Path("/etc/wolochain-financial-maintenance/c03-observer-enrollment-v2.json")
UNIT=Path("/etc/systemd/system/wolo-c03-observer.service")
TIMER=Path("/etc/systemd/system/wolo-c03-observer.timer")
ROOT=Path("/root/aoe2war-c03-observer-v2-cutover-20261108")
LOCK=Path("/run/lock/aoe2war-c03-observer-v2-cutover.lock")

UNIT_SHA="e3f0effe2d7781b98f0584f3458c2fe269d4c17c94f9400587c9dc90bc2b3849"
TIMER_SHA="5c2c9043338d1d31bfb9bd5d1da540b19ecb3c1a03d23aa33b01dc1b9524cd6e"
V1_ENROLL_SHA="67ba18c7b32fb19a3a5f5a611bd60bd3e519519d5af4ff3e4a9224f2941b595c"
UNIT_NAMES_SHA="96026be468a9fd2cc6a65c8119ad83c8fd915a3233ef98c247fe90a319d745f0"
V1_SHA={
 "settlement_c03_observer_watchdog.py":"f2df45b3efe7868c130d864e348a3c50da8fcf21d06d67dd478f88994398b707",
 "settlement_c03_physical_writer_universe_hold.py":"339540b550219b592554bbd0898447c3bf5f206f758bc8d8dea4e7500661c35b",
 "settlement_c03_db_owner_boundary_hold.py":"294a4427702d6fd9ab7265ea5e7e0ec1e7816f1c5194c6f37781591b1337cd87",
}
V2_SHA={
 "settlement_c03_observer_watchdog_v2.py":"793c58385c7895c2da8464a0b14ee4ea42ea13a5610cb57e3866ddd575fa558e",
 "settlement_c03_physical_writer_universe_hold.py":"0b14bc7dc6505bef8162eed87f7cac314d2782f0b9bfe3d7660de327cc88d811",
 "settlement_c03_db_owner_boundary_hold.py":"504b85a9002c82a8150d468bc9c627b18eb97586565323de9d26857bfddee57b",
}
SOURCE_SHA_SET={k:v for k,v in V2_SHA.items() if k!="settlement_c03_observer_watchdog_v2.py"}
ENROLL_SCHEMA="wolo.c03.observer-baseline.v2"
SCHEMA="wolo.c03.telemetry-v2-reversible-systemd-cutover-hardhold.v1"
HEX64=re.compile("[0-9a-f]{64}\\Z")

class Hold(ValueError):pass

def need(ok,why):
    if not ok:raise Hold(why)

def sha(raw):return hashlib.sha256(raw).hexdigest()

def jsonbytes(obj):
    return (json.dumps(obj,sort_keys=True,indent=2)+"\n").encode()

def checkdir(p):
    s=p.lstat()
    need(stat.S_ISDIR(s.st_mode) and not p.is_symlink() and
         s.st_uid==0 and stat.S_IMODE(s.st_mode)==0o700,
         "ROOT_PRIVATE_DIRECTORY_DRIFT")

def checkfile(p,expected,mode):
    s=p.lstat()
    need(stat.S_ISREG(s.st_mode) and not p.is_symlink() and
         s.st_uid==0 and s.st_nlink==1 and stat.S_IMODE(s.st_mode)==mode,
         "EXPECTED_ROOT_FILE_OR_MODE_DRIFT")
    raw=p.read_bytes()
    need(sha(raw)==expected,"PINNED_FILE_CHANGED")
    return raw

def run(args,timeout=17):
    r=subprocess.run(args,capture_output=True,text=True,timeout=timeout,check=False)
    return r

def good(args,timeout=17):
    r=run(args,timeout)
    need(r.returncode==0,"SYSTEMD_CONTROL_FAILED")
    return r.stdout

def state(unit):
    r=good(["systemctl","show",unit,"-p","MainPID","-p","ActiveState",
            "-p","UnitFileState","-p","ExecMainStatus"],timeout=5)
    return dict(line.split("=",1) for line in r.splitlines() if "=" in line)

def candidate(original:bytes):
    need(sha(original)==UNIT_SHA,"ORIGINAL_SERVICE_UNIT_SHA_CHANGED")
    old_src=b"/usr/local/libexec/wolo-c03-observer"
    old_data=b"/var/lib/wolo-c03-observer"
    old_file=b"/settlement_c03_observer_watchdog.py"
    need(original.count(old_src)==2 and original.count(old_data)==2
         and original.count(old_file)==1,"OLD_UNIT_REPLACE_SHAPE_DRIFT")
    rewritten=original.replace(old_src,str(NEW_DIR).encode())
    rewritten=rewritten.replace(old_data,str(NEW_DATA).encode())
    rewritten=rewritten.replace(old_file,b"/settlement_c03_observer_watchdog_v2.py")
    need(rewritten.count(str(NEW_DIR).encode())==2
         and rewritten.count(str(NEW_DATA).encode())==2
         and rewritten.count(b"ReadWritePaths=/var/lib/wolo-c03-observer-v2")==1
         and b"SuccessExitStatus=3" in rewritten
         and b"NoNewPrivileges=yes" in rewritten
         and b"ProtectSystem=strict" in rewritten
         and b"RestrictAddressFamilies=AF_UNIX" in rewritten
         and b"Type=oneshot" in rewritten
         and b"systemctl" not in rewritten,
         "V2_UNIT_NOT_EXACT_READONLY_SUBSTITUTION")
    return rewritten

def stable_receipts():
    root=NEW_DATA/"receipts"
    checkdir(NEW_DATA);checkdir(root)
    files=sorted(root.glob("*.json"))
    need(2<=len(files)<=50,"V2_STABLE_OBSERVATIONS_REQUIRED")
    selected=files[-2:]
    result=[]
    for p in selected:
        s=p.lstat()
        need(stat.S_ISREG(s.st_mode) and not p.is_symlink()
             and s.st_uid==0 and stat.S_IMODE(s.st_mode)==0o600,
             "C03_V2_EVIDENCE_NOT_PRIVATE")
        raw=p.read_bytes()
        j=json.loads(raw)
        need(j.get("unitCount")==67 and j.get("unscopedUnitCount")==43
             and j.get("unitNamesSha256")==UNIT_NAMES_SHA
             and j.get("sourceSha256")==SOURCE_SHA_SET
             and j.get("status")=="HOLD_UNENROLLED"
             and j.get("financialReleaseAuthorized") is False
             and j.get("extended67UnitRequired") is True
             and j.get("autoRemediation") is False,
             "C03_V2_EVIDENCE_NOT_STRICT_FINANCIAL_HOLD")
        result.append(sha(raw))
    need(len(set(result))==2,"DUPLICATE_V2_PHYSICAL_OBSERVATIONS")
    return result

def live_census():
    p=run(["/usr/bin/python3","-B",str(
      NEW_DIR/"settlement_c03_physical_writer_universe_hold.py")],timeout=100)
    need(p.returncode==3 and not p.stderr.strip()
         and len(p.stdout.encode())<300000,
         "C03_EXTENDED_SOURCE_CENSUS_NOT_HEALTHY")
    j=json.loads(p.stdout)
    rows=j.get("census",{}).get("systemdUnits")
    need(j.get("status")=="HOLD"
         and j.get("paymentAuthorized") is False
         and j.get("fenceAndQuiescenceProven") is False
         and j.get("unitsModified") is False
         and j.get("databaseOwnershipChanged") is False
         and isinstance(rows,list) and len(rows)==67
         and j.get("unscopedUnitCount")==43,
         "C03_NEW_SOURCE_CENSUS_DRIFT")
    names=sorted(x["unit"] for x in rows)
    need(len(set(names))==67 and
         sha(json.dumps(names,sort_keys=True,separators=(",",":")).encode())
         ==UNIT_NAMES_SHA,
         "C03_EXTENDED_NAME_BASELINE_CHANGED")
    return j

def endpoints_held():
    rows=good(["ss","-H","-ltn"],timeout=5).splitlines()
    need(not any(":8094 " in r or ":8095 " in r for r in rows),
         "FUNDED_SATCHEL_PORT_ALREADY_OPEN")
    validator=state("wolochaind-mainnet.service")
    need(validator.get("ActiveState")=="active"
         and validator.get("MainPID")=="1009",
         "WOLONODE_PROTECTED_PID_DRIFT")
    for unit in ("wolo-satchel-c01.service","wolo-reviewer-c01.service"):
        s=state(unit)
        need(s.get("ActiveState")=="inactive"
             and s.get("MainPID")=="0",
             "FINANCIAL_SERVICE_NOT_INACTIVE")

def preflight():
    need(os.geteuid()==0 and sys.platform.startswith("linux"),
         "HEL1_ROOT_REQUIRED")
    need(not NEW_ENROLL.exists() and not NEW_ENROLL.is_symlink(),
         "V2_ENROLLMENT_ALREADY_PRESENT")
    need(not ROOT.exists() and not ROOT.is_symlink(),
         "CUTOVER_RECEIPT_ROOT_ALREADY_EXISTS")
    for p in (OLD_DIR,NEW_DIR,OLD_DATA,NEW_DATA,NEW_DATA/"receipts",
              NEW_ENROLL.parent):
        checkdir(p)
    original=checkfile(UNIT,UNIT_SHA,0o644)
    checkfile(TIMER,TIMER_SHA,0o644)
    checkfile(OLD_ENROLL,V1_ENROLL_SHA,0o600)
    for name,digest in V1_SHA.items():checkfile(OLD_DIR/name,digest,0o600)
    for name,digest in V2_SHA.items():checkfile(NEW_DIR/name,digest,0o600)
    service=state("wolo-c03-observer.service")
    timer=state("wolo-c03-observer.timer")
    need(service.get("ActiveState")=="inactive" and
         service.get("MainPID")=="0" and service.get("ExecMainStatus")=="3",
         "OLD_C03_OBSERVER_RUNNING_OR_UNEXPECTED")
    need(timer.get("ActiveState")=="active" and
         timer.get("UnitFileState")=="enabled",
         "OLD_C03_OBSERVER_TIMER_CHANGED")
    endpoints_held()
    evidence=stable_receipts()
    live_census()
    return original,candidate(original),evidence

def write_exclusive(path:Path,raw:bytes,mode:int):
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,mode)
    with os.fdopen(fd,"wb") as f:
        f.write(raw);f.flush();os.fsync(f.fileno())
    need(stat.S_IMODE(path.stat().st_mode)==mode,
         "EXCLUSIVE_ROOT_FILE_PERMISSIONS_CHANGED")

def replace_unit(raw:bytes):
    temp=UNIT.with_name(".wolo-c03-observer-v2-swap-"+sha(raw)[:12]+".service")
    need(not temp.exists() and not temp.is_symlink(),
         "SUSPICIOUS_PREEXISTING_UNIT_TEMP")
    write_exclusive(temp,raw,0o644)
    need(sha(temp.read_bytes())==sha(raw),"TEMP_UNIT_CONTENT_CHANGED")
    os.replace(temp,UNIT)

def enroll_bytes():
    return jsonbytes({
        "schema":ENROLL_SCHEMA,"unit_names_sha256":UNIT_NAMES_SHA,
        "source_hashes":SOURCE_SHA_SET,"enabled":True})

def rollback(original:bytes,enrollment_hash:str):
    # Roll back only the telemetry service and *our exact* V2 enrollment.
    if sha(UNIT.read_bytes())!=sha(original):
        replace_unit(original)
    good(["systemctl","daemon-reload"],timeout=18)
    good(["systemctl","start","wolo-c03-observer.timer"],timeout=10)
    need(state("wolo-c03-observer.timer").get("ActiveState")=="active",
         "OLD_C03_TIMER_ROLLBACK_NOT_ACTIVE")
    if NEW_ENROLL.is_file() and not NEW_ENROLL.is_symlink():
        need(sha(NEW_ENROLL.read_bytes())==enrollment_hash,
             "UNEXPECTED_ENROLLMENT_TAMPER_DURING_ROLLBACK")
        NEW_ENROLL.unlink()
    need(sha(UNIT.read_bytes())==UNIT_SHA,"ROLLBACK_UNIT_NOT_EXACT")
    need(sha(OLD_ENROLL.read_bytes())==V1_ENROLL_SHA,
         "ROLLBACK_V1_ENROLLMENT_DRIFT")

def apply():
    original,newunit,evidence=preflight()
    next_enroll=enroll_bytes()
    ROOT.mkdir(mode=0o700)
    write_exclusive(ROOT/"original-v1.service",original,0o600)
    write_exclusive(ROOT/"candidate-v2.service",newunit,0o600)
    # systemd-analyze accepts an inert .service path and never starts it.
    good(["systemd-analyze","verify",str(ROOT/"candidate-v2.service")],
         timeout=25)
    enrollment_hash=sha(next_enroll)
    timer_paused=False
    updated=False
    try:
        good(["systemctl","stop","wolo-c03-observer.timer"],timeout=12)
        timer_paused=True
        need(state("wolo-c03-observer.service").get("ActiveState")=="inactive",
             "OLD_OBSERVER_IS_RUNNING")
        # No auth, user, treasury, finance or web services are touched.
        write_exclusive(NEW_ENROLL,next_enroll,0o600)
        replace_unit(newunit)
        updated=True
        good(["systemctl","daemon-reload"],timeout=18)
        before=len(list((NEW_DATA/"receipts").glob("*.json")))
        good(["systemctl","start","wolo-c03-observer.service"],timeout=125)
        after=sorted((NEW_DATA/"receipts").glob("*.json"))
        need(len(after)==before+1,"V2_ENROLLED_RECEIPT_MISSING")
        newest=json.loads(after[-1].read_bytes())
        need(newest.get("status")=="HOLD_EXPECTED_UNCONTAINED"
             and newest.get("unitNamesSha256")==UNIT_NAMES_SHA
             and newest.get("unitCount")==67
             and newest.get("unscopedUnitCount")==43
             and newest.get("financialReleaseAuthorized") is False
             and newest.get("autoRemediation") is False
             and newest.get("backupCertified") is False,
             "V2_ENROLLED_OBSERVATION_NOT_FINANCIAL_HOLD")
        need(state("wolo-c03-observer.service").get("ExecMainStatus")=="3",
             "V2_SERVICE_EXIT_NOT_EXPECTED_HOLD")
        good(["systemctl","start","wolo-c03-observer.timer"],timeout=12)
        need(state("wolo-c03-observer.timer").get("ActiveState")=="active",
             "V2_TIMER_NOT_STARTED")
        endpoints_held()
        checkfile(OLD_ENROLL,V1_ENROLL_SHA,0o600)
        for name,digest in V1_SHA.items():checkfile(OLD_DIR/name,digest,0o600)
        result={
            "schema":SCHEMA,"status":"PASS_V2_TELEMETRY_CUTOVER_ONLY_FINANCIAL_HOLD",
            "utc":datetime.now(timezone.utc).isoformat(),
            "old_service_unit_sha256":UNIT_SHA,
            "new_service_unit_sha256":sha(newunit),
            "old_enrollment_sha256":V1_ENROLL_SHA,
            "new_enrollment_sha256":enrollment_hash,
            "source_pins":SOURCE_SHA_SET,
            "prior_receipt_sha256s":evidence,
            "new_enrolled_receipt_sha256":sha(after[-1].read_bytes()),
            "unit_names_sha256":UNIT_NAMES_SHA,
            "detected_units":67,"unreviewed_units":43,
            "source_scoped_observer_not_global_financial_fence":True,
            "old_57_source_and_enrollment_retained":True,
            "original_hourly_timer_running":True,
            "db_role_writes_or_grants":False,
            "wolo_transfers_or_signatures":False,
            "financial_release_authorized":False,
            "c03_gate_closed":False}
        write_exclusive(ROOT/"v2-cutover-success-finance-hold.json",
                         jsonbytes(result),0o600)
        return result
    except BaseException:
        if timer_paused:
            try:rollback(original,enrollment_hash)
            except BaseException:
                print("HOLD_C03_OBSERVER_ROLLBACK_REQUIRES_MANUAL_REVIEW",
                      file=sys.stderr)
                raise
        raise

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--mode",choices=("inspect","apply"),default="inspect")
    args=parser.parse_args()
    try:
        with os.fdopen(os.open(LOCK,os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600),"wb") as f:
            fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
            if args.mode=="inspect":
                before,after,evidence=preflight()
                result={"schema":SCHEMA,
                  "status":"PASS_V2_READONLY_CUTOVER_ADMISSION_FINANCE_HOLD",
                  "old_service_unit_sha256":sha(before),
                  "candidate_service_unit_sha256":sha(after),
                  "prior_evidence_sha256s":evidence,
                  "unit_names_sha256":UNIT_NAMES_SHA,
                  "financial_release_authorized":False,
                  "production_modified":False}
                rc=3
            else:
                result=apply()
                rc=0
        print(json.dumps(result,sort_keys=True))
        return rc
    except (Hold,OSError,ValueError,TypeError,subprocess.SubprocessError) as exc:
        print(json.dumps({"schema":SCHEMA,
           "status":"HOLD_C03_V2_TELEMETRY_CUTOVER_NOT_ADMITTED",
           "reason":str(exc)[:110] if isinstance(exc,Hold) else
              "UNQUALIFIED_SOURCE_OR_HOST_STATE",
           "financial_release_authorized":False},sort_keys=True))
        return 2

if __name__=="__main__":sys.exit(main())

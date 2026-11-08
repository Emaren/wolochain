#!/usr/bin/env python3
"""V2 67-unit full-discovery C03 observer, never any finance authorization.

A reviewed, separately installed systemd timer may run this root-locally.
Unenrolled source/baseline, new units and catalog drift retain financial HOLD.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys

SCHEMA = "wolo.c03.financial-writer-watchdog-extended-hold.v2"
SOURCE_DIR = Path("/usr/local/libexec/wolo-c03-observer-v2")
DATA_ROOT = Path("/var/lib/wolo-c03-observer-v2")
ENROLLMENT = Path("/etc/wolochain-financial-maintenance/c03-observer-enrollment-v2.json")
PINNED = {
    "settlement_c03_physical_writer_universe_hold.py":
        "0b14bc7dc6505bef8162eed87f7cac314d2782f0b9bfe3d7660de327cc88d811",
    "settlement_c03_db_owner_boundary_hold.py":
        "504b85a9002c82a8150d468bc9c627b18eb97586565323de9d26857bfddee57b",
}
SHA = re.compile(r"[0-9a-f]{64}\Z")
MAX_AUDITOR_BYTES = 300000
MAX_RECEIPTS = 2000
MIN_FREE_BYTES = 256 * 1024 * 1024

class Stop(ValueError):
    pass

def require(value, reason):
    if not value:
        raise Stop(reason)

def sha256(raw):
    return hashlib.sha256(raw).hexdigest()

def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()

def private_dir(path):
    st=path.lstat()
    require(stat.S_ISDIR(st.st_mode) and st.st_uid==0 and
            stat.S_IMODE(st.st_mode)==0o700 and not path.is_symlink(),
            "ROOT_PRIVATE_RECEIPT_DIR_REQUIRED")

def checked_source(path, expected):
    st=path.lstat()
    require(stat.S_ISREG(st.st_mode) and st.st_uid==0 and
            not path.is_symlink() and st.st_nlink==1 and
            not (stat.S_IMODE(st.st_mode)&0o022) and st.st_size<=80000,
            "SOURCE_PROVENANCE_UNSAFE")
    raw=path.read_bytes()
    require(sha256(raw)==expected,"PINNED_OBSERVER_SOURCE_DRIFT")
    return True

def read_enrollment():
    if not ENROLLMENT.exists():
        require(not ENROLLMENT.is_symlink(),
                "OBSERVER_BASELINE_DANGLING_SYMLINK")
        return None
    st=ENROLLMENT.lstat()
    require(stat.S_ISREG(st.st_mode) and st.st_uid==0 and
            stat.S_IMODE(st.st_mode)==0o600 and
            not ENROLLMENT.is_symlink() and st.st_size<4096,
            "UNSAFE_OBSERVER_BASELINE")
    obj=json.loads(ENROLLMENT.read_text())
    require(type(obj) is dict and
            set(obj)=={"schema","unit_names_sha256","source_hashes","enabled"} and
            obj["schema"]=="wolo.c03.observer-baseline.v2" and
            obj["enabled"] is True and
            type(obj["source_hashes"]) is dict and obj["source_hashes"]==PINNED and
            type(obj["unit_names_sha256"]) is str and
            SHA.fullmatch(obj["unit_names_sha256"]),
            "INVALID_OBSERVER_BASELINE")
    return obj

def reduced_observation(raw, exit_code, enrollment):
    require(exit_code==3 and type(raw) is dict and
            raw.get("schema")=="wolo.c03.physical-writer-universe-hold.v1" and
            raw.get("status")=="HOLD" and
            raw.get("paymentAuthorized") is False and
            raw.get("backupAuthorized") is False and
            raw.get("fenceAndQuiescenceProven") is False and
            raw.get("databaseOwnershipChanged") is False and
            raw.get("unitsModified") is False,
            "FINANCE_OBSERVER_UNEXPECTED_RELEASE_OR_STATUS")
    rows=raw.get("census",{}).get("systemdUnits")
    require(type(rows) is list and 0<len(rows)<=500,"MISSING_SYSTEMD_UNIT_CENSUS")
    names=[item.get("unit") for item in rows if type(item) is dict]
    require(len(names)==len(rows) and len(names)==len(set(names))
            and all(type(x) is str and x.endswith((".service",".timer")) for x in names),
            "DUPLICATE_OR_UNKNOWN_UNIT_IDENTITY")
    sha=sha256(canonical(sorted(names)))
    db=raw.get("census",{}).get("legacyDbOwner")
    require(type(db) is dict and set(db)=={"aoe2hd_db","aoe2de_db"} and
            all(type(v) is dict and v.get("finance_writer_capability") is True
                and v.get("implicit_owner_or_schema_bypass") is True for v in db.values()),
            "LIVE_OWNER_OBSERVATION_NOT_QUALIFIED")
    # The extended review must never downgrade to the original 57-unit list.
    # Exact baseline count is independently reviewed and pinned at enrollment.
    require(len(names)==67 and
            raw.get("unscopedUnitCount")==43 and
            type(raw.get("unprovenDomains")) is list and
            len(raw["unprovenDomains"]) >= 1,
            "EXTENDED_67_UNIT_REVIEW_SCOPE_MISSING")
    require(raw.get("discoveredUnitCount")==len(names) and
            type(raw.get("unscopedUnitCount")) is int and
            raw["unscopedUnitCount"] <= len(names),
            "UNSCOPED_UNIT_CENSUS_DRIFT")
    is_enrolled=enrollment is not None
    has_drift=is_enrolled and sha != enrollment["unit_names_sha256"]
    return {
        "schema":SCHEMA,"observedUtc":datetime.now(timezone.utc).isoformat(),
        "status":"HOLD_UNIT_DRIFT" if has_drift else
                 ("HOLD_EXPECTED_UNCONTAINED" if is_enrolled else "HOLD_UNENROLLED"),
        "unitNamesSha256":sha,
        "sourceSha256":dict(PINNED),
        "extended67UnitRequired":True,
        "unitCount":len(names),
        "unscopedUnitCount":raw["unscopedUnitCount"],
        "legacyOwnerFinances":{
            name:{"financeRelationsOwned":db[name].get("finance_relations_owned"),
                  "dbOwner":db[name].get("legacy_database_owner")}
            for name in sorted(db)},
        "enrolled":is_enrolled,"driftDetected":bool(has_drift),
        "sourceObserverReturnedHold":True,
        "financialReleaseAuthorized":False,
        "backupCertified":False,
        "autoRemediation":False,
        "fundedPermitIssued":False,
    }

def write_receipt(report):
    private_dir(DATA_ROOT)
    receipts=DATA_ROOT/"receipts"
    private_dir(receipts)
    space=os.statvfs(receipts)
    require(space.f_bavail*space.f_frsize>=MIN_FREE_BYTES,
            "RECEIPT_VOLUME_LOW_CAPACITY")
    require(sum(1 for _ in receipts.iterdir())<MAX_RECEIPTS,
            "RECEIPT_RETENTION_REVIEW_REQUIRED")
    # Append-only, no overwrite. No secrets or database rows in this summary.
    stamp=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    name=stamp+"-"+sha256(canonical(report))[:12]+".json"
    target=receipts/name
    fd=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,"wb") as out:
        out.write(canonical(report)+b"\n")
        out.flush()
        os.fsync(out.fileno())
    return sha256(target.read_bytes())

def once():
    require(os.geteuid()==0,"ROOT_LOCAL_MONITOR_REQUIRED")
    private_dir(SOURCE_DIR)
    for name,digest in PINNED.items():
        checked_source(SOURCE_DIR/name,digest)
    enrollment=read_enrollment()
    auditor=SOURCE_DIR/"settlement_c03_physical_writer_universe_hold.py"
    p=subprocess.run([sys.executable,"-B",str(auditor)],
                     stdin=subprocess.DEVNULL,capture_output=True,
                     env={"PATH":"/usr/sbin:/usr/bin:/bin","LANG":"C.UTF-8",
                          "PYTHONNOUSERSITE":"1"},
                     text=True,timeout=100,check=False)
    require(len(p.stdout.encode())<=MAX_AUDITOR_BYTES and not p.stderr.strip(),
            "UNBOUNDED_OR_FAILED_FINANCE_OBSERVER")
    report=reduced_observation(json.loads(p.stdout),p.returncode,enrollment)
    receipt_sha=write_receipt(report)
    print(json.dumps({"status":report["status"],"receiptSha256":receipt_sha,
                      "unitCount":report["unitCount"],
                      "driftDetected":report["driftDetected"],
                      "financialReleaseAuthorized":False},sort_keys=True))
    return 2 if report["driftDetected"] else 3

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode",choices=("plan","once"),default="plan")
    args=parser.parse_args(argv)
    if args.mode=="plan":
        print(json.dumps({"schema":SCHEMA,"status":"HOLD_UNENROLLED",
              "readOnly":True,"autoRemediation":False,
              "financialReleaseAuthorized":False,"installerIncluded":False},
              sort_keys=True))
        return 3
    try:return once()
    except (Stop,OSError,ValueError,TypeError,subprocess.SubprocessError) as e:
        reason=str(e) if isinstance(e,Stop) else "OBSERVER_OR_RECEIPT_UNAVAILABLE"
        print(json.dumps({"schema":SCHEMA,"status":"STOP",
              "reason":reason,"financialReleaseAuthorized":False},sort_keys=True))
        return 2

if __name__=="__main__":
    sys.exit(main())

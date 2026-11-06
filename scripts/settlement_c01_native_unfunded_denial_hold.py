#!/usr/bin/env python3
"""C01 live staged signer/reviewer DENIAL: read-only native executable proof.

Runs only the shipped root-owned executables with --check against known
ABSENT C01 protected profiles, under their existing nonroot Linux identities.
If configs become present, this controller refuses to launch anything.

No state, keys, HTTP, bank calls, DB, payments, service start, port change,
shell, config creation or owner permit. Exit 3/HOLD on precise native denial
with executable/identity/port guard; 2/STOP on any drift or unexpected success.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import stat
import subprocess
import sys

ROOT = Path("/usr/local/libexec/wolo-c01/f7b5a74928e041a6a90ac983d87649e0484677a4")
CONFIG = Path("/etc/wolo-financial-c01")
SCHEMA = "wolo.c01.actual-native-check-negative-admission.v1"
PROGRAMS = {
    "wolosatcheld": {
        "user": "wolo-satchel", "uid": 988, "sha": "bf07bee6cfe18988e9d3c3465bc3a3e66835d9cbc45fa3415462bba8727449e8",
        "size": 55921448, "file": "custody.json",
        "error": "satchel: configuration refused",
    },
    "woloreviewerd": {
        "user": "wolo-reviewer", "uid": 987, "sha": "deceac51afa73ee6e224447b004eb72b54e5a7d997d835ec1c82bf8277ad48e9",
        "size": 55866092, "file": "reviewer.json",
        "error": "reviewer: protected configuration refused",
    },
}
PORT_RE = re.compile(r":(?:8094|8095)(?:\s|$)")


class Stop(ValueError):
    pass


def require(ok, why):
    if not ok:
        raise Stop(why)


def command(argv, *, timeout=5):
    p=subprocess.run(argv, input=b"", capture_output=True, timeout=timeout,
                     check=False, env={"PATH":"/usr/sbin:/usr/bin:/bin", "HOME":"/nonexistent"})
    require(len(p.stdout) < 16384 and len(p.stderr) < 16384, "C01_NATIVE_OUTPUT_TOO_LARGE")
    return p


def read_port_state():
    p=command(["/usr/bin/ss", "-ltnH"])
    require(p.returncode==0, "C01_PORT_INSPECTION_FAILED")
    return not bool(PORT_RE.search(p.stdout.decode("utf-8", "strict")))


def verify_binary(path, expected):
    require(path.is_absolute() and not path.is_symlink()
            and path.resolve(strict=True)==path, "C01_PINNED_BINARY_PATH_DRIFT")
    s=path.stat()
    require(stat.S_ISREG(s.st_mode) and s.st_uid==0 and
            stat.S_IMODE(s.st_mode)==0o555 and s.st_size==expected["size"],
            "C01_PINNED_BINARY_OWNER_MODE_SIZE_DRIFT")
    digest=hashlib.sha256()
    with path.open("rb",buffering=0) as f:
        before=os.fstat(f.fileno())
        while True:
            part=f.read(1048576)
            if not part:
                break
            digest.update(part)
        after=os.fstat(f.fileno())
    require(all(getattr(before,k)==getattr(after,k) for k in (
        "st_dev","st_ino","st_size","st_uid","st_mode","st_mtime_ns","st_ctime_ns")),
        "C01_BINARY_CHANGED_DURING_VERIFY")
    require(digest.hexdigest()==expected["sha"],"C01_PINNED_EXECUTABLE_SHA256_DRIFT")


def denied(name, spec):
    p=CONFIG/spec["file"]
    require(not p.exists() and not p.is_symlink(), "C01_PROTECTED_CONFIG_NOW_PRESENT")
    role=pwd.getpwnam(spec["user"])
    require(role.pw_uid==spec["uid"] and role.pw_uid!=0,
            "C01_NATIVE_SERVICE_IDENTITY_DRIFT")
    path=ROOT/name
    verify_binary(path,spec)
    proc=command(["/usr/sbin/runuser","-u",spec["user"],"--",str(path),
                  "--check","--config",str(p)],timeout=8)
    require(proc.returncode==2 and proc.stdout==b"",
            "C01_NATIVE_CONFIG_CHECK_UNEXPECTEDLY_SUCCEEDED_OR_CHANGED")
    stderr=proc.stderr.decode("utf-8","replace")
    require(spec["error"] in stderr and stderr.count(spec["error"])==1,
            "C01_NATIVE_DENIAL_DIAGNOSTIC_CHANGED")
    require(not p.exists() and not p.is_symlink(),
            "C01_CONFIG_APPEARED_DURING_DENIAL")
    return {"program":name, "actual_unfunded_nonroot_check": True,
            "expected_fixed_config_refusal": True,"native_exit":2,
            "pinned_binary_sha256":spec["sha"],"sensitive_output_captured":False}


def classify(result, *, ports_before, ports_after):
    require(ports_before is True and ports_after is True,
            "C01_FINANCIAL_LISTENER_APPEARED")
    require(type(result) is list and len(result)==2 and
            {r["program"] for r in result}==set(PROGRAMS),
            "C01_NATIVE_COVERAGE_INCOMPLETE")
    for row in result:
        require(type(row) is dict and set(row)=={
            "program","actual_unfunded_nonroot_check","expected_fixed_config_refusal",
            "native_exit","pinned_binary_sha256","sensitive_output_captured"},
            "C01_NATIVE_ROW_INVALID")
        require(row["actual_unfunded_nonroot_check"] is True
                and row["expected_fixed_config_refusal"] is True
                and type(row["native_exit"]) is int and row["native_exit"]==2
                and row["pinned_binary_sha256"]==PROGRAMS[row["program"]]["sha"]
                and row["sensitive_output_captured"] is False,
                "C01_NATIVE_CUSTODY_DENIAL_NOT_PROVEN")
    return {"schema":SCHEMA,"status":"HOLD",
            "nonroot_real_binary_check_denied_before_config":True,
            "exact_source_binary_checks":len(result),
            "actual_checked_programs":sorted(PROGRAMS),
            "all_new_financial_listeners_absent":True,
            "custody_and_reviewer_profiles_not_present":True,
            "protected_source_and_independent_permits_unchecked":True,
            "financial_database_fenced":False,
            "independent_reviewer_admitted":False,
            "c01_physically_admitted":False,
            "financial_release_authorized":False,
            "production_mutated":False,
            "next_evidence":"independently reviewed and protected authority profiles plus real restored-state C07 admission and transaction-specific owner permit"}


def main(argv):
    if argv!=["--inspect"] or os.geteuid()!=0:
        print(json.dumps({"schema":SCHEMA,"status":"STOP",
                          "reason":"C01_ROOT_FIXED_READ_ONLY_INSPECTION_ONLY",
                          "financial_release_authorized":False}))
        return 2
    try:
        before=read_port_state()
        require(before,"C01_FINANCIAL_LISTENERS_ALREADY_PRESENT")
        observations=[denied(name,spec) for name,spec in PROGRAMS.items()]
        out=classify(observations,ports_before=before,ports_after=read_port_state())
    except (Stop,OSError,ValueError,UnicodeError,KeyError,
            subprocess.SubprocessError,subprocess.TimeoutExpired):
        print(json.dumps({"schema":SCHEMA,"status":"STOP",
                          "reason":"C01_NATIVE_NEGATIVE_ADMISSION_FAILED",
                          "financial_release_authorized":False},sort_keys=True))
        return 2
    print(json.dumps(out,sort_keys=True,separators=(",",":")))
    return 3


if __name__=="__main__":
    sys.exit(main(sys.argv[1:]))

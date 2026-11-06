#!/usr/bin/env python3
"""C01 root-local, read-only staged-binary/unit observer. NEVER custody admission.

No config contents, private paths, wallet/identity values, or environment are read.
No service start, network I/O, payment, file mutation or release permit is possible.
A valid observation always returns 3/HOLD. Drift returns 2/STOP.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import pwd
import grp
import re
import stat
import subprocess
import sys

SCHEMA = "wolo.c01.unfunded-staged-host-boundary-hold.v1"
ROOT = Path("/usr/local/libexec/wolo-c01/f7b5a74928e041a6a90ac983d87649e0484677a4")
CONFIG_ROOT = Path("/etc/wolo-financial-c01")
SPECS = {
    "wolo-satchel-c01.service": {
        "user": "wolo-satchel", "uid": 988, "gid": 983, "binary": "wolosatcheld",
        "bytes": 55921448,
        "sha256": "bf07bee6cfe18988e9d3c3465bc3a3e66835d9cbc45fa3415462bba8727449e8",
    },
    "wolo-reviewer-c01.service": {
        "user": "wolo-reviewer", "uid": 987, "gid": 982, "binary": "woloreviewerd",
        "bytes": 55866092,
        "sha256": "deceac51afa73ee6e224447b004eb72b54e5a7d997d835ec1c82bf8277ad48e9",
    },
}
CONFIGS = ("custody.json", "reviewer.json")
UNIT_KEYS = frozenset(("LoadState", "ActiveState", "MainPID", "User", "Group", "ExecStart"))


class Stop(ValueError):
    pass


def require(test: bool, code: str) -> None:
    if not test:
        raise Stop(code)


def command(*args: str) -> str:
    result = subprocess.run(args, capture_output=True, timeout=5, check=False)
    require(result.returncode == 0 and len(result.stdout) <= 32768, "HOST_OBSERVER_UNAVAILABLE")
    try:
        return result.stdout.decode("utf-8", "strict")
    except UnicodeError as exc:
        raise Stop("HOST_OUTPUT_ENCODING_INVALID") from exc


def unit_fields(text: str) -> dict:
    fields = {}
    require(len(text) <= 8192, "UNIT_REPORT_OVERSIZED")
    for line in text.splitlines():
        key, sep, value = line.partition("=")
        require(bool(sep) and key in UNIT_KEYS and key not in fields, "UNIT_REPORT_SHAPE_INVALID")
        fields[key] = value
    require(set(fields) == UNIT_KEYS, "UNIT_FIELDS_INCOMPLETE")
    return fields


def hash_root_binary(path: Path) -> dict:
    require(path.is_absolute() and path.resolve(strict=True) == path, "BINARY_SYMLINK_PATH")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        before = os.fstat(fd)
        require(stat.S_ISREG(before.st_mode), "BINARY_NOT_REGULAR")
        require(before.st_uid == 0 and stat.S_IMODE(before.st_mode) == 0o555,
                "BINARY_OWNER_OR_MODE_DRIFT")
        sha = hashlib.sha256()
        total = 0
        while True:
            block = os.read(fd, 1048576)
            if not block:
                break
            total += len(block)
            require(total <= 100000000, "BINARY_OVERSIZED")
            sha.update(block)
        after = os.fstat(fd)
        identity = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
        require(all(getattr(before, n) == getattr(after, n) for n in identity)
                and total == before.st_size, "BINARY_CHANGED_DURING_READ")
        return {"bytes": total, "sha256": sha.hexdigest(), "uid": before.st_uid,
                "mode": stat.S_IMODE(before.st_mode)}
    finally:
        os.close(fd)


def config_mode(name: str) -> str:
    p = CONFIG_ROOT / name
    try:
        s = p.lstat()
    except FileNotFoundError:
        return "ABSENT"
    require(stat.S_ISREG(s.st_mode) and s.st_uid == 0 and
            stat.S_IMODE(s.st_mode) == 0o600, "CONFIG_TYPE_OR_MODE_DRIFT")
    return "PRESENT_UNREAD"


def collect() -> dict:
    units = {}
    binaries = {}
    for name, spec in SPECS.items():
        units[name] = unit_fields(command(
            "systemctl", "show", name, "--no-pager",
            "-p", "LoadState", "-p", "ActiveState", "-p", "MainPID",
            "-p", "User", "-p", "Group", "-p", "ExecStart"))
        user = pwd.getpwnam(spec["user"])
        group = grp.getgrnam(spec["user"])
        require(user.pw_uid == spec["uid"] and user.pw_gid == spec["gid"]
                and group.gr_gid == spec["gid"],
                "STAGED_SERVICE_ACCOUNT_DRIFT")
        binaries[name] = hash_root_binary(ROOT / spec["binary"])
    ports = command("ss", "-ltnH")
    return {"units": units, "binaries": binaries,
            "financial_service_listener_present": bool(re.search(r":(?:8094|8095)(?:\s|$)", ports)),
            "configs": {name: config_mode(name) for name in CONFIGS}}


def classify(snapshot: dict) -> dict:
    require(type(snapshot) is dict and set(snapshot) ==
            {"units", "binaries", "financial_service_listener_present", "configs"},
            "SNAPSHOT_SHAPE_INVALID")
    require(type(snapshot["units"]) is dict and set(snapshot["units"]) == set(SPECS)
            and type(snapshot["binaries"]) is dict and set(snapshot["binaries"]) == set(SPECS),
            "STAGED_UNIT_COVERAGE_INVALID")
    for name, spec in SPECS.items():
        unit = snapshot["units"][name]
        binary = snapshot["binaries"][name]
        require(type(unit) is dict and set(unit) == UNIT_KEYS, "UNIT_FIELDS_INCOMPLETE")
        require(unit["LoadState"] == "loaded" and unit["ActiveState"] == "inactive"
                and unit["MainPID"] == "0", "STAGED_UNIT_NOT_INACTIVE")
        require(unit["User"] == spec["user"] and unit["Group"] == spec["user"],
                "STAGED_SERVICE_IDENTITY_DRIFT")
        match = re.search(r"\bpath=(/[^\s;}]+)", unit["ExecStart"])
        require(match is not None and match.group(1) == str(ROOT / spec["binary"]),
                "STAGED_EXECUTABLE_PATH_DRIFT")
        require(type(binary) is dict and binary ==
                {"bytes": spec["bytes"], "sha256": spec["sha256"], "uid": 0, "mode": 0o555},
                "STAGED_BINARY_BYTES_DRIFT")
    require(snapshot["financial_service_listener_present"] is False,
            "UNAUTHORIZED_FINANCIAL_LISTENER")
    require(type(snapshot["configs"]) is dict and set(snapshot["configs"]) == set(CONFIGS),
            "CUSTODY_CONFIG_COVERAGE_INVALID")
    require(all(state in ("ABSENT", "PRESENT_UNREAD")
                for state in snapshot["configs"].values()), "CUSTODY_CONFIG_STATE_INVALID")
    return {
        "schema": SCHEMA, "status": "HOLD",
        "staged_binaries_match_pinned_bytes": True,
        "staged_service_accounts_and_executable_path_match": True,
        "unit_full_argument_contract_accepted": False,
        "both_proposed_services_inactive": True,
        "new_financial_ports_8094_8095_absent": True,
        "configuration_presence_only": dict(snapshot["configs"]),
        "configuration_contents_reviewed": False,
        "custody_keys_enrolled_or_verified": False,
        "reviewer_independent_human_identity_verified": False,
        "financial_database_fenced": False,
        "c01_physically_admitted": False,
        "c08_governance_adopted": False,
        "funded_canary_authorized": False,
        "financial_release_authorized": False,
        "production_mutated": False,
        "next_evidence": "rehearsed C07 restore, enrolled root-protected roles and revoked keys, solo-owner witness, actual runtime native negative/positive test",
    }


def main(argv: list[str]) -> int:
    if argv != ["--inspect"] or os.geteuid() != 0:
        print(json.dumps({"schema": SCHEMA, "status": "STOP",
                          "reason": "ROOT_ONLY_FIXED_READ_ONLY_INSPECT",
                          "financial_release_authorized": False}))
        return 2
    try:
        report = classify(collect())
    except (Stop, OSError, KeyError, ValueError, subprocess.SubprocessError) as exc:
        reason = str(exc) if type(exc) is Stop else "HOST_OBSERVER_UNAVAILABLE"
        print(json.dumps({"schema": SCHEMA, "status": "STOP",
                          "reason": reason, "financial_release_authorized": False}))
        return 2
    print(json.dumps(report, sort_keys=True))
    return 3


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

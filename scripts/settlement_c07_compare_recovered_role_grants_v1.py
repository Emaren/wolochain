#!/usr/bin/env python3
"""Offline comparison of actual C07 role/owner/ACL digests; never financial acceptance.

Expected private input files: hd.owner.txt, de.owner.txt,
hd.effective.txt, de.effective.txt in each separate directory.
No connections, SQL writes, secrets or live service operations.
"""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys

SCOPES = {
    "hd": {"USER_REL_COUNT": "401", "USER_FUNCTION_COUNT": "42", "SCHEMA_COUNT": "15",
           "DB_OWNER": "aoe2hd_user"},
    "de": {"USER_REL_COUNT": "102", "USER_FUNCTION_COUNT": "0", "SCHEMA_COUNT": "1",
           "DB_OWNER": "aoe2de_user"},
}
ROLES = ("aoe2hd_user", "aoe2de_user", "aoe2war_auth_owner",
         "aoe2war_web_prod", "aoe2war_r25_web_ro")
TYPES = ("SCHEMA_EFFECTIVE", "REL_EFFECTIVE", "FUNCTION_EFFECTIVE")
HEX32 = re.compile(r"^[0-9a-f]{32}$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")

def fail(msg):
    raise ValueError("HOLD_C07_" + msg)

def parse_owner(payload, scope):
    lines = payload.decode("utf-8").splitlines()
    values = {}
    for line in lines:
        if "|" not in line:
            fail("OWNER_LINE_NOT_DELIMITED")
        k, v = line.split("|", 1)
        if not k or k in values:
            fail("OWNER_DUPLICATE_OR_EMPTY_KEY")
        values[k] = v
    if set(values) != {"ROLE_COUNT", "MEMBER_COUNT", "USER_REL_COUNT",
                       "USER_FUNCTION_COUNT", "SCHEMA_COUNT", "DB_OWNER",
                       "REL_OWNER_SHA", "FUNC_OWNER_SHA", "SCHEMA_OWNER_SHA",
                       "ROLE_FLAG_SHA", "MEMBER_SHA"}:
        fail("OWNER_FIELDS_CHANGED")
    if values["ROLE_COUNT"] != "24" or values["MEMBER_COUNT"] != "3":
        fail("GLOBAL_ROLE_MEMBERSHIP_SCOPE_DRIFT")
    for key, value in SCOPES[scope].items():
        if values[key] != value:
            fail("ORIGINAL_SCOPE_DRIFT_" + scope + "_" + key)
    for key in ("REL_OWNER_SHA", "SCHEMA_OWNER_SHA",
                "ROLE_FLAG_SHA", "MEMBER_SHA"):
        if not HEX32.fullmatch(values[key]):
            fail("INVALID_OWNER_HASH_" + key)
    if scope == "hd":
        if not HEX32.fullmatch(values["FUNC_OWNER_SHA"]):
            fail("HD_FUNC_OWNER_SHA_INVALID")
    elif values["FUNC_OWNER_SHA"] != "":
        fail("DE_FUNC_OWNER_SHOULD_BE_EMPTY")
    return values

def parse_permissions(payload, scope):
    lines = payload.decode("utf-8").splitlines()
    expected = ({f"{t}|{role}" for t in TYPES for role in ROLES}
                if scope == "hd" else
                {f"{t}|{role}" for t in TYPES[:-1] for role in ROLES})
    entries = {}
    for line in lines:
        if "|" not in line:
            fail("EFFECTIVE_LINE_INVALID")
        parts = line.split("|")
        if len(parts) != 3:
            fail("EFFECTIVE_FIELDS_INVALID")
        typ, role, digest = parts
        key = f"{typ}|{role}"
        if key in entries or key not in expected or not HEX32.fullmatch(digest):
            fail("UNEXPECTED_EFFECTIVE_ROLE_OR_HASH")
        entries[key] = digest
    if set(entries) != expected:
        fail("MISSING_EFFECTIVE_ROLE_COVERAGE")
    return entries

def load_private(path):
    if path.is_symlink() or not path.is_file():
        fail("SOURCE_NOT_REGULAR_FILE")
    s = path.stat()
    if s.st_mode & (stat.S_IRWXG | stat.S_IRWXO):
        fail("SOURCE_ACCESS_TOO_BROAD")
    if not 10 < s.st_size <= 16384:
        fail("SOURCE_SIZE_OUT_OF_RANGE")
    return path.read_bytes()

def compare(live_dir, restored_dir):
    verified = {}
    for scope in ("hd", "de"):
        verified[scope] = {}
        for kind in ("owner", "effective"):
            filename = f"{scope}.{kind}.txt"
            a = load_private(live_dir / filename)
            b = load_private(restored_dir / filename)
            if kind == "owner":
                parse_owner(a, scope)
                parse_owner(b, scope)
            else:
                parse_permissions(a, scope)
                parse_permissions(b, scope)
            if a != b:
                fail("LIVE_RESTORED_MISMATCH_" + scope.upper() + "_" + kind.upper())
            verified[scope][kind] = {"exact_equal": True,
                  "sha256": hashlib.sha256(a).hexdigest(),
                  "records": len(a.decode("utf-8").splitlines())}
    return verified

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--live-dir", type=Path, required=True)
    ap.add_argument("--restored-dir", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--c06-capture-sha256", default=None)
    args = ap.parse_args(argv)
    for directory in (args.live_dir, args.restored_dir):
        if directory.is_symlink() or not directory.is_dir():
            fail("INPUT_DIRECTORY_MISSING_OR_LINK")
        if directory.stat().st_mode & (stat.S_IRWXG | stat.S_IRWXO):
            fail("INPUT_DIRECTORY_MODE_TOO_BROAD")
    if args.live_dir.resolve() == args.restored_dir.resolve():
        fail("LIVE_AND_RESTORED_INPUT_IDENTICAL")
    if args.c06_capture_sha256 and not HEX64.fullmatch(args.c06_capture_sha256):
        fail("INVALID_C06_REFERENCE")
    result = compare(args.live_dir, args.restored_dir)
    if args.out.exists() or args.out.is_symlink():
        fail("NO_OVERWRITE_RECEIPT")
    if args.out.parent.is_symlink() or not args.out.parent.is_dir():
        fail("OUTPUT_PARENT_UNTRUSTED")
    if args.out.parent.stat().st_mode & (stat.S_IRWXG | stat.S_IRWXO):
        fail("OUTPUT_PARENT_PERMISSIONS_TOO_BROAD")
    receipt = {
        "schema": "wolo.c07.recovered-role-owner-acl-offline-compare.v1",
        "observed_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "verified": result,
        "c06_capture_sha256_reference_unverified": args.c06_capture_sha256,
        "cross_db_transactional_consistency_proven": False,
        "password_verifiers_restored": False,
        "consensus_and_journal_same_checkpoint_proven": False,
        "complete_restore_test_proven": False,
        "c06_formally_closed": False, "c07_formally_closed": False,
        "financial_release_authorized": False,
        "outcome": "PASS_ROLE_AND_EFFECTIVE_ACL_PARITY_ONLY_HOLD_C07",
    }
    raw = (json.dumps(receipt, sort_keys=True, indent=2) + "\n").encode()
    fd = os.open(args.out, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(raw)
        f.flush()
        os.fsync(f.fileno())
    print("PASS_C07_HD_DE_OWNER_AND_EFFECTIVE_ACL_PARITY")
    print("C07_OFFLINE_RECEIPT_SHA256=" + hashlib.sha256(raw).hexdigest())
    print("HOLD_C07_SAME_C06_CAPTURE_RESTORE_AND_FULL_FINANCIAL_REPLAY_NOT_YET_PROVEN")
    return 0

if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, OSError, UnicodeError) as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(3)

#!/usr/bin/env python3
"""HD-only ↔ Wolo 8094 static source-wire gate. Always NONAUTHORIZING.

The protected website is already deployed. This bounded source inspection checks
the actual held HD Satchel ↔ Wolo signer contract without enabling a signer or
touching the chain. Matching strings are NOT custody proof, bank authentication,
source integrity signatures, a producer fence or funded-release authority.
The operator must independently qualify both exact Git heads, the real 8094
service, and the bank/finality/solvency evidence before any canary.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys

SCHEMA = "aoe2war.hd-wolo.funded-wire-review.v1"
MAX_FILE = 64 * 1024
HEX40 = re.compile(r"[a-f0-9]{40}\Z")
FILES = {
    "hd_client": ("hd", "lib/warSatchelDedicatedSignerClient.ts"),
    "hd_bridge": ("hd", "lib/warSatchelFinancialBridgeHold.ts"),
    "hd_admission": ("hd", "lib/warSatchelFundedAdmission.ts"),
    "wolo_signer": ("wolo", "cmd/wolosatcheld/main.go"),
    "wolo_http": ("wolo", "internal/satchelservice/http.go"),
}
# These are guards against unintended *wire/feature shape drift*, not proof of
# semantic equivalence. The original cross-language behavioral tests still run.
SURFACES = {
    "hd_client": {
        "fixed_loopback_8094": 'http://127.0.0.1:8094',
        "reserved_signed_one_shot": '"/satchel/v2/one-shot"',
        "explicit_custody_capability": 'health.custody_capability !== "AVAILABLE"',
        "require_durable_one_shot": 'health.durable_one_shot !== true',
        "require_owner_reservation": 'health.owner_bound_wager_reservation_required !== true',
        "bounded_auto_bet": 'BET_MAX_STAKE_UWOLO',
        "independent_wager_review": "verifyIndependentWagerReservation",
        "one_shot_lease": "withHdFinancialLease",
    },
    "hd_bridge": {
        "money_fail_closed": "SATCHEL_FINANCIAL_BRIDGE_READY = false as const",
        "money_held_exception": "SATCHEL_FINANCIAL_BRIDGE_UNVERIFIED_HOLD",
    },
    "hd_admission": {
        "proposal_not_money": "PROPOSAL_ONLY_NOT_WAGER_AUTHORIZATION",
        "one_height_vault": "headHeight",
        "all_owner_liabilities": "aggregateLiabilityUwolo",
        "signed_consent": "signedBudgetVerified",
    },
    "wolo_signer": {
        "isolated_custody_service": 'NewPrivateHTTPServer("127.0.0.1:8094"',
        "protected_keyring": "NewKeyringBackend",
        "runtime_custody_authority": "NewCustodyAuthority",
        "chain_verifier": "trusted.CheckTrust",
        "pre_broadcast_verifier": "AuthorizeBroadcast",
        "source_bound_executable": "runningDigest()",
    },
    "wolo_http": {
        "signed_one_shot": '"/satchel/v2/one-shot"',
        "v2_receipt": "reservedACK",
        "protocol_v2": '"execution_protocol": 2',
        "owner_reservation": '"owner_bound_wager_reservation_required": true',
        "refuse_by_default": '"custody_capability": "UNAVAILABLE"',
        "available_requires_grant": 'if i.Accepting && capability.grant != nil',
        "long_lived_replay_prevention": '"replay_after_restart_forbidden": true',
    },
}
class ReviewHold(ValueError):
    pass

def check(cond: bool, why: str) -> None:
    if not cond:
        raise ReviewHold(why)

def read_bounded(root: Path, relative: str) -> bytes:
    check(root.is_absolute() and root.is_dir() and not root.is_symlink(),
          "SOURCE_ROOT_INVALID")
    current = root
    for seg in Path(relative).parts:
        check(seg not in ("..", ".", ""), "RELATIVE_PATH_INVALID")
        current = current / seg
        info = current.lstat()
        check(not stat.S_ISLNK(info.st_mode), "SOURCE_PATH_SYMLINK")
    fd = os.open(current, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        before = os.fstat(fd)
        check(stat.S_ISREG(before.st_mode) and before.st_nlink == 1
              and 0 < before.st_size <= MAX_FILE, "SOURCE_FILE_INVALID")
        data = os.read(fd, MAX_FILE + 1)
        after = os.fstat(fd)
        check(len(data) == before.st_size and all(
            getattr(before, field) == getattr(after, field)
            for field in ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
        ), "SOURCE_FILE_CHANGED")
        return data
    finally:
        os.close(fd)

def source_head(root: Path) -> tuple[str, bool]:
    try:
        head = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"],
                              capture_output=True, text=True, timeout=4, check=True).stdout.strip()
        dirt = subprocess.run(["git", "-C", str(root), "status", "--porcelain",
                               "--untracked-files=no"], capture_output=True,
                              text=True, timeout=5, check=True).stdout.strip()
    except (subprocess.CalledProcessError, OSError, subprocess.TimeoutExpired) as exc:
        raise ReviewHold("SOURCE_GIT_IDENTITY_UNAVAILABLE") from exc
    check(bool(HEX40.fullmatch(head)), "SOURCE_COMMIT_INVALID")
    return head, bool(dirt)

def inspect(wolo_head: str, hd_head: str, contents: dict[str, bytes]) -> dict:
    check(bool(HEX40.fullmatch(wolo_head)) and bool(HEX40.fullmatch(hd_head)),
          "EXACT_SOURCE_SHA_REQUIRED")
    check(set(contents) == set(FILES), "MISSING_SOURCE_SURFACE")
    failures, checks, digests = [], {}, {}
    for name, raw in contents.items():
        check(type(raw) is bytes and 0 < len(raw) <= MAX_FILE,
              "SOURCE_BYTES_UNAVAILABLE")
        try:
            text = raw.decode("utf-8")
        except UnicodeError as exc:
            raise ReviewHold("SOURCE_BYTES_NOT_UTF8") from exc
        found = {key: needle in text for key, needle in SURFACES[name].items()}
        checks[name] = found
        failures.extend(name + "." + key for key, ok in found.items() if not ok)
        digests[name] = hashlib.sha256(raw).hexdigest()
    # All source checks passing is STILL a HOLD because source text cannot
    # attest runtime vault control or the essential offhost chain trust proof.
    return {
        "schema": SCHEMA, "status": "HOLD",
        "wolo_source_sha": wolo_head, "hd_source_sha": hd_head,
        "surface_checks": checks, "source_file_sha256": digests,
        "static_wire_surface_matches": not failures,
        "source_shape_gaps": sorted(failures),
        "dedicated_8094_runtime_custody_proven": False,
        "historical_consensus_trust_authenticated": False,
        "same_height_solvency_certified": False,
        "hd_funded_bridge_enabled": False,
        "legacy_money_mutated": False,
        "financial_release_authorized": False,
        "next": ("A complete source-wire match qualifies only the protocol shape. "
                 "Read actual signed 8094 custody, bank and full HD liability "
                 "receipts, rebase held HD source on certified Renaissance, "
                 "and qualify a separate owner-signed financial cutover."),
    }

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wolo-root", required=True, type=Path)
    parser.add_argument("--hd-root", required=True, type=Path)
    parser.add_argument("--expect-wolo-sha", required=True)
    parser.add_argument("--expect-hd-sha", required=True)
    args = parser.parse_args(argv)
    try:
        roots = {"wolo": args.wolo_root.resolve(), "hd": args.hd_root.resolve()}
        heads = {k: source_head(v) for k,v in roots.items()}
        check(heads["wolo"][0] == args.expect_wolo_sha and
              heads["hd"][0] == args.expect_hd_sha and
              not heads["wolo"][1] and not heads["hd"][1],
              "SOURCE_SHA_OR_TRACKED_DIRTY_MISMATCH")
        contents = {name: read_bounded(roots[which], path)
                    for name,(which,path) in FILES.items()}
        output = inspect(heads["wolo"][0], heads["hd"][0], contents)
    except (ReviewHold, OSError, ValueError) as exc:
        print(json.dumps({"status":"STOP", "reason":str(exc),
                          "financial_release_authorized":False}, sort_keys=True))
        return 2
    print(json.dumps(output, indent=2, sort_keys=True))
    return 3

if __name__ == "__main__":
    sys.exit(main())

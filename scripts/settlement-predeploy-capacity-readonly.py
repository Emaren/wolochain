#!/usr/bin/env python3
"""Fail-closed, nonmutating VPS storage-headroom gate for Wolo settlement release.

Checks BOTH the operating-system root mount (Next.js build, service, logs) and
the separately mounted Wolo data volume (snapshots, state, immutable artifacts).
No action is authorized by passing a minimum free-space floor.

Never deletes, prunes, snapshots, changes a mount, or touches wallet/state data.
This is NOT a backup-size estimate, financial drain certificate, or release approval.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys

VOLUME = Path("/mnt/HC_Volume_105319120")
ROOT = Path("/")
GIB = 1024 ** 3
MIN_ROOT_FREE_GIB = 8
MIN_WOLO_FREE_GIB = 20


def free_bytes(path: Path) -> int:
    result = os.statvfs(path)
    # f_bavail is available even to unprivileged site build processes.
    # Root-reserved filesystem blocks must not be relied on for deployments.
    value = result.f_bavail * result.f_frsize
    if value < 0:
        raise ValueError("invalid available capacity")
    return value


def inspect() -> dict:
    if VOLUME.is_symlink() or not VOLUME.is_dir():
        raise ValueError("dedicated Wolo volume is missing or symlinked")
    if not os.path.ismount(VOLUME):
        raise ValueError("dedicated Wolo volume is NOT mounted; possible root fallback")
    if ROOT.stat().st_dev == VOLUME.stat().st_dev:
        raise ValueError("Wolo state and OS root are on same device")
    root_free = free_bytes(ROOT)
    wolo_free = free_bytes(VOLUME)
    root_ok = root_free >= MIN_ROOT_FREE_GIB * GIB
    wolo_ok = wolo_free >= MIN_WOLO_FREE_GIB * GIB
    return {
        "mode": "READ_ONLY_TWO_FILESYSTEM_DEPLOYMENT_HEADROOM",
        "observedAtUtc": datetime.now(timezone.utc).isoformat(),
        "root": {
            "freeGiB": round(root_free / GIB, 2),
            "policyMinimumGiB": MIN_ROOT_FREE_GIB,
            "minimumHeadroomPresent": root_ok,
        },
        "woloStateVolume": {
            "mountPresentAndSeparateFromRoot": True,
            "freeGiB": round(wolo_free / GIB, 2),
            "policyMinimumGiB": MIN_WOLO_FREE_GIB,
            "minimumHeadroomPresent": wolo_ok,
        },
        "status": (
            "CAPACITY_POLICY_FLOOR_PASS_NOT_RELEASE_APPROVAL"
            if root_ok and wolo_ok
            else "BLOCKED_INSUFFICIENT_PREDEPLOY_HEADROOM"
        ),
        "limits": [
            "Policy free-space floors are conservative screening values, not a measured backup or build footprint",
            "State snapshot must have its own measured, protected capacity reservation after ingress is fenced",
            "Actual database migration, Next.js build and rollback must be separately rehearsed",
            "Never prune chain data, settlement receipts, or financial backups to satisfy this check",
        ],
        "filesystemMutations": False,
        "financialDrainCertified": False,
        "rollbackCertified": False,
        "productionAuthorized": False,
    }


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if args not in ([], ["--inspect"]):
        print("BLOCKED: only --inspect is supported", file=sys.stderr)
        return 2
    try:
        result = inspect()
    except (OSError, ValueError):
        print("BLOCKED: cannot independently verify both mounted filesystems", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "CAPACITY_POLICY_FLOOR_PASS_NOT_RELEASE_APPROVAL" else 3


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""C06 physical backup-capacity census: read-only and never a capture permit.

The current signed financial controller writes *both* HD/DE custom dumps and
dual-settlement snapshots to one HEL1 volume. A separate 40-GiB loop restore
mount is NOT backup capacity. This standalone census never runs a backup,
touches permissions, starts a service, alters a database or signs anything.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import stat
import subprocess
import sys

SCHEMA = "wolo.c06.backup-capacity-census-held.v1"
VOLUME = Path("/mnt/HC_Volume_105319120")
PARENT = VOLUME / "wolochain-mainnet"
BACKUPS = PARENT / "financial-maintenance-backups"
SNAPSHOTS = PARENT / "settlement-backups"
RESERVE = 1 << 30
EXPECTED_DB = {"aoe2hd_db", "aoe2de_db"}
QUERY = (
    "BEGIN TRANSACTION READ ONLY; "
    "SELECT datname, pg_database_size(oid) "
    "FROM pg_database WHERE datname IN ('aoe2hd_db','aoe2de_db') "
    "ORDER BY datname; ROLLBACK;"
)


class Hold(ValueError):
    pass


def require(condition, reason):
    if not condition:
        raise Hold(reason)


def safe_directory(path: Path, *, private=False):
    try:
        st = path.lstat()
    except OSError:
        raise Hold("REQUIRED_DIRECTORY_UNAVAILABLE") from None
    require(stat.S_ISDIR(st.st_mode) and not stat.S_ISLNK(st.st_mode),
            "DIRECTORY_NOT_REAL")
    require(st.st_uid == 0 and st.st_gid == 0, "DIRECTORY_NOT_ROOT_OWNED")
    require(stat.S_IMODE(st.st_mode) & 0o022 == 0, "DIRECTORY_GROUP_OTHER_WRITABLE")
    if private:
        require(stat.S_IMODE(st.st_mode) == 0o700,
                "STAGING_DIRECTORY_NOT_0700")
    return st


def parse_db_sizes(out: str) -> dict:
    require(type(out) is str and 0 < len(out) < 4096, "PG_SIZE_OUTPUT_UNAVAILABLE")
    rows = {}
    for line in out.splitlines():
        pieces = line.split("|")
        require(len(pieces) == 2 and pieces[0] in EXPECTED_DB and
                pieces[0] not in rows and pieces[1].isdigit(),
                "PG_SIZE_RESULT_INVALID")
        bytes_used = int(pieces[1])
        require(0 < bytes_used < (1 << 50), "PG_SIZE_OUT_OF_BOUNDS")
        rows[pieces[0]] = bytes_used
    require(set(rows) == EXPECTED_DB, "HD_DE_DATABASE_INCOMPLETE")
    return rows


def report(*, volume_free: int, disk_sizes: dict, stage_empty: bool,
           snapshot_root_safe: bool, same_volume: bool,
           legacy_writers_active: bool) -> dict:
    require(type(volume_free) is int and volume_free >= 0, "CAPACITY_INVALID")
    require(type(disk_sizes) is dict and set(disk_sizes) == EXPECTED_DB and
            all(type(v) is int and 0 < v < (1 << 50)
                for v in disk_sizes.values()), "DATABASE_SIZE_INVALID")
    require(type(stage_empty) is bool and type(snapshot_root_safe) is bool and
            type(same_volume) is bool and type(legacy_writers_active) is bool,
            "OBSERVATION_FLAGS_INVALID")
    # The backup permit must independently authorize a max_total_bytes. This
    # number is only the greatest ceiling consistent with the existing 1-GiB
    # controller space guard; it is NOT an estimated backup size.
    upper_bound = max(0, volume_free - RESERVE)
    return {
        "schema": SCHEMA,
        "status": "HOLD",
        "observed_utc": datetime.now(timezone.utc).isoformat(),
        "volume_free_bytes": volume_free,
        "controller_required_additional_free_bytes": RESERVE,
        "upper_bound_for_separately_authorized_max_total_bytes": upper_bound,
        "postgres_database_logical_sizes_bytes": disk_sizes,
        "postgres_database_sizes_sum_is_not_dump_size": True,
        "staging_empty_root_0700": stage_empty,
        "snapshot_root_safe": snapshot_root_safe,
        "capture_paths_share_one_backing_volume": same_volume,
        "restore_loop_free_excluded_from_capture_capacity": True,
        "legacy_producer_services_active": legacy_writers_active,
        "global_financial_writers_fenced": False,
        "offhost_ciphertext_receipt_verified": False,
        "backup_capture_executed": False,
        "backup_size_guaranteed_to_fit": False,
        "backup_or_restore_authorized": False,
        "financial_release_authorized": False,
        "reason": "GLOBAL_WRITER_FENCE_AND_OFFHOST_CUSTODY_NOT_VERIFIED",
    }


def inspect():
    require(os.geteuid() == 0, "ROOT_REQUIRED")
    require(os.path.ismount(VOLUME), "EXPECTED_VOLUME_NOT_MOUNTED")
    root_st = safe_directory(VOLUME)
    safe_directory(PARENT)
    safe_directory(BACKUPS, private=True)
    snap_st = safe_directory(SNAPSHOTS)
    require(root_st.st_dev == PARENT.stat().st_dev ==
            BACKUPS.stat().st_dev == snap_st.st_dev,
            "CAPTURE_PATHS_CROSS_FILESYSTEM")
    require(not any(BACKUPS.iterdir()), "STAGING_DIRECTORY_NOT_EMPTY")
    fs = os.statvfs(BACKUPS)
    require(fs.f_bavail >= 0 and fs.f_frsize > 0, "VOLUME_STATVFS_INVALID")
    capacity = fs.f_bavail * fs.f_frsize
    require(0 < capacity < (1 << 55), "VOLUME_FREE_SPACE_INVALID")
    cmd = ["runuser", "-u", "postgres", "--", "psql", "-X", "-qAt",
           "-F", "|", "-d", "postgres", "-v", "ON_ERROR_STOP=1",
           "-c", QUERY]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=12,
                          check=False)
    require(proc.returncode == 0, "POSTGRES_READ_ONLY_SIZE_QUERY_FAILED")
    disk_sizes = parse_db_sizes(proc.stdout)
    active = []
    for name in ("wolochain-mainnet-settlement.service",
                 "wolochain-founder-rewards-settlement.service"):
        check = subprocess.run(["systemctl", "show", "--value", "-p",
                                "ActiveState", name],
                               capture_output=True, text=True, timeout=5)
        require(check.returncode == 0 and
                check.stdout.strip() in {"active", "inactive", "failed"},
                "LEGACY_SERVICE_STATUS_UNAVAILABLE")
        active.append(check.stdout.strip() == "active")
    return report(volume_free=capacity, disk_sizes=disk_sizes,
                  stage_empty=True, snapshot_root_safe=True,
                  same_volume=True, legacy_writers_active=any(active))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inspect", action="store_true", required=True)
    parser.parse_args(argv)
    try:
        result = inspect()
    except (Hold, OSError, subprocess.SubprocessError, ValueError) as e:
        reason = str(e) if isinstance(e, Hold) else "SAFE_READ_ONLY_INSPECTION_UNAVAILABLE"
        print(json.dumps({"schema": SCHEMA, "status": "STOP",
                          "reason": reason, "financial_release_authorized": False},
                         sort_keys=True))
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 3


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Bounded, source-hashed archival settlement journal restore to isolated storage.

NO database, WAL, keys, config, executable, network, wallet, signer, or production
service is restored. Never authorizes financial launch. Production CLI accepts
only a root-owned archived two-settlement checkpoint and dedicated mounted FS.
Source archive from October is NOT a current, quiesced financial backup.
"""
from __future__ import annotations

from datetime import datetime, timezone
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys

ARCHIVE_BASE = Path("/mnt/HC_Volume_105319120/wolochain-mainnet/settlement-backups")
RECOVERY_BASE = Path("/var/lib/wolo-financial-restore/bounded")
ARCHIVE_NAME = re.compile(r"20[0-9]{6}T[0-9]{6}Z-two-settlement-node-untouched\Z")
HEXDIGEST = re.compile(r"[0-9a-f]{64}\Z")
MAX_MANIFEST_BYTES = 512 * 1024
MAX_FILE_BYTES = 256 * 1024 * 1024
MAX_ARCHIVE_BYTES = 256 * 1024 * 1024
MAX_ENTRIES = 5000
CHUNK = 1024 * 1024


class Hold(ValueError):
    pass


def directory(path: Path) -> None:
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or path.is_symlink():
        raise Hold("UNSAFE_DIRECTORY")


def file_digest(path: Path) -> tuple[str, int]:
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or path.is_symlink() or info.st_size > MAX_FILE_BYTES:
        raise Hold("UNSAFE_FILE")
    handle = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        before = os.fstat(handle)
        h = hashlib.sha256()
        length = 0
        while True:
            chunk = os.read(handle, CHUNK)
            if not chunk:
                break
            length += len(chunk)
            if length > MAX_FILE_BYTES:
                raise Hold("FILE_LIMIT")
            h.update(chunk)
        after = os.fstat(handle)
        if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
            after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns
        ) or length != before.st_size:
            raise Hold("FILE_CHANGED_DURING_READ")
        return h.hexdigest(), length
    finally:
        os.close(handle)


def manifest(archive: Path, section: str) -> dict[Path, str]:
    if section not in ("primary", "founder", "config"):
        raise Hold("INVALID_MANIFEST_SECTION")
    p = archive / "proof" / (section + "-files.sha256")
    directory(p.parent)
    info = p.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_MANIFEST_BYTES:
        raise Hold("MANIFEST_UNSAFE")
    raw = p.read_bytes()
    if len(raw) != info.st_size or b"\r" in raw or not raw.endswith(b"\n"):
        raise Hold("MANIFEST_UNSAFE")
    try:
        lines = raw.decode("ascii").splitlines()
    except UnicodeDecodeError as err:
        raise Hold("MANIFEST_UNSAFE") from err
    if not 0 < len(lines) <= MAX_ENTRIES:
        raise Hold("MANIFEST_COUNT")
    result: dict[Path, str] = {}
    base = archive if section == "config" else archive / "state" / section
    directory(base)
    for line in lines:
        parts = line.split("  ", 1)
        if len(parts) != 2 or not HEXDIGEST.fullmatch(parts[0]):
            raise Hold("MANIFEST_DIGEST")
        rawname = parts[1]
        if not rawname or len(rawname) > 320 or "\\" in rawname or "//" in rawname:
            raise Hold("MANIFEST_PATH")
        segments = rawname.split("/")
        if segments[0] == ".":
            segments.pop(0)
        if not segments or any(x in ("", ".", "..") for x in segments):
            raise Hold("MANIFEST_TRAVERSAL")
        if section != "config" and segments[0] not in ("requests", "runs"):
            raise Hold("UNEXPECTED_JOURNAL_PATH")
        if section == "config" and segments[0] not in ("config", "units"):
            raise Hold("UNEXPECTED_CONFIG_PATH")
        target = base.joinpath(*segments)
        if target in result:
            raise Hold("DUPLICATE_MANIFEST_IDENTITY")
        # Never follow a symlink even in intermediate directories.
        for parent in list(target.parents):
            if parent == base or parent == archive:
                break
            if not parent.is_relative_to(base if section != "config" else archive):
                raise Hold("ESCAPED_ARCHIVE")
            directory(parent)
        result[target] = parts[0]
    return result


def inventory(archive: Path) -> tuple[dict[Path, str], dict[str, int]]:
    directory(archive)
    directory(archive / "state")
    manifests: dict[str, dict[Path, str]] = {}
    total = 0
    for section in ("primary", "founder", "config"):
        manifest_rows = manifest(archive, section)
        manifests[section] = manifest_rows
        for path, expected in manifest_rows.items():
            actual, size = file_digest(path)
            if actual != expected:
                raise Hold("ARCHIVE_MANIFEST_MISMATCH")
            total += size
            if total > MAX_ARCHIVE_BYTES:
                raise Hold("ARCHIVE_TOO_LARGE")
    journal = {**manifests["primary"], **manifests["founder"]}
    for section in ("primary", "founder"):
        base = archive / "state" / section
        seen: set[Path] = set()
        for item in base.rglob("*"):
            if item.is_symlink():
                raise Hold("ARCHIVE_SYMLINK")
            if item.is_dir():
                directory(item)
            elif item.is_file():
                seen.add(item)
            else:
                raise Hold("ARCHIVE_SPECIAL_FILE")
        if seen != set(manifests[section]):
            raise Hold("ARCHIVE_UNMANIFESTED_FILES")
    return journal, {"primary": len(manifests["primary"]),
                     "founder": len(manifests["founder"]),
                     "config_hash_verified_not_restored": len(manifests["config"])}


def copy_journal(source: Path, target: Path, expected: str) -> None:
    # Source must have passed the original manifest before any writes begin.
    source_fd = os.open(source, os.O_RDONLY | os.O_NOFOLLOW)
    dest_fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        h = hashlib.sha256()
        total = 0
        while True:
            chunk = os.read(source_fd, CHUNK)
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_FILE_BYTES:
                raise Hold("COPY_LIMIT")
            h.update(chunk)
            while chunk:
                written = os.write(dest_fd, chunk)
                if written <= 0:
                    raise Hold("COPY_FAILED")
                chunk = chunk[written:]
        if h.hexdigest() != expected:
            raise Hold("SOURCE_CHANGED_DURING_RESTORE")
        os.fsync(dest_fd)
    finally:
        os.close(dest_fd)
        os.close(source_fd)
    if file_digest(target)[0] != expected:
        raise Hold("DESTINATION_RESTORE_CHECKSUM_MISMATCH")


def sync_dir(path: Path) -> None:
    handle = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(handle)
    finally:
        os.close(handle)


def restore(archive: Path, recovery: Path, *, production: bool) -> dict:
    if production:
        if os.name != "posix" or not sys.platform.startswith("linux") or os.geteuid() != 0:
            raise Hold("ROOT_LINUX_ONLY")
        if archive.parent != ARCHIVE_BASE or not ARCHIVE_NAME.fullmatch(archive.name):
            raise Hold("UNAPPROVED_ARCHIVE_ROOT")
        if recovery != RECOVERY_BASE or not os.path.ismount(recovery):
            raise Hold("UNAPPROVED_RESTORE_MOUNT")
    directory(archive.parent)
    directory(recovery)
    if production and archive.stat().st_dev == recovery.stat().st_dev:
        raise Hold("RESTORE_NOT_ISOLATED_FILESYSTEM")
    if production and (archive.stat().st_uid != 0 or recovery.stat().st_uid != 0):
        raise Hold("ROOT_OWNERSHIP_REQUIRED")
    journal, counts = inventory(archive)
    final = recovery / ("archived-financial-journal-only-" + archive.name)
    stage = recovery / ("." + final.name + ".partial")
    if final.exists() or final.is_symlink() or stage.exists() or stage.is_symlink():
        raise Hold("RESTORE_TARGET_ALREADY_PRESENT")
    stage.mkdir(mode=0o700)
    for lane in ("primary", "founder"):
        (stage / lane).mkdir(mode=0o700)
    for source, digest in journal.items():
        lane = source.relative_to(archive / "state").parts[0]
        target = stage / source.relative_to(archive / "state")
        target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        copy_journal(source, target, digest)
    for directory_to_sync in sorted((p for p in stage.rglob("*") if p.is_dir()),
                                    key=lambda p: len(p.parts), reverse=True):
        sync_dir(directory_to_sync)
    sync_dir(stage)
    os.rename(stage, final)
    sync_dir(recovery)
    counts["total_archived_journal_files_restored"] = len(journal)
    receipt = {
        "schema": "wolo.c07.historical-journal-restore-nonfinancial.v1",
        "utc": datetime.now(timezone.utc).isoformat(),
        "source_archive_name": archive.name,
        "source_manifest_sha256": {
            section: file_digest(archive / "proof" / (section+"-files.sha256"))[0]
            for section in ("primary", "founder", "config")
        },
        "file_counts": counts,
        "journal_restore_integrity_verified": True,
        "encrypted_offhost_backup_verified": False,
        "snapshot_matches_current_production": False,
        "live_postgresql_wal_restored": False,
        "current_financial_journals_restored": False,
        "config_secrets_or_custody_keys_copied": False,
        "signer_or_mainnet_service_started": False,
        "financial_release_authorized": False,
        "isolated_recovery_storage_written": True,
        "live_financial_runtime_mutated": False,
        "c06_closed": False, "c07_closed": False,
    }
    report = final / "RESTORE-HELD-RECEIPT.json"
    data = (json.dumps(receipt, sort_keys=True, separators=(",", ":"))+"\n").encode()
    with os.fdopen(os.open(report, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600),
                   "wb") as out:
        out.write(data)
        out.flush()
        os.fsync(out.fileno())
    sync_dir(final)
    return {"status": "HOLD", "receipt_sha256": hashlib.sha256(data).hexdigest(),
            "archive": archive.name, "counts": counts, "c07_closed": False,
            "financial_release_authorized": False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", required=True)
    parser.add_argument("--restore-mount", default=str(RECOVERY_BASE))
    args = parser.parse_args()
    try:
        result = restore(Path(args.archive), Path(args.restore_mount), production=True)
        print(json.dumps(result, sort_keys=True))
        return 3
    except (Hold, OSError, ValueError):
        print(json.dumps({"status": "STOP", "reason": "ARCHIVED_JOURNAL_RESTORE_REFUSED",
                          "financial_release_authorized": False, "c07_closed": False},
                         sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

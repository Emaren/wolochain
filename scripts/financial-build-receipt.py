#!/usr/bin/env python3
"""Bind a nonfunded CI build to its Git source. Never authorize or deploy it.

Run after the existing CI checks. This receipt records bytes and workflow
references; it does not authenticate test results, previous production state,
an owner signature, an inverse, or a financial release.
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


class Hold(ValueError):
    pass


def git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True,
        check=False, timeout=15,
    )
    if result.returncode:
        raise Hold("GIT_READ_FAILED")
    return result.stdout.strip()


def local_path(root: Path, value: str) -> Path:
    p = Path(value)
    if p.is_absolute() or not p.parts or any(x in {"..", "."} for x in p.parts):
        raise Hold("UNSAFE_ARTIFACT_PATH")
    current = root
    for part in p.parts:
        current = current / part
        if current.is_symlink():
            raise Hold("SYMLINK_ARTIFACT_PATH")
    return current


def candidate(root: Path, expected: str, artifact: str) -> dict:
    if not re.fullmatch(r"[0-9a-f]{40}", expected):
        raise Hold("FULL_SOURCE_SHA_REQUIRED")
    if git(root, "rev-parse", "HEAD") != expected:
        raise Hold("SOURCE_SHA_MISMATCH")
    status = git(root, "status", "--porcelain=v1", "--untracked-files=normal")
    # The preserved hidden worktree directory is outside Go package discovery.
    if any(line != "?? .worktrees/" for line in status.splitlines()):
        raise Hold("SOURCE_NOT_CLEAN")
    p = local_path(root, artifact)
    fd = os.open(p, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, "rb") as f:
        before = os.fstat(f.fileno())
        if not stat.S_ISREG(before.st_mode):
            raise Hold("ARTIFACT_NOT_REGULAR")
        header = f.read(64)
        if (len(header) < 64 or header[:6] != b"\x7fELF\x02\x01"
                or int.from_bytes(header[18:20], "little") != 62):
            raise Hold("LINUX_AMD64_ELF_REQUIRED")
        digest = hashlib.sha256(header)
        for block in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(block)
        after = os.fstat(f.fileno())
    fields = ("st_ino", "st_dev", "st_size", "st_mtime_ns", "st_ctime_ns")
    if any(getattr(before, x) != getattr(after, x) for x in fields):
        raise Hold("ARTIFACT_CHANGED_DURING_READ")
    if git(root, "rev-parse", "HEAD") != expected:
        raise Hold("SOURCE_CHANGED_DURING_READ")
    run_id = os.environ.get("GITHUB_RUN_ID", "")
    repository = os.environ.get("GITHUB_REPOSITORY", "")
    run_url = None
    if run_id.isdigit() and re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        run_url = f"https://github.com/{repository}/actions/runs/{run_id}"
    return {
        "schema": "aoe2war.financial.quarantined-build.v1",
        "observed_utc": datetime.now(timezone.utc).isoformat(),
        "source_sha": expected,
        "source_tree_sha": git(root, "rev-parse", "HEAD^{tree}"),
        "artifact": {"path": artifact, "sha256": digest.hexdigest(), "bytes": after.st_size},
        "workflow_run_reference": run_url,
        "test_results_authenticated_by_this_tool": False,
        "qualification": "BUILD_IDENTITY_ONLY",
        "state": "QUARANTINED",
        "previous_production_release": None,
        "deployment_authorized": False,
        "funded_operations": "DENIED",
        "recovery": "REQUIRES_SEPARATELY_REVIEWED_EXACT_INVERSE_AND_RECOVERY_RECEIPT",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--artifact", default="build/wolochaind")
    parser.add_argument("--output", default="build/financial-build-candidate.json")
    args = parser.parse_args()
    try:
        root = args.repo.resolve(strict=True)
        receipt = candidate(root, args.source_sha, args.artifact)
        output = local_path(root, args.output)
        if output == local_path(root, args.artifact):
            raise Hold("OUTPUT_IS_ARTIFACT")
        raw = (json.dumps(receipt, sort_keys=True, indent=2) + "\n").encode()
        fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(raw)
            f.flush()
            os.fsync(f.fileno())
        print(json.dumps({"build_identity": "PASS", "state": "QUARANTINED",
                          "deployment_authorized": False, "funded_operations": "DENIED",
                          "receipt_sha256": hashlib.sha256(raw).hexdigest()}))
        return 0
    except (Hold, OSError, subprocess.SubprocessError) as exc:
        reason = str(exc) if isinstance(exc, Hold) else type(exc).__name__
        print(json.dumps({"build_identity": "HOLD", "reason": reason,
                          "deployment_authorized": False, "funded_operations": "DENIED"}))
        return 2


if __name__ == "__main__":
    sys.exit(main())

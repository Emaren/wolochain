#!/usr/bin/env python3
"""Attest exact CI source and actual binary bytes; never install or authorize."""
import hashlib
import json
import os
import pathlib
import re
import subprocess
import sys


def build_receipt(root):
    source = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    if not re.fullmatch(r"[a-f0-9]{40}", source):
        raise ValueError("invalid_source")
    if subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=no"], text=True):
        raise ValueError("modified_source")
    binaries = {}
    for name in ("wolosatcheld", "wolochaind-settlement-UNDEPLOYED"):
        path = root / name
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 512 << 20:
            raise ValueError("invalid_binary")
        metadata = subprocess.check_output(["go", "version", "-m", str(path)], text=True)
        if f"vcs.revision={source}" not in metadata or "vcs.modified=false" not in metadata:
            raise ValueError("binary_source_mismatch")
        if "GOOS=linux" not in metadata or "GOARCH=amd64" not in metadata:
            raise ValueError("binary_platform_mismatch")
        with path.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        binaries[name] = {"sha256": digest, "source": source}
    return {"schema": 1, "source": source, "run_id": os.environ.get("GITHUB_RUN_ID"),
            "binaries": binaries, "custody_capability": "UNAVAILABLE",
            "production_authorized": False, "consensus_authorized": False,
            "financial_clearance": False, "installation_performed": False}


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("expected private build-output directory")
    directory = pathlib.Path(sys.argv[1]).resolve(strict=True)
    receipt = build_receipt(directory)
    (directory / "SOURCE_AUTHORITY.json").write_text(json.dumps(receipt, indent=2) + "\n")

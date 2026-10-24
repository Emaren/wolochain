#!/usr/bin/env python3
"""Read-only historic wolochaind byte-reproduction REVIEW, never a release permit.

Compares an isolated CI rebuild against the SHA of the already independently
observed old settlement executable. Reproducibility alone cannot authenticate
who originally built/deployed it, prove modified-consensus provenance, resolve
171 commits of finance behavior drift, or bypass app Finish.
"""
import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path

OLD_SOURCE = "78c25985420ee41a6678c42fab8ea8d6c3b1b519"
OLD_SETTLEMENT_SHA256 = "040126a2884946caf1651a50b7d8115c5a6fb2d5aa94fcbbe150694602d451a5"
# Owner read production's embedded build metadata directly on 2026-10-24.
# The historical source CI used Go 1.24.0 but DID NOT produce the on-host binary.
EXPECTED_GO = "go1.26.0"
EXPECTED_BUILD_SETTINGS = {
    "-trimpath": "true",
    "-buildmode": "exe",
    "-compiler": "gc",
    "CGO_ENABLED": "1",
    "GOOS": "linux",
    "GOARCH": "amd64",
    "GOAMD64": "v1",
}
HEX40 = re.compile(r"[0-9a-f]{40}\Z")
HEX64 = re.compile(r"[0-9a-f]{64}\Z")


def assess(*, source, tree_clean, toolchain, vcs_revision, vcs_modified,
           built_sha256, build_settings=None,
           expected_sha256=OLD_SETTLEMENT_SHA256):
    """Deterministic verdict; only exact-byte match is recognized, never GO."""
    checks = {
        "source_commit_exact": type(source) is str and source == OLD_SOURCE,
        "git_worktree_clean": tree_clean is True,
        "toolchain_exact": toolchain == EXPECTED_GO,
        "embedded_build_settings_match_live":
            type(build_settings) is dict and all(
                build_settings.get(k) == v
                for k, v in EXPECTED_BUILD_SETTINGS.items()),
        "go_embedded_source_exact": vcs_revision == OLD_SOURCE,
        "go_embedded_modified_false": vcs_modified == "false",
        "rebuilt_sha256_well_formed": type(built_sha256) is str
                                   and HEX64.fullmatch(built_sha256) is not None,
        "observed_live_sha256_well_formed": type(expected_sha256) is str
                                          and HEX64.fullmatch(expected_sha256) is not None,
        "rebuilt_bytes_match_live": built_sha256 == expected_sha256,
    }
    complete = all(checks.values())
    return {
        "schema": "wolo.legacy-settlement-reproduction-review.v1",
        "status": ("EXACT_BYTE_MATCH_NONAUTHORIZING" if complete
                   else "REPRODUCTION_NOT_ESTABLISHED_HOLD"),
        "original_settlement_source": OLD_SOURCE,
        "observed_live_binary_sha256": OLD_SETTLEMENT_SHA256,
        "rebuild_sha256": built_sha256,
        "checks": checks,
        "original_builder_identity_independently_verified": False,
        "original_deployment_custody_verified": False,
        "consensus_dirty_tree_source_reconstructed": False,
        "semantic_171_commit_p1_resolved": False,
        "independent_human_approval_obtained": False,
        "website_release_authorized": False,
        "financial_release_authorized": False,
        "production_binary_change_authorized": False,
    }


def capture(command):
    result = subprocess.run(command, capture_output=True, text=True, timeout=30,
                            check=False)
    if result.returncode:
        raise RuntimeError("READ_ONLY_PROBE_RC_%d" % result.returncode)
    return result.stdout.strip()


def review(binary, source_dir):
    binary = Path(binary)
    source_dir = Path(source_dir)
    if binary.is_symlink() or not binary.is_file():
        raise RuntimeError("REBUILT_BINARY_MISSING_OR_SYMLINK")
    if not (source_dir / ".git").is_dir():
        raise RuntimeError("ISOLATED_GIT_CHECKOUT_REQUIRED")
    source = capture(["git", "-C", str(source_dir), "rev-parse", "--verify", "HEAD"])
    dirty = capture(["git", "-C", str(source_dir), "status",
                     "--porcelain", "--untracked-files=no"])
    go = capture(["go", "version"]).split()
    toolchain = go[2] if len(go) >= 3 else None
    metadata = capture(["go", "version", "-m", str(binary)])
    fields = {}
    for line in metadata.splitlines():
        pieces = line.strip().split(None, 1)
        if len(pieces) == 2 and pieces[0] == "build" and "=" in pieces[1]:
            k, v = pieces[1].split("=", 1)
            if k in fields:
                raise RuntimeError("DUPLICATE_BUILD_METADATA")
            fields[k] = v
    hasher = hashlib.sha256()
    with binary.open("rb") as f:
        for part in iter(lambda: f.read(1024 * 1024), b""):
            hasher.update(part)
    verdict = assess(source=source, tree_clean=dirty == "",
                     toolchain=toolchain,
                     vcs_revision=fields.get("vcs.revision"),
                     vcs_modified=fields.get("vcs.modified"),
                     build_settings=fields,
                     built_sha256=hasher.hexdigest())
    return verdict


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", required=True)
    parser.add_argument("--source-dir", required=True)
    args = parser.parse_args()
    print("STEP: isolated original settlement byte reproduction", flush=True)
    try:
        result = review(args.binary, args.source_dir)
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
        print(json.dumps({"status": "BLOCKED", "error": str(exc),
                          "website_release_authorized": False,
                          "financial_release_authorized": False},
                         sort_keys=True))
        print("RC=2 BLOCKED: independent original build origin not established")
        return 2
    print(json.dumps(result, sort_keys=True))
    matched = result["status"] == "EXACT_BYTE_MATCH_NONAUTHORIZING"
    print("RC=%d %s; ORIGINAL_BUILD_DEPLOY_PROVENANCE_STILL_UNKNOWN" %
          (0 if matched else 2, "PASS BYTE_REPRODUCIBILITY_ONLY" if matched
           else "BLOCKED BYTE_REPRODUCIBILITY_NOT_ESTABLISHED"))
    return 0 if matched else 2


if __name__ == "__main__":
    raise SystemExit(main())

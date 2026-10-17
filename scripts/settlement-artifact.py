#!/usr/bin/env python3
"""Offline, non-executing provenance for strict named source artifact profiles.

The expected CI identity is supplied separately from the manifest. This checks
bytes and consistency; GitHub's authenticated run/artifact receipt remains the
external authority for who performed the build. It grants no deployment rights.
"""

from __future__ import annotations

import argparse
import copy
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import selectors
import signal
import stat
import struct
import subprocess
import sys
import tempfile
import time

EXPECTED_SOURCE = "526d5eb6123f6cc0394b5e78489c668e77e46106"
COMPOSED_SOURCE = "155fcf67fb2127a2227de5ea785e51bdbb0155c0"
PINNED_GO_VERSION = "go1.24.6"
EXPECTED_REPOSITORY = "Emaren/wolochain"
EXPECTED_MAIN_PATH = "github.com/emaren/wolochain/cmd/wolochaind"
WORKFLOW_PATH = ".github/workflows/legacy-settlement-exact-526d5-artifact.yml"
COMPOSED_WORKFLOW_PATH = ".github/workflows/composed-satcheld-exact-artifact.yml"
MAX_BINARY_BYTES = 256 * 1024 * 1024
MAX_MANIFEST_BYTES = 64 * 1024
MAX_COMMAND_BYTES = 4 * 1024 * 1024
COMMAND_TIMEOUT_SECONDS = 30
RECIPE = {
    "toolchain": PINNED_GO_VERSION,
    "environment": {
        "GOOS": "linux", "GOARCH": "amd64", "GOAMD64": "v1",
        "CGO_ENABLED": "0", "GOTOOLCHAIN": "local", "GOENV": "off",
        "GOWORK": "off", "GOFLAGS": "", "GOEXPERIMENT": "", "GOFIPS140": "off",
        "GIT_NO_REPLACE_OBJECTS": "1",
    },
    "build_flags": [
        "-trimpath", "-buildvcs=true", "-tags=go1.27", "-mod=readonly",
        "-ldflags=-buildid=",
    ],
    "package": "./cmd/wolochaind",
}
AUTHORITY = {
    "production_authorized": False,
    "consensus_upgrade_authorized": False,
    "satchel_activation_authorized": False,
    "financial_readiness_attested": False,
    "runtime_identity_attested": False,
    "founder_889_resolved": False,
    "rollback_certified": False,
}


class ArtifactError(ValueError):
    """Candidate cannot be accepted under this exact-source proof contract."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ArtifactError(message)


def profile_policy(profile: str = "legacy526") -> dict:
    """Only reviewed source pins; callers cannot supply an arbitrary revision."""
    _require(type(profile) is str and profile in ("legacy526", "composed-satcheld"),
             "unknown artifact profile")
    if profile == "legacy526":
        return {
            "source": EXPECTED_SOURCE, "binary": "wolochaind",
            "main_path": EXPECTED_MAIN_PATH, "package": "./cmd/wolochaind",
            "workflow": WORKFLOW_PATH, "purpose": "UNDEPLOYED_SETTLEMENT_CANDIDATE",
        }
    _require(re.fullmatch(r"[0-9a-f]{40}", COMPOSED_SOURCE) is not None,
             "NONACCEPTING composed source: reviewed implementation pin unavailable")
    return {
        "source": COMPOSED_SOURCE, "binary": "wolosatcheld",
        "main_path": "github.com/emaren/wolochain/cmd/wolosatcheld",
        "package": "./cmd/wolosatcheld", "workflow": COMPOSED_WORKFLOW_PATH,
        "purpose": "UNDEPLOYED_COMPOSED_SATCHELD_CANDIDATE",
    }


def _run(arguments: list[str]) -> str:
    """Run inspection tools, with bounded time and combined captured output."""
    environment = os.environ.copy()
    environment.update({"GOTOOLCHAIN": "local", "GOENV": "off", "GOWORK": "off"})
    process = subprocess.Popen(
        arguments, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        env=environment, start_new_session=True,
    )
    selector = selectors.DefaultSelector()
    output = {"stdout": bytearray(), "stderr": bytearray()}
    assert process.stdout is not None and process.stderr is not None
    selector.register(process.stdout, selectors.EVENT_READ, "stdout")
    selector.register(process.stderr, selectors.EVENT_READ, "stderr")
    deadline = time.monotonic() + COMMAND_TIMEOUT_SECONDS
    total = 0
    try:
        while selector.get_map():
            _require(time.monotonic() < deadline, "inspection command timed out")
            for key, _ in selector.select(min(0.2, max(0, deadline - time.monotonic()))):
                data = os.read(key.fileobj.fileno(), 65536)
                if not data:
                    selector.unregister(key.fileobj)
                    continue
                total += len(data)
                _require(total <= MAX_COMMAND_BYTES, "inspection output exceeds limit")
                output[key.data].extend(data)
        remaining = max(0.001, deadline - time.monotonic())
        _require(process.wait(timeout=remaining) == 0, "inspection command failed")
        return output["stdout"].decode("utf-8", errors="strict")
    except subprocess.TimeoutExpired as error:
        raise ArtifactError("inspection command timed out") from error
    finally:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait()
        selector.close()
        process.stdout.close()
        process.stderr.close()


def _sha(value: object, length: int, label: str) -> str:
    _require(type(value) is str and re.fullmatch(r"[0-9a-f]{%d}" % length, value) is not None,
             f"invalid {label}")
    return value


def source_identity(source_dir: str | Path, profile: str = "legacy526") -> dict:
    policy = profile_policy(profile)
    directory = str(Path(source_dir).resolve(strict=True))

    def git(*arguments: str) -> str:
        return _run(["git", "--no-replace-objects", "-C", directory, *arguments]).strip()

    revision = _sha(git("rev-parse", "HEAD"), 40, "source revision")
    _require(revision == policy["source"], "source drift: checkout is not the reviewed source")
    tracked = git("ls-files", "-v").splitlines()
    _require(bool(tracked) and all(line.startswith("H ") for line in tracked),
             "source index hides tracked files (assume-unchanged or skip-worktree)")
    _require(not git("status", "--porcelain=v1", "--untracked-files=all", "--ignored=matching"),
             "dirty source tree (including untracked or ignored files)")
    tree = _sha(git("rev-parse", "HEAD^{tree}"), 40, "source tree")
    timestamp = git("show", "-s", "--format=%ct", "HEAD")
    _require(re.fullmatch(r"[0-9]{1,12}", timestamp) is not None, "invalid source commit time")
    vcs_time = datetime.datetime.fromtimestamp(int(timestamp), datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    return {"commit": revision, "tree": tree, "vcs_time": vcs_time, "dirty": False}


def _parse_go_metadata(metadata: str, profile: str = "legacy526") -> dict:
    policy = profile_policy(profile)
    lines = metadata.splitlines()
    _require(bool(lines) and ": " in lines[0], "missing Go build metadata")
    version = lines[0].rsplit(": ", 1)[1]
    _require(version == PINNED_GO_VERSION, "compiler version mismatch")
    settings = {}
    paths = []
    for line in lines[1:]:
        fields = line.split("\t")
        if len(fields) >= 3 and fields[1] == "path":
            _require(len(fields) == 3, "invalid Go main package metadata")
            paths.append(fields[2])
        elif len(fields) >= 3 and fields[1] == "build":
            _require(len(fields) == 3 and "=" in fields[2], "invalid Go build setting")
            key, value = fields[2].split("=", 1)
            _require(key not in settings, "duplicate Go build setting")
            settings[key] = value
    _require(paths == [policy["main_path"]], "binary main package mismatch")
    expected = {
        "-buildmode": "exe", "-compiler": "gc", "-tags": "go1.27", "-trimpath": "true",
        "CGO_ENABLED": "0", "GOARCH": "amd64", "GOOS": "linux", "GOAMD64": "v1",
        "vcs": "git", "vcs.revision": policy["source"], "vcs.modified": "false",
    }
    _require(set(settings) == set(expected) | {"vcs.time"}, "unexpected or absent Go build settings")
    for key, value in expected.items():
        _require(settings.get(key) == value, f"embedded {key} mismatch")
    _require(re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", settings["vcs.time"]) is not None,
             "invalid embedded VCS time")
    return {"version": version, "path": paths[0], "build_settings": settings}


def inspect_binary(path: str | Path, go: str = "go", profile: str = "legacy526") -> dict:
    """Inspect a stable private snapshot; never execute the candidate binary."""
    path = Path(path)
    policy = profile_policy(profile)
    _require(path.name == policy["binary"], "binary filename must be " + policy["binary"])
    flags = os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0)
    with os.fdopen(os.open(path, flags), "rb") as source, tempfile.TemporaryDirectory(
        prefix="wolo-artifact-inspect-"
    ) as temporary:
        original = os.fstat(source.fileno())
        _require(stat.S_ISREG(original.st_mode), "binary is not a regular file")
        _require(64 <= original.st_size <= MAX_BINARY_BYTES, "binary size outside limits")
        snapshot = Path(temporary) / policy["binary"]
        digest = hashlib.sha256()
        total = 0
        with snapshot.open("xb") as destination:
            while chunk := source.read(1024 * 1024):
                total += len(chunk)
                _require(total <= MAX_BINARY_BYTES, "binary exceeds size limit")
                destination.write(chunk)
                digest.update(chunk)
        after = os.fstat(source.fileno())
        current = os.stat(path, follow_symlinks=False)
        identity = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
        _require(identity(original) == identity(after) == identity(current) and total == original.st_size,
                 "binary changed during inspection")
        with snapshot.open("rb") as executable:
            header = executable.read(64)
        _require(header[:7] == b"\x7fELF\x02\x01\x01" and header[7] in (0, 3),
                 "binary is not a little-endian ELF64 Linux candidate")
        _require(struct.unpack_from("<HHI", header, 16) == (2, 62, 1),
                 "binary ELF architecture or executable type mismatch")
        _require(struct.unpack_from("<H", header, 52)[0] == 64, "invalid ELF header size")
        metadata = _parse_go_metadata(_run([go, "version", "-m", str(snapshot)]), profile)
        build_id = _run([go, "tool", "buildid", str(snapshot)]).strip()
        _require(build_id == "", "binary has an unexpected Go build ID")
        return {
            "name": path.name, "size": total, "sha256": digest.hexdigest(),
            "format": "ELF64-little-linux-amd64", "go": metadata, "build_id": build_id,
        }


def _identity(identity: dict, profile: str = "legacy526") -> dict:
    policy = profile_policy(profile)
    expected_keys = {"repository", "builder_commit", "run_id", "run_attempt", "workflow_ref", "workflow_sha"}
    _require(type(identity) is dict and set(identity) == expected_keys, "invalid GitHub identity fields")
    _require(all(type(value) is str for value in identity.values()), "GitHub identity values must be strings")
    _require(identity["repository"] == EXPECTED_REPOSITORY, "GitHub repository mismatch")
    _sha(identity["builder_commit"], 40, "builder commit")
    _sha(identity["workflow_sha"], 40, "workflow SHA")
    for key in ("run_id", "run_attempt"):
        _require(re.fullmatch(r"[1-9][0-9]{0,19}", identity[key]) is not None, f"invalid GitHub {key}")
    prefix = EXPECTED_REPOSITORY + "/" + policy["workflow"] + "@refs/"
    reference = identity["workflow_ref"]
    _require(reference.startswith(prefix) and len(reference) <= 1024
             and re.fullmatch(r"[^\s\x00-\x1f]+", reference) is not None
             and reference[len(prefix):].startswith(("heads/", "pull/")),
             "GitHub workflow reference mismatch")
    return dict(identity)


def _manifest(binary: dict, source: dict, identity: dict, profile: str = "legacy526") -> dict:
    policy = profile_policy(profile)
    _require(binary["go"]["build_settings"]["vcs.time"] == source["vcs_time"],
             "embedded VCS time disagrees with source")
    manifest = {
        "schema_version": 1,
        "purpose": policy["purpose"],
        "source": source,
        "binary": binary,
        "recipe": copy.deepcopy(RECIPE),
        "reproducibility": {
            "comparison": "byte-for-byte", "builds": 2, "second_sha256": binary["sha256"],
        },
        "github": _identity(identity, profile),
        "authority": dict(AUTHORITY),
    }
    manifest["recipe"]["package"] = policy["package"]
    if profile != "legacy526":
        manifest.update({"schema_version": 2, "profile": profile})
    return manifest


def create_manifest(binary: str | Path, rebuild: str | Path, source_dir: str | Path,
                    identity: dict, go: str = "go", profile: str = "legacy526") -> dict:
    source = source_identity(source_dir, profile)
    _require(not os.path.samefile(binary, rebuild), "reproducibility requires distinct build files")
    first = inspect_binary(binary, go, profile)
    second = inspect_binary(rebuild, go, profile)
    _require(first == second, "independent build bytes or metadata disagree")
    _require(source_identity(source_dir, profile) == source, "source changed during verification")
    return _manifest(first, source, identity, profile)


def verify_manifest(manifest: dict, binary: str | Path, source_dir: str | Path,
                    identity: dict, go: str = "go", profile: str = "legacy526") -> None:
    """Check internal consistency, without authenticating an unsigned manifest.

    Authoritative CLI verification additionally requires the raw manifest digest
    from the independently authenticated GitHub run/artifact receipt.
    """
    expected = _manifest(inspect_binary(binary, go, profile), source_identity(source_dir, profile), identity, profile)
    # Compare canonical JSON, rather than Python equality (where False == 0).
    canonical = lambda value: json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    _require(canonical(manifest) == canonical(expected), "manifest mismatch against source, binary or expected CI identity")


def load_manifest(path: str | Path, expected_sha256: str | None = None) -> dict:
    """Read bounded JSON, optionally bound to an externally trusted raw digest."""
    if expected_sha256 is not None:
        _sha(expected_sha256, 64, "expected manifest SHA-256")
    def unique_pairs(pairs: list[tuple[str, object]]) -> dict:
        result = {}
        for key, value in pairs:
            _require(key not in result, "duplicate manifest JSON field")
            result[key] = value
        return result

    def invalid_constant(_: str) -> None:
        raise ArtifactError("nonfinite JSON value")

    flags = os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0)
    with os.fdopen(os.open(path, flags), "rb") as source:
        _require(stat.S_ISREG(os.fstat(source.fileno()).st_mode), "manifest is not a regular file")
        data = source.read(MAX_MANIFEST_BYTES + 1)
    _require(len(data) <= MAX_MANIFEST_BYTES, "manifest exceeds size limit")
    if expected_sha256 is not None:
        _require(hashlib.sha256(data).hexdigest() == expected_sha256,
                 "manifest receipt SHA-256 mismatch")
    try:
        value = json.loads(data, object_pairs_hook=unique_pairs,
                           parse_constant=invalid_constant)
    except (json.JSONDecodeError, UnicodeDecodeError, RecursionError) as error:
        raise ArtifactError("malformed manifest JSON") from error
    _require(type(value) is dict, "manifest must be a JSON object")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("create", "verify"))
    parser.add_argument("--profile", choices=("legacy526", "composed-satcheld"), default="legacy526")
    for argument in ("source-dir", "binary", "manifest", "builder-commit", "repository",
                     "run-id", "run-attempt", "workflow-ref", "workflow-sha"):
        parser.add_argument("--" + argument, required=True)
    parser.add_argument("--rebuild", help="second independently built binary (create only)")
    parser.add_argument("--expected-manifest-sha256",
                        help="required for verify: raw manifest digest from an authenticated CI receipt")
    parser.add_argument("--go", default="go", help="trusted Go metadata inspection tool")
    arguments = parser.parse_args(argv)
    identity = {key: getattr(arguments, key) for key in (
        "repository", "builder_commit", "run_id", "run_attempt", "workflow_ref", "workflow_sha"
    )}
    try:
        if arguments.command == "create":
            _require(arguments.expected_manifest_sha256 is None,
                     "create does not accept --expected-manifest-sha256")
            _require(bool(arguments.rebuild), "create requires --rebuild")
            manifest = create_manifest(arguments.binary, arguments.rebuild, arguments.source_dir,
                                       identity, arguments.go, arguments.profile)
            data = json.dumps(manifest, indent=2, sort_keys=True, allow_nan=False) + "\n"
            _require(len(data.encode("utf-8")) <= MAX_MANIFEST_BYTES, "manifest exceeds size limit")
            with Path(arguments.manifest).open("x", encoding="utf-8") as output:
                output.write(data)
        else:
            _require(arguments.rebuild is None, "verify does not accept --rebuild")
            _require(arguments.expected_manifest_sha256 is not None,
                     "verify requires --expected-manifest-sha256 from an authenticated CI receipt")
            verify_manifest(load_manifest(arguments.manifest, arguments.expected_manifest_sha256), arguments.binary,
                            arguments.source_dir, identity, arguments.go, arguments.profile)
    except (ArtifactError, OSError, UnicodeError, ValueError) as error:
        print(f"INVALID SETTLEMENT ARTIFACT: {error}", file=sys.stderr)
        return 2
    print("VERIFIED exact-source UNDEPLOYED settlement artifact; no runtime or financial authority")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

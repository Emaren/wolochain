#!/usr/bin/env python3
"""Compare two *complete observed* 100-WOLO escrow identity manifests.

Read-only, privacy-minimized, source-HELD reconciliation leads. Input files
must come from settlement-state-evidence.py --full-escrow-100-manifest, captured
in the same primary/founder root order. This is NOT an atomic delta, an
authenticated chain proof, a payment conclusion, or financial release authority.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys

MAX_INPUT_BYTES = 4 << 20
MAX_RECORDS = 2500
HEX = re.compile(r"[0-9a-f]{64}\Z")
STATUS = {"accepted", "confirmed"}
VERSION = "wolo.settlement.escrow100-observed-delta.v1"


class InvalidManifest(ValueError):
    pass


def _reject(code):
    raise InvalidManifest(code)


def _object(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            _reject("DUPLICATE_JSON_KEY")
        out[key] = value
    return out


def _digest(value):
    return isinstance(value, str) and HEX.fullmatch(value) is not None


def read_snapshot(path):
    """Open exact local file once without following symlinks; never print paths."""
    fd = None
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_size > MAX_INPUT_BYTES:
            _reject("INVALID_SNAPSHOT_FILE")
        raw = bytearray()
        while len(raw) <= MAX_INPUT_BYTES:
            chunk = os.read(fd, min(65536, MAX_INPUT_BYTES + 1 - len(raw)))
            if not chunk:
                break
            raw.extend(chunk)
        after = os.fstat(fd)
        if len(raw) > MAX_INPUT_BYTES or (before.st_dev, before.st_ino, before.st_size,
                before.st_mtime_ns, before.st_ctime_ns) != (
                after.st_dev, after.st_ino, after.st_size,
                after.st_mtime_ns, after.st_ctime_ns):
            _reject("SNAPSHOT_CHANGED_DURING_READ")
        snapshot = json.loads(raw, object_pairs_hook=_object,
                              parse_constant=lambda _: _reject("INVALID_JSON_NUMBER"))
        if not isinstance(snapshot, dict):
            _reject("INVALID_SNAPSHOT_SHAPE")
        return snapshot, hashlib.sha256(raw).hexdigest()
    except InvalidManifest:
        raise
    except (OSError, ValueError, RecursionError, UnicodeError):
        _reject("INVALID_SNAPSHOT_FILE")
    finally:
        if fd is not None:
            os.close(fd)


def _extract(doc):
    if (type(doc) is not dict
            or doc.get("version") != "wolo.settlement.state-evidence.v1"
            or doc.get("status") != "HELD"
            or doc.get("observation_complete") is not True
            or doc.get("observation_atomic") is not False
            or doc.get("chain_proof_verified") is not False
            or doc.get("release_authorized") is not False
            or doc.get("retry_authorized") is not False
            or type(doc.get("roots_observed")) is not int
            or doc["roots_observed"] not in (1, 2)
            or not _digest(doc.get("source_tree_sha256"))):
        _reject("UNTRUSTED_OBSERVATION")
    focus = doc.get("escrow100Focus")
    manifest = doc.get("escrow100IdentityManifest")
    if (type(focus) is not dict or type(manifest) is not dict
            or manifest.get("schema") != "wolo.settlement.escrow100-identity-manifest.v1"
            or manifest.get("complete_for_observed_100_wolo_requests") is not True
            or manifest.get("authoritative_chain_evidence") is not False
            or manifest.get("financial_release_authorized") is not False
            or type(manifest.get("records")) is not list
            or type(focus.get("matchedAcceptedCount")) is not int
            or type(focus.get("matchedConfirmedCount")) is not int):
        _reject("INCOMPLETE_ESCROW_IDENTITY_MANIFEST")
    rows = manifest["records"]
    if (len(rows) > MAX_RECORDS or
            len(rows) != focus["matchedAcceptedCount"] + focus["matchedConfirmedCount"] or
            manifest.get("count") != len(rows)):
        _reject("INCONSISTENT_IDENTITY_COUNTS")
    found = {}
    accepted = confirmed = 0
    previous = None
    for row in rows:
        if (type(row) is not dict
                or set(row) != {"laneIndex", "recordedStatus", "requestIdSha256",
                                    "requestRecordSha256"}
                or type(row["laneIndex"]) is not int
                or not 0 <= row["laneIndex"] < doc["roots_observed"]
                or row["recordedStatus"] not in STATUS
                or not _digest(row["requestIdSha256"])
                or not _digest(row["requestRecordSha256"])):
            _reject("INVALID_ESCROW_IDENTITY_ROW")
        key = (row["laneIndex"], row["requestIdSha256"])
        if key in found or (previous is not None and key <= previous):
            _reject("DUPLICATE_OR_UNSORTED_IDENTITY")
        previous = key
        found[key] = row
        accepted += row["recordedStatus"] == "accepted"
        confirmed += row["recordedStatus"] == "confirmed"
    if (accepted != focus["matchedAcceptedCount"]
            or confirmed != focus["matchedConfirmedCount"]):
        _reject("INCONSISTENT_IDENTITY_COUNTS")
    return found


def compare(before, after, before_digest=None, after_digest=None):
    left = _extract(before)
    right = _extract(after)
    if before["roots_observed"] != after["roots_observed"]:
        _reject("ROOT_LANE_COUNT_CHANGED")
    added = [right[key] for key in sorted(right.keys() - left.keys())]
    removed = [left[key] for key in sorted(left.keys() - right.keys())]
    changed = [{"laneIndex": key[0], "requestIdSha256": key[1],
                "beforeStatus": left[key]["recordedStatus"],
                "afterStatus": right[key]["recordedStatus"],
                "beforeRecordSha256": left[key]["requestRecordSha256"],
                "afterRecordSha256": right[key]["requestRecordSha256"]}
               for key in sorted(left.keys() & right.keys()) if left[key] != right[key]]
    return {
        "version": VERSION, "status": "HELD",
        "comparison_complete_for_supplied_manifests": True,
        "before_snapshot_sha256": before_digest,
        "after_snapshot_sha256": after_digest,
        "before_source_tree_sha256": before["source_tree_sha256"],
        "after_source_tree_sha256": after["source_tree_sha256"],
        "roots_observed": before["roots_observed"],
        "before_count": len(left), "after_count": len(right),
        "added": added, "removed": removed, "changed": changed,
        "added_count": len(added), "removed_count": len(removed),
        "changed_count": len(changed),
        "root_lane_identity_independently_verified": False,
        "historical_arrival_time_proven": False,
        "snapshots_atomic": False,
        "chain_proof_verified": False,
        "payment_outcome_certified": False,
        "global_liabilities_complete": False,
        "financial_release_authorized": False,
        "retry_authorized": False,
        "filesystem_writes": False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before", required=True, type=Path)
    parser.add_argument("--after", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        old, old_digest = read_snapshot(args.before)
        new, new_digest = read_snapshot(args.after)
        report = compare(old, new, old_digest, new_digest)
    except InvalidManifest as exc:
        print(json.dumps({"version": VERSION, "status": "HELD",
                          "comparison_complete_for_supplied_manifests": False,
                          "error": str(exc), "financial_release_authorized": False,
                          "retry_authorized": False}, sort_keys=True))
        return 2
    print(json.dumps(report, indent=2, sort_keys=True))
    return 3  # A valid observation is *still financially held*.


if __name__ == "__main__":
    sys.exit(main())

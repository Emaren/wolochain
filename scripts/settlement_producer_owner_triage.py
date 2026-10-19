#!/usr/bin/env python3
"""Read-only owner-review correlation of existing HD/DE producer source and VPS unit observations.

No shell/systemctl, root, network, tokens, private env, database, signing or mutations.
All three inputs are independently obtained OBSERVATIONS, not permits or fences.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import stat
import sys

MAX_BYTES = 512_000
MAX_UNITS = 150
MAX_OBSERVATIONS = 512
MAX_AGE_SECONDS = 3600
UNIT = re.compile(r"^[a-zA-Z0-9_.@:-]{1,120}\.(?:service|timer)$")
SOURCE_SHA = re.compile(r"^[a-f0-9]{40}$")
EXPECTED_RUNTIME_MODE = "READ_ONLY_SHARED_HD_DE_PAYOUT_INGRESS_INVENTORY"
HD_SCHEMA = "aoe2war.app.financial_producer_source_census.v1"
DE_SCHEMA = "wolo.financial.de-producer-source-map.v1"

# These are review-owner classifications, NOT automatic stop or restart selections.
def owner(unit: str) -> str:
    if unit.startswith("aoe2dewarwagers-"):
        return "DE"
    if unit.startswith(("aoe2hdbets-", "aoe2war-", "aoe2-wolo-")):
        return "HD_OR_SHARED"
    return "UNKNOWN_OWNER"


def unique_json(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("DUPLICATE_JSON_KEY")
        result[key] = value
    return result


def read_packet(p: Path) -> dict:
    try:
        if p.is_symlink():
            raise ValueError("SYMLINK_PACKET")
        stat_result = p.lstat()
        if not stat.S_ISREG(stat_result.st_mode) or not (0 < stat_result.st_size <= MAX_BYTES):
            raise ValueError("PACKET_SIZE_OR_TYPE")
        fd = os.open(p, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        try:
            opened = os.fstat(fd)
            if (not stat.S_ISREG(opened.st_mode) or opened.st_ino != stat_result.st_ino
                    or opened.st_dev != stat_result.st_dev or opened.st_size != stat_result.st_size):
                raise ValueError("PACKET_CHANGED")
            raw = os.read(fd, MAX_BYTES + 1)
            if len(raw) != opened.st_size:
                raise ValueError("PACKET_CHANGED")
        finally:
            os.close(fd)
        data = json.loads(raw, object_pairs_hook=unique_json,
                          parse_constant=lambda _: (_ for _ in ()).throw(ValueError("NONFINITE_JSON")))
        if not isinstance(data, dict):
            raise ValueError("PACKET_NOT_OBJECT")
        return data
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("PACKET_UNREADABLE") from exc


def report(runtime: dict | None, hd: dict | None, de: dict | None,
           now: datetime | None = None) -> dict:
    """Pure fail-closed correlation. Only public unit names, counts and fixed status strings."""
    moment = now or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        raise ValueError("NAIVE_TIMESTAMP")
    issues = []
    mapped = []
    runtime_fresh = False
    seen = set()
    if not isinstance(runtime, dict) or runtime.get("mode") != EXPECTED_RUNTIME_MODE:
        issues.append("RUNTIME_INVENTORY_MISSING_OR_INVALID")
    else:
        timestamp = runtime.get("observedAtUtc")
        try:
            at = datetime.fromisoformat(str(timestamp).replace("Z", "+00:00"))
            age = (moment - at).total_seconds()
            runtime_fresh = at.tzinfo is not None and 0 <= age <= MAX_AGE_SECONDS
        except (ValueError, TypeError):
            runtime_fresh = False
        if not runtime_fresh:
            issues.append("RUNTIME_INVENTORY_STALE_OR_UNDATED")
        units = runtime.get("appUnits")
        if not isinstance(units, list) or len(units) > MAX_UNITS:
            issues.append("RUNTIME_UNITS_INVALID_OR_UNBOUNDED")
        else:
            for unit in units:
                if not isinstance(unit, dict) or not isinstance(unit.get("unit"), str):
                    issues.append("RUNTIME_UNIT_MALFORMED")
                    continue
                name = unit["unit"]
                if not UNIT.fullmatch(name) or name in seen:
                    issues.append("RUNTIME_UNIT_INVALID_OR_DUPLICATE")
                    continue
                seen.add(name)
                label = owner(name)
                is_active = unit.get("active") is True
                inspection_complete = isinstance(unit.get("active"), bool) and isinstance(
                    unit.get("mainPidPresent"), bool)
                if not inspection_complete:
                    issues.append("UNIT_INSPECTION_INCOMPLETE")
                mapped.append({
                    "unit": name,
                    "owner": label,
                    "activeObserved": is_active if inspection_complete else None,
                    "mainPidPresent": unit.get("mainPidPresent") if inspection_complete else None,
                    "runtimeSignerProof": "UNKNOWN",
                    "reviewStatus": "OWNER_REVIEW_REQUIRED",
                })
            if runtime.get("inventoryCompleteForDiscoveredUnits") is not True or runtime.get("unitsWithIncompleteInspection"):
                issues.append("RUNTIME_DISCOVERED_UNIT_COVERAGE_UNKNOWN")
            if not mapped:
                issues.append("RUNTIME_ZERO_UNITS_NOT_PROOF_OF_NO_WRITERS")
    hd_edges = (
        isinstance(hd, dict) and hd.get("schema") == HD_SCHEMA
        and hd.get("classification") == "SOURCE_OBSERVATION_ONLY"
        and hd.get("known_source_edges_intact") is True
        and isinstance(hd.get("observations"), list)
        and 0 < len(hd["observations"]) <= MAX_OBSERVATIONS
        and all(isinstance(e, dict) and e.get("status") == "SOURCE_OBSERVED"
                for e in hd["observations"])
    )
    de_edges = (
        isinstance(de, dict) and de.get("schema") == DE_SCHEMA
        and de.get("mode") == "READ_ONLY_NONAUTHORIZING"
        and de.get("known_de_source_edges_intact") is True
        and isinstance(de.get("observations"), list)
        and 0 < len(de["observations"]) <= MAX_OBSERVATIONS
        and all(isinstance(e, dict) and e.get("status") == "SOURCE_OBSERVED"
                for e in de["observations"])
        and isinstance(de.get("local_source"), dict)
        and de["local_source"].get("state") == "LOCAL_CLEAN_GIT_ONLY"
        and isinstance(de["local_source"].get("head"), str)
        and bool(SOURCE_SHA.fullmatch(de["local_source"]["head"]))
    )
    if not hd_edges:
        issues.append("HD_SOURCE_EDGE_PROOF_MISSING_OR_DRIFTED")
    if not de_edges:
        issues.append("DE_SOURCE_EDGE_PROOF_MISSING_OR_DRIFTED")
    counts = {
        "unitsObserved": len(mapped),
        "activeObserved": sum(1 for e in mapped if e["activeObserved"] is True),
        "hdOrSharedUnits": sum(1 for e in mapped if e["owner"] == "HD_OR_SHARED"),
        "deUnits": sum(1 for e in mapped if e["owner"] == "DE"),
        "unknownOwnerUnits": sum(1 for e in mapped if e["owner"] == "UNKNOWN_OWNER"),
    }
    issues.extend((
        "DEPLOYED_HD_DE_SOURCE_TO_RUNTIME_BINDING_UNPROVEN",
        "CRON_USER_CONTAINERS_EXTERNAL_SIGNERS_UNPROVEN",
        "QUEUES_INFLIGHT_AND_BANK_LIABILITIES_UNRECONCILED",
        "NAMED_FINANCIAL_FENCE_APPROVAL_MISSING",
    ))
    return {
        "schema": "wolo.financial.producer-owner-triage.v1",
        "mode": "READ_ONLY_NONAUTHORIZING",
        "status": "HOLD",
        "runtimeFresh": runtime_fresh,
        "hdSourceObserved": bool(hd_edges),
        "deSourceObserved": bool(de_edges),
        "counts": counts,
        "unitOwnerReview": sorted(mapped, key=lambda x: x["unit"]),
        "unresolved": sorted(set(issues)),
        "sourceRuntimeParityProven": False,
        "producerIsolationProven": False,
        "allTransfersReconciled": False,
        "financialReleaseAuthorized": False,
        "websiteReleaseAuthorized": False,
        "productionMutated": False,
        "note": "This is a review queue, not a stop list or signed release receipt.",
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--hd-source", type=Path, required=True)
    parser.add_argument("--de-source", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        output = report(read_packet(args.runtime), read_packet(args.hd_source), read_packet(args.de_source))
    except ValueError:
        output = report(None, None, None)
    print(json.dumps(output, indent=2, sort_keys=True))
    return 3  # no invocation can signal producer isolation or release authorization


if __name__ == "__main__":
    sys.exit(main())

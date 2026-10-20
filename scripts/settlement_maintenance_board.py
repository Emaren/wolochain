#!/usr/bin/env python3
"""Offline six-control financial HOLD board: an operator handoff, never a permit.

Consumes WoloChain's checksummed historical six-control evidence index and
optionally the sanitized HD/DE/VPS producer-owner triage packet. Performs no
network, SSH, root inspection, writes, key access, chain queries or broadcasts.
Every successful report exits 3: it cannot be mistaken for release approval.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys

from financial_release_checklist_audit import (
    audit as audit_historical_evidence,
    json_object,
    safe_read,
    INDEX,
    CONTROLS,
    SCHEMA,
    AuditFailure,
)
from settlement_producer_owner_triage import read_packet as read_sanitized_packet

TRIAGE_SCHEMA = "wolo.financial.producer-owner-triage.v1"
SHA40 = re.compile(r"[0-9a-f]{40}\Z")
UNIT = re.compile(r"[a-zA-Z0-9_.@:-]{1,120}\.(?:service|timer)\Z")
OWNERS = frozenset({"HD_OR_SHARED", "DE", "UNKNOWN_OWNER"})
MAX_REVIEW_UNITS = 150
NEXT_BOUNDARIES = (
    "Name HD, DE and external owners of every active or latent financial producer",
    "Independently inventory cron, user managers, containers, API/GET side effects, signing paths and queued work",
    "Approve separately the exact bounded maintenance and producer fence/drain; no blanket stop",
    "Reconcile each accepted or uncertain transfer with independent authenticated finality; preserve claim 889",
    "Witness fresh quiesced, checksummed backups of both settlement states/config/units",
    "Witness bounded two-service code-only rollback without consensus restart or state restore",
    "Independently prove same-height global assets, obligations, overlaps and pending fee/gas solvency",
    "Only then issue a separate exact-scoped paired code-cutover permit; Satchel still requires its own certification",
)

class BoardFailure(ValueError):
    pass


def summarize(checklist: dict, triage: dict | None, *,
              observed_at: datetime | None = None, checklist_sha256: str) -> dict:
    """Pure redacted projection. Presence of evidence is never authority."""
    at = observed_at or datetime.now(timezone.utc)
    if at.tzinfo is None or not re.fullmatch(r"[0-9a-f]{64}", checklist_sha256):
        raise BoardFailure("INVALID_REPORT_PROVENANCE")
    if not isinstance(checklist, dict) or checklist.get("schema") != SCHEMA or (
        checklist.get("overall_status") != "HOLD"
        or checklist.get("financial_release_authorized") is not False
        or checklist.get("global_liability_upper_bound_uwolo", "missing") is not None
    ):
        raise BoardFailure("UNCERTIFIED_CHECKLIST")
    controls = checklist.get("controls")
    if not isinstance(controls, dict) or set(controls) != CONTROLS:
        raise BoardFailure("INCOMPLETE_SIX_CONTROL_SET")
    matrix = []
    for name in sorted(CONTROLS):
        record = controls[name]
        if not isinstance(record, dict) or record.get("status") not in {"BLOCKED", "UNKNOWN"}:
            raise BoardFailure("UNWITNESSED_STATUS_ESCALATION")
        if not isinstance(record.get("unknowns"), list) or not record["unknowns"]:
            raise BoardFailure("UNRESOLVED_EVIDENCE_ERASED")
        # Never print arbitrary descriptions/paths from untrusted evidence
        matrix.append({"control": name, "status": record["status"],
                       "unknownCount": len(record["unknowns"]),
                       "independentlyWitnessed": False})
    candidate = checklist.get("exact_historical_candidate")
    old = checklist.get("live_settlement_revision")
    if (not isinstance(candidate, dict)
            or not isinstance(candidate.get("revision"), str)
            or not SHA40.fullmatch(candidate["revision"])
            or not isinstance(old, str) or not SHA40.fullmatch(old)):
        raise BoardFailure("SOURCE_IDENTITY_UNKNOWN")
    producer = {"triageAvailable": False, "fresh": False,
                "unitsObserved": None, "activeObserved": None,
                "ownersReviewRequired": None, "unknownOwnerUnits": None,
                "units": []}
    if triage is not None:
        if (not isinstance(triage, dict) or triage.get("schema") != TRIAGE_SCHEMA
                or triage.get("mode") != "READ_ONLY_NONAUTHORIZING"
                or triage.get("status") != "HOLD"
                or triage.get("producerIsolationProven") is not False
                or triage.get("financialReleaseAuthorized") is not False
                or triage.get("productionMutated") is not False):
            raise BoardFailure("UNTRUSTED_PRODUCER_TRIAGE")
        units = triage.get("unitOwnerReview")
        counts = triage.get("counts")
        if (not isinstance(units, list) or len(units) > MAX_REVIEW_UNITS
                or not isinstance(counts, dict)):
            raise BoardFailure("INVALID_PRODUCER_INVENTORY")
        safe_units = []
        seen = set()
        for unit in units:
            if not isinstance(unit, dict):
                raise BoardFailure("INVALID_PRODUCER_INVENTORY")
            name, who = unit.get("unit"), unit.get("owner")
            if (not isinstance(name, str) or not UNIT.fullmatch(name)
                    or name in seen or who not in OWNERS
                    or unit.get("reviewStatus") != "OWNER_REVIEW_REQUIRED"
                    or unit.get("runtimeSignerProof") != "UNKNOWN"
                    or unit.get("activeObserved") not in {True, False, None}):
                raise BoardFailure("UNTRUSTED_PRODUCER_CLASSIFICATION")
            seen.add(name)
            safe_units.append({"unit": name, "reviewOwnerCategory": who,
                               "activeObserved": unit["activeObserved"],
                               "fenceAuthorized": False})
        numeric = ("unitsObserved", "activeObserved", "unknownOwnerUnits")
        if (any(type(counts.get(k)) is not int or not 0 <= counts[k] <= MAX_REVIEW_UNITS
                for k in numeric)
                or counts["unitsObserved"] != len(safe_units)
                or counts["activeObserved"] != sum(u["activeObserved"] is True for u in safe_units)
                or counts["unknownOwnerUnits"] != sum(u["reviewOwnerCategory"] == "UNKNOWN_OWNER"
                                                    for u in safe_units)):
            raise BoardFailure("PRODUCER_COUNTS_MISMATCH")
        producer = {"triageAvailable": True,
                    "fresh": triage.get("runtimeFresh") is True,
                    "unitsObserved": len(safe_units),
                    "activeObserved": counts["activeObserved"],
                    "unknownOwnerUnits": counts["unknownOwnerUnits"],
                    "ownersReviewRequired": len(safe_units),
                    "units": sorted(safe_units, key=lambda u: u["unit"])}
    return {
        "schema": "aoe2war.wolo.financial-maintenance-board.v1",
        "generatedAtUtc": at.astimezone(timezone.utc).isoformat(),
        "source": "CHECKSUMMED_REPOSITORY_OBSERVATIONS_NOT_LIVE_CHAIN_PROOF",
        "checklistSha256": checklist_sha256,
        "historicalCandidateRevision": candidate["revision"],
        "documentedOldSettlementRevision": old,
        "finance": {"state": "HOLD", "controls": matrix,
                    "globalLiabilityKnown": False,
                    "independentChainSolvencyProven": False,
                    "claim889DispositionProven": False},
        "producers": producer,
        "orderedOperatorWork": list(NEXT_BOUNDARIES),
        "ownerMaintenanceWillingnessIsNotCutoverPermit": True,
        "sourceRuntimeParityProven": False,
        "productionMutated": False,
        "financialProducersFenced": False,
        "financialReleaseAuthorized": False,
        "satchelCustodyAuthorized": False,
        "websiteReleaseAuthorized": False,
        "canIssueFinancialCutoverPermit": False,
        "nextStep": "CLASSIFY_AND_WITNESS_CURRENT_FINANCIAL_PRODUCERS",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--triage", type=Path,
                        help="Optional SANITIZED local JSON from settlement_producer_owner_triage.py")
    args = parser.parse_args(argv)
    try:
        # Existing strict receipt checker authenticates all checked-in hashes,
        # enforces the original HOLD, six exact controls and historical source.
        audit_historical_evidence(args.root)
        raw = safe_read(args.root, INDEX)
        checklist = json_object(raw)
        triage = read_sanitized_packet(args.triage) if args.triage else None
        result = summarize(checklist, triage,
                           checklist_sha256=hashlib.sha256(raw).hexdigest())
    except (AuditFailure, BoardFailure, ValueError, OSError, RecursionError):
        print(json.dumps({"status": "STOP", "financialReleaseAuthorized": False,
                          "reason": "EVIDENCE_INCOMPLETE_OR_UNSAFE"}, sort_keys=True))
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 3  # Even perfect historical source coverage is NEVER live approval.


if __name__ == "__main__":
    raise SystemExit(main())

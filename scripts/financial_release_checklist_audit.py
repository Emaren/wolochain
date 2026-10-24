#!/usr/bin/env python3
"""Offline, non-authorizing audit of WoloChain's six-control release evidence.

This is a repository evidence integrity check, NOT a live release preflight.
No network, process inspection, transaction, signer, state or keyring access.
An operator-supplied expected SHA is only a consistency comparison, not an
authenticated statement of the running revision or owner approval.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import stat
import sys

SCHEMA = "aoe2war.wolo.financial-release-checklist.v1"
INDEX = "docs/settlement-contracts/financial-release-checklist.json"
EVIDENCE_DIR = "docs/settlement-contracts/financial-release-evidence-20261018"
CONTROLS = frozenset({
    "hd_de_producers_isolated",
    "inflight_requests_and_accepted_tx_reconciled",
    "claim_889_liability_preserved_and_release_reviewed",
    "fresh_quiesced_backup_hash_verified",
    "reviewed_code_only_rollback_rehearsed",
    "bank_solvent_and_independently_checked",
})
FALSE_FLAGS = (
    "independent_consensus_authentication_proven",
    "complete_financial_producer_inventory_proven",
    "financial_drain_certified",
    "claim_889_reconciled",
    "fresh_quiesced_snapshot_certified",
    "live_rollback_certified",
    "financial_release_authorized",
    "production_mutated",
)
SHA = re.compile(r"[0-9a-f]{40}\Z")
DIGEST = re.compile(r"[0-9a-f]{64}\Z")
MAX_BYTES = 2 * 1024 * 1024


class AuditFailure(ValueError):
    """Non-sensitive, stable reason for rejecting a checklist."""


def reject(reason: str) -> None:
    raise AuditFailure(reason)


def pairs_unique(pairs):
    output = {}
    for key, value in pairs:
        if key in output:
            reject("DUPLICATE_JSON_KEY")
        output[key] = value
    return output


def safe_read(root: Path, relative: str) -> bytes:
    parts = Path(relative).parts
    if not parts or Path(relative).is_absolute() or any(x in {".", ".."} for x in parts):
        reject("UNSAFE_EVIDENCE_PATH")
    current = root
    for i, component in enumerate(parts):
        current = current / component
        try:
            metadata = current.lstat()
        except OSError:
            reject("EVIDENCE_UNAVAILABLE")
        if stat.S_ISLNK(metadata.st_mode):
            reject("SYMLINK_EVIDENCE")
        if i < len(parts) - 1 and not stat.S_ISDIR(metadata.st_mode):
            reject("UNSAFE_EVIDENCE_PATH")
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > MAX_BYTES:
        reject("INVALID_EVIDENCE_FILE")
    try:
        with current.open("rb") as stream:
            raw = stream.read(MAX_BYTES + 1)
    except OSError:
        reject("EVIDENCE_UNAVAILABLE")
    if len(raw) > MAX_BYTES:
        reject("EVIDENCE_TOO_LARGE")
    return raw


def json_object(raw: bytes) -> dict:
    try:
        result = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=pairs_unique,
            parse_constant=lambda _: reject("NONFINITE_JSON"),
        )
    except AuditFailure:
        raise
    except (ValueError, UnicodeError, RecursionError):
        reject("INVALID_JSON")
    if not isinstance(result, dict):
        reject("INVALID_JSON_ROOT")
    return result


def audit(root: Path, expected_implementation: str | None = None) -> dict:
    checklist = json_object(safe_read(root, INDEX))
    if checklist.get("schema") != SCHEMA:
        reject("CHECKLIST_SCHEMA_MISMATCH")
    if checklist.get("overall_status") != "HOLD":
        reject("RELEASE_HOLD_REMOVED")
    if checklist.get("financial_release_authorized") is not False:
        reject("RELEASE_AUTHORITY_NOT_FALSE")
    for name in FALSE_FLAGS:
        if checklist.get(name) is not False:
            reject("UNATTESTED_CONTROL_FLAG")
    if checklist.get("global_liability_upper_bound_uwolo", "INVALID") is not None:
        reject("GLOBAL_LIABILITY_UNPROVEN")
    if checklist.get("global_liability_bound") != "UNBOUNDED_NOT_PROVEN":
        reject("GLOBAL_LIABILITY_BOUND_MISREPRESENTED")
    if checklist.get("custody_capability") != "UNAVAILABLE":
        reject("CUSTODY_HOLD_REMOVED")
    if checklist.get("chain_evidence") != "NONCREDITING":
        reject("CHAIN_EVIDENCE_ESCALATED")
    if checklist.get("website", {}).get("status") != "CERTIFIED_INDEPENDENT_APP_RELEASE":
        reject("WEBSITE_EVIDENCE_CHANGED")
    controls = checklist.get("controls")
    if not isinstance(controls, dict) or set(controls) != CONTROLS:
        reject("SIX_CONTROL_SET_MISMATCH")
    inventory = checklist.get("evidence")
    if not isinstance(inventory, dict) or not inventory:
        reject("EVIDENCE_INVENTORY_MISSING")
    for name, control in controls.items():
        if not isinstance(control, dict) or control.get("status") not in {"BLOCKED", "UNKNOWN"}:
            reject("UNATTESTED_CONTROL_PROMOTED")
        refs = control.get("evidence")
        if not isinstance(refs, list) or not refs or any(not isinstance(v, str) or v not in inventory for v in refs):
            reject("CONTROL_EVIDENCE_MISSING")
        if not isinstance(control.get("unknowns"), list) or not control["unknowns"]:
            reject("CONTROL_UNCERTAINTY_ERASED")
    for name, record in inventory.items():
        if not isinstance(name, str) or name in {".", ".."} or "/" in name or "\\" in name:
            reject("UNSAFE_EVIDENCE_NAME")
        if not isinstance(record, dict) or record.get("path") != EVIDENCE_DIR + "/" + name:
            reject("EVIDENCE_PATH_MISMATCH")
        declared = record.get("sha256")
        if not isinstance(declared, str) or not DIGEST.fullmatch(declared):
            reject("EVIDENCE_DIGEST_INVALID")
        actual = hashlib.sha256(safe_read(root, record["path"])).hexdigest()
        if actual != declared:
            reject("EVIDENCE_DIGEST_MISMATCH")
    candidate = checklist.get("exact_historical_candidate")
    if not isinstance(candidate, dict) or not isinstance(candidate.get("revision"), str) or not SHA.fullmatch(candidate["revision"]):
        reject("CANDIDATE_REVISION_INVALID")
    if not isinstance(candidate.get("binary_sha256"), str) or not DIGEST.fullmatch(candidate["binary_sha256"]):
        reject("CANDIDATE_BINARY_DIGEST_INVALID")
    live = checklist.get("live_settlement_revision")
    if not isinstance(live, str) or not SHA.fullmatch(live):
        reject("LIVE_REVISION_INVALID")
    if expected_implementation is not None:
        if not SHA.fullmatch(expected_implementation):
            reject("EXPECTED_BASELINE_INVALID")
        if candidate["revision"] != expected_implementation:
            reject("HISTORICAL_CANDIDATE_NOT_FEDERATED_BASELINE")
    return {
        "result": "VALIDATED_HOLD_ONLY",
        "financial_release_authorized": False,
        "live_attestation_performed": False,
        "independent_review_performed": False,
        "global_liability_bound": None,
        "control_count": len(controls),
        "evidence_count": len(inventory),
        "historical_candidate_revision": candidate["revision"],
        "documented_live_revision": live,
        "expected_implementation_revision": expected_implementation,
        "candidate_equals_expected": candidate["revision"] == expected_implementation if expected_implementation else None,
        "deployment_permitted": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--expected-implementation", help="Operator-supplied full 40-hex baseline; does not authenticate authority")
    args = parser.parse_args()
    try:
        result = audit(args.root, args.expected_implementation)
    except AuditFailure as exc:
        print(json.dumps({"result": "STOP", "reason": str(exc), "deployment_permitted": False,
                          "financial_release_authorized": False}, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())

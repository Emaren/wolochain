#!/usr/bin/env python3
"""Review-only, fail-closed three-phase Wolo financial maintenance evidence gate.

Never starts, stops, fences, dumps, restores, issues permits or consumes nonces.
This composes the *real* five-human Ed25519 verifier with strict phase lineage.
Passing review is NOT independent human enrollment or an authority to act.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import settlement_human_authority_verify as human

SCHEMA = "wolo.financial-maintenance-phase-review.v1"
EVIDENCE_SCHEMA = "wolo.financial-maintenance-phase-evidence.v1"
STATES = {
    "live_capture": "CAPTURE_PROPOSED",
    "offline_verify": "CAPTURE_SEALED_RESTORE_PROPOSED",
    "resume": "RESTORE_EVIDENCE_REVIEWED_RESUME_PROPOSED",
}
EVIDENCE_FIELDS = frozenset({
    "schema", "phase", "state", "source_commit", "scope_sha256",
    "host_identity_sha256", "capture_manifest_sha256", "fence_receipt_sha256",
    "restore_receipt_sha256", "previous_review_sha256",
    "writers_and_external_signers_independently_checked",
    "complete_hd_de_census_independently_checked",
    "bank_solvent_independently_checked",
    "automatic_resume_authorized", "financial_release_authorized",
})
REVIEW_FIELDS = frozenset({
    "schema", "phase", "state", "source_commit", "scope_sha256",
    "host_identity_sha256", "signed_packet_sha256", "evidence_sha256",
    "capture_manifest_sha256", "fence_receipt_sha256",
    "restore_receipt_sha256", "previous_review_sha256",
    "human_enrollment_independently_proven",
    "nonce_atomically_consumed", "production_action_authorized",
    "automatic_resume_authorized", "financial_release_authorized",
    "status",
})


def require(condition, reason):
    if not condition:
        raise human.Refusal(reason)


def digest(raw: bytes) -> str:
    return human.sha(raw)


def decode(raw: bytes, schema: str, keys: frozenset[str]):
    value = human.parse_json(raw)
    require(set(value) == keys and value["schema"] == schema, "CLOSED_SCHEMA_REQUIRED")
    require(human.canonical(value) == raw, "CANONICAL_EVIDENCE_REQUIRED")
    return value


def expected_sha(raw: bytes | None):
    return digest(raw) if raw is not None else None


def review(packet: dict, registry: dict, registry_raw: bytes, ledger: dict,
           expected: dict, evidence: bytes, procedure: bytes,
           *, capture: bytes | None = None, fence: bytes | None = None,
           restore: bytes | None = None, previous: bytes | None = None,
           now=None):
    """One snapshot-level gate: deterministic, no side effects, always NONAUTHORIZING."""
    signed = human.verify(packet, registry, registry_raw, ledger, expected,
                          evidence, procedure, capture=capture, fence=fence, now=now)
    require(signed["status"] == "CRYPTOGRAPHIC_EVIDENCE_VERIFIED_NONAUTHORIZING",
            "UNEXPECTED_CRYPTO_VERDICT")
    req = packet["request"]
    phase = req["phase"]
    e = decode(evidence, EVIDENCE_SCHEMA, EVIDENCE_FIELDS)
    require(e["phase"] == phase and e["state"] == STATES[phase],
            "PHASE_STATE_MISMATCH")
    for name, actual in (("source_commit", expected["source_commit"]),
                         ("scope_sha256", expected["scope"]),
                         ("host_identity_sha256", expected["host"]),
                         ("capture_manifest_sha256", expected_sha(capture)),
                         ("fence_receipt_sha256", expected_sha(fence)),
                         ("restore_receipt_sha256", expected_sha(restore)),
                         ("previous_review_sha256", expected_sha(previous))):
        require(e[name] == actual, "EVIDENCE_LINEAGE_MISMATCH")
    require(e["automatic_resume_authorized"] is False and
            e["financial_release_authorized"] is False,
            "FORBIDDEN_IMPLICIT_AUTHORITY")
    for flag in ("writers_and_external_signers_independently_checked",
                 "complete_hd_de_census_independently_checked",
                 "bank_solvent_independently_checked"):
        require(type(e[flag]) is bool, "ATTESTATION_TYPE_INVALID")

    if phase == "live_capture":
        require(all(x is None for x in (capture, fence, restore, previous)) and
                not e["complete_hd_de_census_independently_checked"] and
                not e["bank_solvent_independently_checked"],
                "LIVE_CAPTURE_MAY_NOT_PRECERTIFY_RECOVERY")
    else:
        require(capture is not None and fence is not None and previous is not None,
                "PRIOR_CAPTURE_AND_REVIEW_REQUIRED")
        prior = decode(previous, SCHEMA, REVIEW_FIELDS)
        required_phase = "live_capture" if phase == "offline_verify" else "offline_verify"
        require(prior["phase"] == required_phase and
                prior["source_commit"] == expected["source_commit"] and
                prior["scope_sha256"] == expected["scope"] and
                prior["host_identity_sha256"] == expected["host"] and
                prior["status"] == "REVIEWED_NONAUTHORIZING" and
                prior["production_action_authorized"] is False and
                prior["financial_release_authorized"] is False and
                prior["automatic_resume_authorized"] is False,
                "PRIOR_PHASE_NOT_TRUSTED")
        if phase == "offline_verify":
            require(restore is None and
                    prior["capture_manifest_sha256"] is None and
                    prior["fence_receipt_sha256"] is None,
                    "OFFLINE_MUST_FOLLOW_LIVE_PROPOSAL")
        else:
            require(restore is not None and
                    prior["capture_manifest_sha256"] == digest(capture) and
                    prior["fence_receipt_sha256"] == digest(fence) and
                    prior["restore_receipt_sha256"] is None and
                    all(e[x] is True for x in (
                        "writers_and_external_signers_independently_checked",
                        "complete_hd_de_census_independently_checked",
                        "bank_solvent_independently_checked")),
                    "RESUME_REVIEW_EVIDENCE_INCOMPLETE")

    result = {
        "schema": SCHEMA, "phase": phase, "state": STATES[phase],
        "source_commit": req["source_commit"], "scope_sha256": req["scope_sha256"],
        "host_identity_sha256": req["host_identity_sha256"],
        "signed_packet_sha256": digest(human.canonical(packet)),
        "evidence_sha256": digest(evidence),
        "capture_manifest_sha256": expected_sha(capture),
        "fence_receipt_sha256": expected_sha(fence),
        "restore_receipt_sha256": expected_sha(restore),
        "previous_review_sha256": expected_sha(previous),
        "human_enrollment_independently_proven": False,
        "nonce_atomically_consumed": False,
        "production_action_authorized": False,
        "automatic_resume_authorized": False,
        "financial_release_authorized": False,
        "status": "REVIEWED_NONAUTHORIZING",
    }
    require(set(result) == REVIEW_FIELDS, "INTERNAL_REVIEW_SCHEMA_DRIFT")
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for label in ("registry", "packet", "nonce-ledger", "evidence", "procedure"):
        parser.add_argument("--" + label, type=Path, required=True)
    for label in ("registry", "source", "scope", "host"):
        parser.add_argument("--expected-" + label + "-sha256", required=True)
    parser.add_argument("--expected-source-commit", required=True)
    for label in ("capture-manifest", "fence-receipt", "restore-receipt", "previous-review"):
        parser.add_argument("--" + label, type=Path)
    args = parser.parse_args(argv)
    try:
        expected = {k: getattr(args, "expected_" + k + "_sha256")
                    for k in ("registry", "source", "scope", "host")}
        expected["source_commit"] = args.expected_source_commit
        require(human.HEX40.fullmatch(expected["source_commit"]) and
                all(human.HEX64.fullmatch(expected[k])
                    for k in ("registry", "source", "scope", "host")),
                "UNTRUSTED_EXPECTED_VALUES")
        registry_raw = human.read_file(args.registry)
        result = review(
            human.parse_json(human.read_file(args.packet)),
            human.parse_json(registry_raw), registry_raw,
            human.parse_json(human.read_file(args.nonce_ledger)), expected,
            human.read_file(args.evidence), human.read_file(args.procedure),
            capture=human.read_file(args.capture_manifest) if args.capture_manifest else None,
            fence=human.read_file(args.fence_receipt) if args.fence_receipt else None,
            restore=human.read_file(args.restore_receipt) if args.restore_receipt else None,
            previous=human.read_file(args.previous_review) if args.previous_review else None,
        )
        print(human.canonical(result).decode("ascii"))
        return 3  # A passing review MUST NOT look like production execution success.
    except (human.Refusal, OSError, ValueError, TypeError, KeyError) as error:
        print("HOLD: " + (str(error) if isinstance(error, human.Refusal)
                          else "REVIEW_INPUT_UNAVAILABLE"), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

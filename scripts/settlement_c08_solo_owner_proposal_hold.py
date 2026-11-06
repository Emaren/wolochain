#!/usr/bin/env python3
"""Validate a PROPOSED single-human WOLO governance model, never an approval.

Offline and source-only. A valid result is HOLD (exit 3), NEVER operational
authority. This verifier is deliberately not wired into the 8094/8095 runtime.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys

SCHEMA = "wolo.solo-owner-centralized-governance-proposal.v1"
GATES = ["C01", "C02", "C03", "C04", "C05", "C06", "C07", "C08", "C09"]
REQUIRED = {
    "schema": SCHEMA,
    "status": "PROPOSED_NOT_RATIFIED",
    "chain_id": "wolo-1",
    "human_operator_count": 1,
    "custody_reserve_release_same_human": True,
    "independent_human_review_available": False,
    "independent_review_claimed": False,
    "ai_review_counts_as_human": False,
    "separate_owner_devices_count_as_independent_humans": False,
    "owner_authority_scope": "source-review-and-nonfinancial-engineering-only",
    "reviewed_runtime_solo_owner_funded_activation_supported": False,
    "financial_release_authorized": False,
    "funded_canary_max_uwolo": 0,
    "legacy_8092_fallback_allowed": False,
    "unknown_auto_retry_allowed": False,
    "historical_liabilities_waiver_allowed": False,
    "native_finality_required": True,
    "next_funded_permit_requires_fresh_exact_owner_signature": True,
    "new_permission_version_required": True,
    "old_five_human_permits_auto_convert": False,
    "offhost_one_use_nonce_witness_required": True,
    "public_control_disclosure_required": True,
    "first_canary_single_operation_only": True,
    "database_writer_fence_required": True,
    "independent_chain_proof_required": True,
    "independently_reproducible_common_height_solvency_required": True,
    "encrypted_offhost_backup_and_isolated_pair_restore_required": True,
    "active_8094_8095_allowed": False,
    "public_notice_min_seconds": 86400,
    "post_adoption_funded_permit_max_lifetime_seconds": 120,
    "required_formal_gates": GATES,
    "non_authorization_statement": (
        "This is a single-owner centralized governance proposal and never a financial permit."
    ),
}


class PolicyHold(ValueError):
    pass


def decode_unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise PolicyHold("DUPLICATE_POLICY_KEY")
        result[key] = value
    return result


def validate(source):
    if type(source) is not dict or set(source) != set(REQUIRED):
        raise PolicyHold("POLICY_FIELDS_UNRECOGNIZED_OR_MISSING")
    for key, expected in REQUIRED.items():
        actual = source[key]
        if type(actual) is not type(expected) or actual != expected:
            raise PolicyHold("POLICY_BOUNDARY_VIOLATION:" + key)
    # This is intentionally NEVER a bool grant or a viable runtime packet.
    return {
        "schema": "wolo.solo-owner-governance-review-held.v1",
        "status": "HOLD",
        "proposal_authenticated_as_non_authorizing": True,
        "centralized_one_human_disclosed": True,
        "actual_funded_runtime_activation_permit": False,
        "independent_human_review_asserted": False,
        "financial_release_authorized": False,
        "canary_transfer_authorized": False,
        "original_financial_constitution_replaced": False,
        "next_step": "separate reviewed implementation, real evidence, public disclosure and exact owner-signed permit",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    args = parser.parse_args(argv)
    try:
        p = args.path
        if p.is_symlink() or not p.is_file() or p.stat().st_size > 16384:
            raise PolicyHold("PROPOSAL_FILE_UNAVAILABLE")
        raw = p.read_bytes()
        policy = json.loads(raw, object_pairs_hook=decode_unique,
                            parse_constant=lambda _: (_ for _ in ()).throw(PolicyHold("NONFINITE")))
        report = validate(policy)
    except (PolicyHold, ValueError, OSError, UnicodeError) as exc:
        reason = str(exc) if isinstance(exc, PolicyHold) else "PROPOSAL_PARSE_UNAVAILABLE"
        print(json.dumps({"status": "STOP", "reason": reason,
                          "financial_release_authorized": False}, sort_keys=True))
        return 2
    print(json.dumps(report, sort_keys=True, indent=2))
    return 3


if __name__ == "__main__":
    sys.exit(main())

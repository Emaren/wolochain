#!/usr/bin/env python3
"""Offline C08/C09 exact single-canary owner signature review: always HOLD.

A real owner Ed25519 signature binds the EXACT new claim, recipient, amount,
fee, source, bank/chain root, restore, reviewer and one-use intent nonce.
It NEVER proves ratified governance, recipient checksum, bank authenticity,
unspent funds, an off-host nonce burn, or funded runtime authorization.

NO network, Cosmos keyring, signing, transfers, service management or SQL.
No transaction-specific operational permit is produced by this program.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import timedelta

import settlement_solo_owner_intent_review as owner

SCHEMA = "wolo.c09.solo-owner-exact-canary-intent.v2"
PACKET_SCHEMA = "wolo.c09.solo-owner-signed-exact-canary-intent.v2"
DOMAIN = b"AOE2WAR-WOLO-EXACT-SOLO-CANARY-V2\x00"
OUT_SCHEMA = "wolo.c09.single-owner-exact-canary-signature-held.v1"
SIGNED_KEYS = frozenset({
    "schema", "chain_id", "operation", "fresh_claim_id", "request_id",
    "recipient", "amount_uwolo", "fee_uwolo", "bank_height",
    "source_commit", "satchel_binary_sha256", "reviewer_binary_sha256",
    "consensus_header_root_sha256", "bank_root_sha256",
    "liability_root_sha256", "full_writer_fence_sha256",
    "coordinated_backup_sha256", "isolated_restore_sha256",
    "c01_c08_acceptance_bundle_sha256", "governance_ratification_sha256",
    "rollback_receipt_sha256", "nonce", "not_before", "expires_at",
    "legacy_fallback_allowed", "retry_on_unknown_allowed",
    "independent_human_review_claimed", "one_operation_only",
})
CANON_AMOUNT = re.compile(r"(?:0|[1-9][0-9]{0,18})\Z")
NEW_CLAIM = re.compile(r"fresh-c09-[a-f0-9]{32}\Z")
REQUEST_ID = re.compile(r"c09-[a-f0-9]{32}\Z")
# Syntax envelope only. Native chain checksum/address validation is NOT proven.
RECIPIENT_ENVELOPE = re.compile(r"wolo1[023456789acdefghjklmnpqrstuvwxyz]{20,88}\Z")


def amount(value: object, *, zero_allowed: bool) -> int:
    owner.require(type(value) is str and CANON_AMOUNT.fullmatch(value) is not None,
                  "C09_NONCANONICAL_AMOUNT")
    parsed = int(value)
    owner.require(parsed <= (1 << 63) - 1 and (zero_allowed or parsed > 0),
                  "C09_AMOUNT_OUT_OF_TECHNICAL_RANGE")
    return parsed


def validate_request(q: dict, now) -> None:
    owner.require(type(q) is dict and set(q) == SIGNED_KEYS
                  and q["schema"] == SCHEMA
                  and q["chain_id"] == "wolo-1"
                  and q["operation"] == "one-new-claim-canary-only",
                  "C09_SIGNED_FIELDS_OR_OPERATION_INVALID")
    owner.require(type(q["fresh_claim_id"]) is str
                  and NEW_CLAIM.fullmatch(q["fresh_claim_id"]) is not None
                  and type(q["request_id"]) is str
                  and REQUEST_ID.fullmatch(q["request_id"]) is not None
                  and q["fresh_claim_id"][10:] != q["request_id"][4:],
                  "C09_FRESH_CANARY_IDENTITY_INVALID")
    owner.require(type(q["recipient"]) is str
                  and RECIPIENT_ENVELOPE.fullmatch(q["recipient"]) is not None,
                  "C09_RECIPIENT_SYNTAX_UNQUALIFIED")
    amount(q["amount_uwolo"], zero_allowed=False)
    amount(q["fee_uwolo"], zero_allowed=True)
    owner.require(type(q["bank_height"]) is int and q["bank_height"] > 0,
                  "C09_BANK_HEIGHT_INVALID")
    owner.require(type(q["source_commit"]) is str
                  and owner.HEX40.fullmatch(q["source_commit"]) is not None
                  and q["source_commit"] != "0" * 40,
                  "C09_SOURCE_UNBOUND")
    root_names = (
        "satchel_binary_sha256", "reviewer_binary_sha256",
        "consensus_header_root_sha256", "bank_root_sha256",
        "liability_root_sha256", "full_writer_fence_sha256",
        "coordinated_backup_sha256", "isolated_restore_sha256",
        "c01_c08_acceptance_bundle_sha256", "governance_ratification_sha256",
        "rollback_receipt_sha256",
    )
    owner.require(all(owner.hex64(q[k]) for k in root_names),
                  "C09_PROOF_HASH_BINDING_INCOMPLETE")
    owner.require(
        q["legacy_fallback_allowed"] is False
        and q["retry_on_unknown_allowed"] is False
        and q["independent_human_review_claimed"] is False
        and q["one_operation_only"] is True,
        "C09_UNSAFE_PERMISSION_SEMANTICS",
    )
    owner.require(type(q["nonce"]) is str
                  and owner.HEX32.fullmatch(q["nonce"]) is not None
                  and q["nonce"] != "0" * 32, "C09_NONCE_INVALID")
    begin = owner.utc(q["not_before"])
    expires = owner.utc(q["expires_at"])
    owner.require(begin <= now < expires and timedelta() < expires - begin
                  <= timedelta(seconds=120), "C09_EXACT_CANARY_WINDOW_INVALID")


def review(enrollment_raw: bytes, packet_raw: bytes, *,
           pinned_enrollment_sha256: str, pinned_owner_der_sha256: str,
           pinned_source_commit: str, now=None) -> dict:
    owner.require(type(pinned_source_commit) is str
                  and owner.HEX40.fullmatch(pinned_source_commit) is not None
                  and pinned_source_commit != "0" * 40,
                  "C09_EXPECTED_SOURCE_PIN_INVALID")
    _, request, _ = owner.authenticate_owner(
        enrollment_raw, packet_raw,
        pinned_enrollment_sha256=pinned_enrollment_sha256,
        pinned_owner_der_sha256=pinned_owner_der_sha256,
        packet_schema=PACKET_SCHEMA, domain=DOMAIN,
        validate_request=validate_request, now=now,
    )
    owner.require(request["source_commit"] == pinned_source_commit,
                  "C09_EXPECTED_SOURCE_MISMATCH")
    # Never leak recipient, raw nonce or private key material in receipts.
    return {
        "schema": OUT_SCHEMA, "status": "CRYPTO_VALID_NONAUTHORIZING_HOLD",
        "request_commitment_sha256": hashlib.sha256(owner.canonical(request)).hexdigest(),
        "fresh_claim_commitment_sha256": hashlib.sha256(
            request["fresh_claim_id"].encode("ascii")).hexdigest(),
        "recipient_commitment_sha256": hashlib.sha256(
            request["recipient"].encode("ascii")).hexdigest(),
        "nonce_commitment_sha256": hashlib.sha256(
            request["nonce"].encode("ascii")).hexdigest(),
        "exact_transaction_fields_were_signed": True,
        "real_single_human_owner_signature_verified": True,
        "owner_enrollment_current_and_unrevoked_at_review": True,
        "owner_signature_alone_is_not_an_execution_permit": True,
        "economic_canary_limit_ratified": False,
        "recipient_chain_checksum_verified": False,
        "independent_chain_checkpoint_verified": False,
        "bank_and_liability_roots_independently_verified": False,
        "physical_c01_c08_gates_accepted": False,
        "offhost_one_use_nonce_consumed": False,
        "new_governance_policy_ratified_and_notice_elapsed": False,
        "independent_human_review_available": False,
        "funded_canary_permit_issued": False,
        "financial_release_authorized": False,
        "retry_authorized": False,
        "production_mutated": False,
        "next_evidence": "original C01-C08 physical receipts, separately adopted governance, fresh one-use offhost witness, independently proven bank/finality and reviewed financial runtime controller",
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--enrollment", required=True)
    parser.add_argument("--signed-intent", required=True)
    parser.add_argument("--pinned-enrollment-sha256", required=True)
    parser.add_argument("--pinned-owner-der-sha256", required=True)
    parser.add_argument("--pinned-source-commit", required=True)
    args = parser.parse_args(argv)
    try:
        report = review(
            owner.read_private(args.enrollment),
            owner.read_private(args.signed_intent),
            pinned_enrollment_sha256=args.pinned_enrollment_sha256,
            pinned_owner_der_sha256=args.pinned_owner_der_sha256,
            pinned_source_commit=args.pinned_source_commit,
        )
    except (owner.AuthorityHold, OSError, UnicodeError, ValueError) as exc:
        reason = str(exc) if type(exc) is owner.AuthorityHold else "C09_EVIDENCE_UNAVAILABLE"
        print(json.dumps({"schema": OUT_SCHEMA, "status": "STOP",
                          "reason": reason, "financial_release_authorized": False},
                         sort_keys=True))
        return 2
    print(json.dumps(report, sort_keys=True))
    return 3


if __name__ == "__main__":
    sys.exit(main())

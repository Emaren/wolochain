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
from datetime import datetime,timedelta,timezone
from pathlib import Path
import settlement_c08_governance_adoption_v2 as ratification
import settlement_c08_keychain_policy_adoption_v3 as keychain_v3

import settlement_solo_owner_intent_review as owner

SCHEMA = "wolo.c09.solo-owner-exact-canary-intent.v3"
PACKET_SCHEMA = "wolo.c09.solo-owner-signed-exact-canary-intent.v3"
DOMAIN = b"AOE2WAR-WOLO-EXACT-SOLO-CANARY-V3\x00"
OUT_SCHEMA = "wolo.c09.single-owner-exact-canary-signature-held.v2"
SIGNED_KEYS = frozenset({
    "schema", "chain_id", "operation", "fresh_claim_id", "native_claim_id", "request_id",
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
# App C02 new native claim sequence. Distinct from all historical INT claim IDs.
NATIVE_CLAIM = re.compile(r"9[0-9]{11}\Z")
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
    owner.require(type(q["native_claim_id"]) is str
                  and NATIVE_CLAIM.fullmatch(q["native_claim_id"]) is not None
                  and "900000000001" <= q["native_claim_id"] <= "999999999999",
                  "C09_NATIVE_CLAIM_NOT_FORWARD_ONLY_APP_ID")
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
        "native_claim_commitment_sha256": hashlib.sha256(
            request["native_claim_id"].encode("ascii")).hexdigest(),
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


def review_with_adopted_governance(enrollment_raw: bytes, packet_raw: bytes, *,
        pinned_enrollment_sha256: str, pinned_owner_der_sha256: str,
        pinned_source_commit: str, ratification_root: Path,
        governance_owner_public_pem: bytes, governance_source_repo: Path,
        notice_issue=None, notice_repository=None, now=None) -> dict:
    """Prove the original C08 adoption *and* signed C09 <= 1 WOLO.

    This is still NOT a runtime operation permit: C01-C07 and offhost nonce
    checks remain unproven. A missing/tampered adoption is a STOP, never an
    optional signed-C09 review override.
    """
    held = review(enrollment_raw, packet_raw,
        pinned_enrollment_sha256=pinned_enrollment_sha256,
        pinned_owner_der_sha256=pinned_owner_der_sha256,
        pinned_source_commit=pinned_source_commit, now=now)
    owner.require(held["status"] == "CRYPTO_VALID_NONAUTHORIZING_HOLD"
                  and held["financial_release_authorized"] is False,
                  "C09_CRYPTOGRAPHIC_BASE_UNEXPECTED")
    owner.require(pinned_owner_der_sha256 == ratification.OWNER_DER_SHA,
                  "C09_DIFFERENT_OWNER_FROM_ADOPTED_GOVERNANCE")
    try:
        adopted = ratification.inspect_adoption(root=ratification_root,
            public_pem=governance_owner_public_pem,
            repo=governance_source_repo,
            notice_issue=notice_issue,notice_repo=notice_repository)
    except (ratification.Hold, ratification.notice.NoticeStop, OSError,
            ValueError, TypeError, KeyError) as exc:
        raise owner.AuthorityHold("C09_RATIFIED_GOVERNANCE_NOT_AUTHENTICATED") from exc
    owner.require(adopted["status"] ==
                  "PASS_C08_GOVERNANCE_ADOPTION_PROOF_VERIFIED"
                  and adopted["financial_release_authorized"] is False
                  and adopted["funded_allowance_uwolo"] == 0,
                  "C09_GOVERNANCE_MUST_GRANT_NO_STANDING_SPEND")
    policy = ratification.strict(ratification.load_policy(governance_source_repo))
    limit = policy["separately_signed_future_c09_canary_ceiling_uwolo"]
    owner.require(type(limit) is int and limit == 1000000,
                  "C09_RATIFIED_MAXIMUM_NOT_ONE_WOLO")
    packet = owner.parse(packet_raw)
    request = packet["request"]
    owner.require(request["governance_ratification_sha256"] ==
                  adopted["receipt_sha256"],
                  "C09_SIGNED_GOVERNANCE_RECEIPT_BINDING_CHANGED")
    owner.require(amount(request["amount_uwolo"],zero_allowed=False) +
                  amount(request["fee_uwolo"],zero_allowed=True) <= limit,
                  "C09_SIGNED_CANARY_PLUS_FEE_EXCEEDS_ONE_WOLO")
    return dict(held,
        status="C09_SIGNED_INTENT_AND_C08_ADOPTION_VALID_FINANCIAL_RELEASE_HOLD",
        economic_canary_limit_ratified=True,
        new_governance_policy_ratified_and_notice_elapsed=True,
        c08_signed_ratification_authenticated=True,
        c08_ratification_receipt_sha256=adopted["receipt_sha256"],
        maximum_signed_canary_including_fee_uwolo=limit,
        physical_c01_c08_gates_accepted=False,
        offhost_one_use_nonce_consumed=False,
        funded_canary_permit_issued=False,
        financial_release_authorized=False)


def qualify_c09_request_against_keychain_governance_v3(request: dict, *,
        governance_root: Path, governance_public_x963: bytes,
        governance_source_repo: Path, now=None, comment=None,
        notice_issue=None, notice_repo=None) -> dict:
    """Strict actual C08 P-256 adoption prerequisite, NEVER a C09 permit.

    The *caller* must separately authenticate a fresh transaction-specific
    C09 owner signature. This proof alone is not signer/recipient/bank proof.
    It does not equate the new Keychain C08 identity to the historical
    Ed25519 direction-only key.
    """
    now=now or datetime.now(timezone.utc)
    validate_request(request,now)
    try:
        state=keychain_v3.adopted(governance_root,governance_source_repo,
            governance_public_x963,now=now,comment=comment,
            issue=notice_issue,repo_info=notice_repo)
    except (keychain_v3.Hold,keychain_v3.old.Hold,
            keychain_v3.notice.NoticeStop,OSError,ValueError,
            KeyError,TypeError) as exc:
        raise owner.AuthorityHold("C09_C08_V3_SIGNED_ADOPTION_UNAVAILABLE") from exc
    owner.require(state["status"]==
                  "PASS_C08_KEYCHAIN_GOVERNANCE_OWNER_ADOPTION_VERIFIED"
                  and state["financial_release_authorized"] is False
                  and state["standing_funded_allowance_uwolo"]==0,
                  "C09_C08_V3_ZERO_CURRENT_PERMISSION_REQUIRED")
    owner.require(type(state["future_c09_canary_ceiling_uwolo"]) is int
                  and state["future_c09_canary_ceiling_uwolo"]==1000000,
                  "C09_C08_V3_MAXIMUM_ONE_WOLO_REQUIRED")
    owner.require(request["governance_ratification_sha256"]==
                  state["receipt_sha256"],
                  "C09_C08_V3_SIGNED_RECEIPT_SHA_MISMATCH")
    limit=state["future_c09_canary_ceiling_uwolo"]
    owner.require(amount(request["amount_uwolo"],zero_allowed=False)+
                  amount(request["fee_uwolo"],zero_allowed=True)<=limit,
                  "C09_C08_V3_AMOUNT_PLUS_FEE_OVER_ONE_WOLO")
    return {
      "schema":"wolo.c09.c08-keychain-v3-policy-proof-only.v1",
      "status":"C09_C08_V3_GOVERNANCE_PROOF_VALID_EXECUTION_HOLD",
      "c08_adoption_receipt_sha256":state["receipt_sha256"],
      "future_maximum_amount_including_fee_uwolo":limit,
      "original_ed25519_key_falsely_reused":False,
      "new_keychain_v3_c08_governance_authenticated":True,
      "transaction_specific_owner_signature_proven_by_this_method":False,
      "offhost_one_use_nonce_consumed":False,
      "all_c01_c07_gates_accepted":False,
      "financial_release_authorized":False
    }


def review_with_keychain_governance_v3(enrollment_raw: bytes,packet_raw: bytes, *,
        pinned_enrollment_sha256: str,pinned_owner_der_sha256: str,
        pinned_source_commit: str,governance_root: Path,
        governance_public_x963: bytes,governance_source_repo: Path,
        now=None,comment=None,notice_issue=None,notice_repo=None) -> dict:
    """Real signed C09 request plus independently adopted C08 P-256 receipt.

    The signing C09 key is verified under its *own* enrolled Ed25519
    contract; no claim that it is the same as the distinct C08 P-256 key.
    Still no permit to broadcast, retry, credit or debit.
    """
    held=review(enrollment_raw,packet_raw,
        pinned_enrollment_sha256=pinned_enrollment_sha256,
        pinned_owner_der_sha256=pinned_owner_der_sha256,
        pinned_source_commit=pinned_source_commit,now=now)
    owner.require(held["status"]=="CRYPTO_VALID_NONAUTHORIZING_HOLD"
                  and held["financial_release_authorized"] is False,
                  "C09_BASE_SIGNED_INTENT_NOT_QUALIFIED")
    packet=owner.parse(packet_raw)
    proof=qualify_c09_request_against_keychain_governance_v3(
        packet["request"],governance_root=governance_root,
        governance_public_x963=governance_public_x963,
        governance_source_repo=governance_source_repo,
        now=now,comment=comment,notice_issue=notice_issue,notice_repo=notice_repo)
    return dict(held,
        status="C09_SIGNED_INTENT_PLUS_C08_KEYCHAIN_V3_VALID_FINANCIAL_HOLD",
        economic_canary_limit_ratified=True,
        new_governance_policy_ratified_and_notice_elapsed=True,
        c08_signed_ratification_authenticated=True,
        c08_ratification_receipt_sha256=proof["c08_adoption_receipt_sha256"],
        maximum_signed_canary_including_fee_uwolo=1000000,
        owner_identity_migration_not_old_key_cross_signature=True,
        physical_c01_c08_gates_accepted=False,
        funded_canary_permit_issued=False,
        financial_release_authorized=False)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--enrollment", required=True)
    parser.add_argument("--signed-intent", required=True)
    parser.add_argument("--pinned-enrollment-sha256", required=True)
    parser.add_argument("--pinned-owner-der-sha256", required=True)
    parser.add_argument("--pinned-source-commit", required=True)
    parser.add_argument("--c08-adopted-owner-root",type=Path)
    parser.add_argument("--c08-owner-public-key",type=Path)
    parser.add_argument("--c08-governance-source-repo",type=Path,
                        default=Path(__file__).resolve().parents[1])
    parser.add_argument("--c08-keychain-v3-owner-root",type=Path)
    parser.add_argument("--c08-keychain-v3-owner-public-x963",type=Path)
    args = parser.parse_args(argv)
    try:
        verified_inputs=dict(
            pinned_enrollment_sha256=args.pinned_enrollment_sha256,
            pinned_owner_der_sha256=args.pinned_owner_der_sha256,
            pinned_source_commit=args.pinned_source_commit)
        enrollment=owner.read_private(args.enrollment)
        packet=owner.read_private(args.signed_intent)
        if (args.c08_adopted_owner_root is None) != (
                args.c08_owner_public_key is None):
            raise owner.AuthorityHold("C09_C08_RATIFICATION_ARGUMENTS_INCOMPLETE")
        if (args.c08_keychain_v3_owner_root is None) != (
                args.c08_keychain_v3_owner_public_x963 is None):
            raise owner.AuthorityHold("C09_C08_V3_SIGNER_POINTERS_INCOMPLETE")
        if args.c08_keychain_v3_owner_root is not None and (
                args.c08_adopted_owner_root is not None or
                args.c08_owner_public_key is not None):
            raise owner.AuthorityHold("C09_TWO_INCOMPATIBLE_GOVERNANCE_MODES")
        if args.c08_keychain_v3_owner_root is not None:
            report=review_with_keychain_governance_v3(enrollment,packet,
                **verified_inputs,
                governance_root=args.c08_keychain_v3_owner_root,
                governance_public_x963=owner.read_private(
                    args.c08_keychain_v3_owner_public_x963),
                governance_source_repo=args.c08_governance_source_repo)
        elif args.c08_adopted_owner_root is None:
            report=review(enrollment,packet,**verified_inputs)
        else:
            report=review_with_adopted_governance(enrollment,packet,
                **verified_inputs,
                ratification_root=args.c08_adopted_owner_root,
                governance_owner_public_pem=owner.read_private(
                    args.c08_owner_public_key),
                governance_source_repo=args.c08_governance_source_repo)
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

#!/usr/bin/env python3
"""C08 read-only proof of the EXISTING Nov 7 owner-device direction.

The historical device signature approves only the direction of centralized
governance. It NEVER ratifies the new funded runtime or signs a C09 transfer.
No private key, Keychain, database, RPC, network or service mutation.
"""
from __future__ import annotations

import base64
import binascii
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile

import settlement_c08_solo_owner_proposal_hold as proposed

SCHEMA = "wolo.c08.existing-device-owner-direction-readonly-hold.v1"
DIRECTION_SCHEMA = "wolo.single-human-device-governance-signed-direction.v2"
DOMAIN = b"AOE2WAR-WOLO-SINGLE-HUMAN-NONFINANCIAL-GOVERNANCE-V2\x00"
POLICY_FILE = "docs/settlement-contracts/solo-owner-governance-proposal-20261106.json"
PINNED_PACKET_SHA = "3951e77f153e9a7b9ca27fa17548d67521cd55cc61489b5b612d0ecde843aca4"
PINNED_POLICY_SHA = "c7b40397dc4d5a182f8826897f72a1a7392e7ac0c169e9329bfc46c19a7ef6c6"
PINNED_PUBLIC_DER_SHA = "00d08c27271cf484f684059e83478d9522765c374101d5c4e8ed29e266e500ed"
PINNED_DIRECTION_SOURCE = "e4cbd15d40f750f50cd92aeb71e78d69ddad2c6a"
PINNED_ISSUED_UTC = "2026-11-07T10:10:27Z"
REQUEST_KEYS = frozenset({
    "schema", "chain_id", "purpose", "source_commit",
    "source_proposal_sha256", "nonce", "device_governance_public_key_der_sha256",
    "utc", "single_human_owner", "custodian_reserve_reviewer_approver_same_human",
    "independent_human_review_available", "independent_human_review_claimed",
    "technical_custody_reviewer_keys_remain_distinct",
    "public_notice_min_seconds",
    "c03_writer_fence_c06_backup_c07_restore_required",
    "c04_unknown_payout_frozen_pending_proof",
    "c05_authenticated_common_height_bank_proof_required",
    "real_complete_liabilities_and_reserves_required",
    "c08_one_use_offhost_witness_required",
    "c09_separate_human_confirmed_transaction_signature_required",
    "legacy_8092_fallback_allowed",
    "funded_canary_max_uwolo",
    "governance_implementation_source_reviewed",
    "owner_interactive_signature_confirmed_this_execution",
    "financial_release_authorized",
})

class Stop(ValueError):
    pass

def need(ok, reason):
    if not ok:
        raise Stop(reason)

def unique_pairs(pairs):
    d = {}
    for k, v in pairs:
        need(k not in d, "DUPLICATE_JSON_PROPERTY")
        d[k] = v
    return d

def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()

def parse_json(raw, max_size):
    need(type(raw) is bytes and 100 <= len(raw) <= max_size, "INVALID_SOURCE_SIZE")
    try:
        return json.loads(raw, object_pairs_hook=unique_pairs,
                          parse_float=lambda _: need(False, "FLOAT_FORBIDDEN"),
                          parse_constant=lambda _: need(False, "NONFINITE_FORBIDDEN"))
    except (ValueError, UnicodeError, RecursionError) as e:
        raise Stop("INVALID_SOURCE_JSON") from e

def verify_existing_direction(direction_raw, policy_raw):
    need(hashlib.sha256(direction_raw).hexdigest() == PINNED_PACKET_SHA,
         "NOV7_DEVICE_DIRECTION_HASH_CHANGED")
    need(hashlib.sha256(policy_raw).hexdigest() == PINNED_POLICY_SHA,
         "SOURCE_POLICY_HASH_CHANGED")
    policy = parse_json(policy_raw, 32768)
    need(type(policy) is dict and policy.get("status") == "PROPOSED_NOT_RATIFIED",
         "POLICY_ALREADY_RATIFIED_OR_CHANGED")
    held = proposed.validate(policy)
    need(held.get("status") == "HOLD"
         and held.get("actual_funded_runtime_activation_permit") is False,
         "POLICY_NONAUTHORIZING_PROOF_CHANGED")
    packet = parse_json(direction_raw, 8192)
    need(type(packet) is dict and set(packet) ==
         {"schema", "request", "signature_b64", "public_key_pem",
          "message_sha256", "device_signature_verified",
          "financial_release_authorized"}
         and packet["schema"] == DIRECTION_SCHEMA
         and packet["device_signature_verified"] is True
         and packet["financial_release_authorized"] is False,
         "DIRECTION_HEADER_OR_RELEASE_SCOPE_INVALID")
    req = packet["request"]
    need(type(req) is dict and set(req) == REQUEST_KEYS
         and req["schema"] == "wolo.single-human-device-governance-direction.v2"
         and req["chain_id"] == "wolo-1"
         and req["purpose"] ==
         "DEVICE_GOVERNANCE_DIRECTION_ONLY_NO_FUNDS_NO_FINANCIAL_PERMIT"
         and req["source_commit"] == PINNED_DIRECTION_SOURCE
         and req["source_proposal_sha256"] == PINNED_POLICY_SHA
         and req["utc"] == PINNED_ISSUED_UTC,
         "SIGNATURE_DIRECTION_SOURCE_OR_IDENTITY_CHANGED")
    flags_true = (
        "single_human_owner",
        "custodian_reserve_reviewer_approver_same_human",
        "technical_custody_reviewer_keys_remain_distinct",
        "c03_writer_fence_c06_backup_c07_restore_required",
        "c04_unknown_payout_frozen_pending_proof",
        "c05_authenticated_common_height_bank_proof_required",
        "real_complete_liabilities_and_reserves_required",
        "c08_one_use_offhost_witness_required",
        "c09_separate_human_confirmed_transaction_signature_required",
    )
    flags_false = (
        "independent_human_review_available",
        "independent_human_review_claimed",
        "legacy_8092_fallback_allowed",
        "governance_implementation_source_reviewed",
        "owner_interactive_signature_confirmed_this_execution",
        "financial_release_authorized",
    )
    need(all(req[x] is True for x in flags_true) and
         all(req[x] is False for x in flags_false) and
         type(req["public_notice_min_seconds"]) is int and
         req["public_notice_min_seconds"] == 86400 and
         type(req["funded_canary_max_uwolo"]) is int and
         req["funded_canary_max_uwolo"] == 0 and
         type(req["nonce"]) is str and
         re.fullmatch(r"[0-9a-f]{64}", req["nonce"]) is not None and
         req["nonce"] != "0"*64,
         "CENTRALIZED_POLICY_OR_FINANCIAL_HOLD_FIELDS_INVALID")
    pem = packet["public_key_pem"]
    need(type(pem) is str and len(pem) < 2048 and
         pem.startswith("-----BEGIN PUBLIC KEY-----") and
         pem.rstrip().endswith("-----END PUBLIC KEY-----"),
         "PUBLIC_KEY_PEM_INVALID")
    need(type(packet["message_sha256"]) is str and
         re.fullmatch(r"[a-f0-9]{64}", packet["message_sha256"]) is not None,
         "SIGNED_MESSAGE_HASH_MISSING")
    message = DOMAIN + canonical(req)
    need(hashlib.sha256(message).hexdigest() == packet["message_sha256"],
         "SIGNED_MESSAGE_MISMATCH")
    need(type(packet["signature_b64"]) is str and
         len(packet["signature_b64"]) <= 128, "INVALID_ED25519_SIGNATURE")
    try:
        signature = base64.b64decode(packet["signature_b64"], validate=True)
    except (ValueError, binascii.Error) as e:
        raise Stop("INVALID_SIGNATURE_ENCODING") from e
    need(len(signature) == 64, "ED25519_SIGNATURE_LENGTH")
    with tempfile.TemporaryDirectory(prefix="wolo-c08-direction-verification-") as tmp:
        p = Path(tmp)
        for name, data in (("public.pem", pem.encode()),
                           ("message.bin", message), ("signature.bin", signature)):
            f = p / name
            f.write_bytes(data)
            f.chmod(0o600)
        der = subprocess.run(
            ["openssl", "pkey", "-pubin", "-in", str(p/"public.pem"),
             "-outform", "DER"], capture_output=True, check=True, timeout=5).stdout
        need(hashlib.sha256(der).hexdigest() == PINNED_PUBLIC_DER_SHA
             and req["device_governance_public_key_der_sha256"] ==
             PINNED_PUBLIC_DER_SHA, "PUBLIC_KEY_DER_ANCHOR_CHANGED")
        verify = subprocess.run(
            ["openssl", "pkeyutl", "-verify", "-pubin", "-rawin",
             "-inkey", str(p/"public.pem"), "-in", str(p/"message.bin"),
             "-sigfile", str(p/"signature.bin")],
            capture_output=True, timeout=5)
        need(verify.returncode == 0, "ED25519_SIGNATURE_INVALID")

    return {
        "schema": SCHEMA,
        "status": "HOLD_C08_VERIFIED_20261107_OWNER_DIRECTION_NOT_POLICY_RATIFICATION",
        "existing_device_ed25519_signature_verified": True,
        "previous_signed_direction_sha256": PINNED_PACKET_SHA,
        "reviewed_source_proposal_sha256": PINNED_POLICY_SHA,
        "reviewed_device_public_der_sha256": PINNED_PUBLIC_DER_SHA,
        "original_signer_direction_source": PINNED_DIRECTION_SOURCE,
        "centralized_one_human_control_disclosed": True,
        "independent_human_review_claimed": False,
        "public_key_identity_independently_enrolled_for_funded_governance": False,
        "owner_approved_current_funded_governance_policy": False,
        "new_governance_runtime_implemented_and_ratified": False,
        "c08_new_time_bounded_ratification_signature_present": False,
        "c09_recipient_or_amount_or_permit_verified": False,
        "c09_funded_transaction_authorized": False,
        "legacy_8092_fallback_allowed": False,
        "financial_release_authorized": False,
        "production_mutated": False,
    }

def private_read(path):
    path = Path(path)
    st = path.lstat()
    need(stat.S_ISREG(st.st_mode) and st.st_nlink == 1 and
         (st.st_mode & 0o077) == 0 and st.st_size <= 8192,
         "PRIVATE_DIRECTION_FILE_REQUIRED")
    return path.read_bytes()

def main():
    import argparse
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--owner-direction", required=True, type=Path)
    args = p.parse_args()
    try:
        policy = (Path(__file__).resolve().parents[1] / POLICY_FILE).read_bytes()
        result = verify_existing_direction(private_read(args.owner_direction), policy)
    except (Stop, proposed.PolicyHold, OSError, subprocess.SubprocessError,
            UnicodeError, ValueError, KeyError, TypeError):
        print(json.dumps({"schema": SCHEMA, "status": "STOP_C08_OWNER_DIRECTION_NOT_VERIFIED",
                          "financial_release_authorized": False,
                          "production_mutated": False}, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 3

if __name__ == "__main__":
    sys.exit(main())

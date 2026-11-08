#!/usr/bin/env python3
"""C08: bind mature PUBLIC notice + exact solo-owner PROPOSAL + real owner intent.

SOURCE REVIEW ONLY: A valid owner Ed25519 signature is not policy ratification,
native custody authority, an independent human reviewer, or a WOLO permit.
No keys generated, no signatures created, no RPC, DB, HTTP listener or payment.
Offline review can use supplied authenticated GitHub notice objects in tests;
CLI performs read-only public GitHub API fetch of issue #184.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

import settlement_c08_solo_owner_proposal_hold as proposal
import settlement_solo_owner_intent_review as solo
import settlement_solo_owner_public_notice_hold as notice

SCHEMA = "wolo.c08.owner-signed-policy-ratification-intent.v1"
PACKET = "wolo.c08.signed-policy-ratification-intent.v1"
DOMAIN = b"AOE2WAR-WOLO-C08-OWNER-RATIFICATION-INTENT-V1\x00"
REPORT = "wolo.c08.owner-ratification-cryptographic-review-hardhold.v1"
HEX40 = re.compile(r"[a-f0-9]{40}\Z")
NONCE = re.compile(r"[a-f0-9]{32}\Z")
POLICY_RELATIVE = (
    "docs/settlement-contracts/solo-owner-governance-proposal-20261106.json"
)
REQUEST_FIELDS = frozenset({
    "schema", "chain_id", "source_commit", "policy_sha256",
    "public_notice_sha256", "public_notice_uri", "public_notice_not_before",
    "approval_scope", "human_operator_count", "independent_human_review_claimed",
    "new_permission_version_required", "allow_legacy_8092_fallback",
    "historical_liabilities_waived", "funded_limit_uwolo",
    "c09_transaction_permit_present", "nonce", "not_before", "expires_at",
})
APPROVAL_SCOPE = "review-centralized-one-human-policy-only"

class Stop(ValueError):
    pass

def need(condition, reason):
    if not condition:
        raise Stop(reason)

def load_policy(raw):
    need(type(raw) is bytes and 1000 <= len(raw) <= 32768,
         "C08_POLICY_SOURCE_SIZE_INVALID")
    try:
        document = json.loads(raw, object_pairs_hook=solo.unique,
                              parse_float=lambda _: need(False, "C08_FLOAT_REJECTED"),
                              parse_constant=lambda _: need(False, "C08_NONFINITE_REJECTED"))
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise Stop("C08_POLICY_JSON_INVALID") from exc
    need(isinstance(document, dict), "C08_POLICY_OBJECT_REQUIRED")
    try:
        held = proposal.validate(document)
    except proposal.PolicyHold as exc:
        raise Stop("C08_POLICY_SOURCE_PROPOSAL_DRIFT") from exc
    need(held["status"] == "HOLD"
         and held["actual_funded_runtime_activation_permit"] is False
         and held["centralized_one_human_disclosed"] is True
         and held["independent_human_review_asserted"] is False,
         "C08_PROPOSED_POLICY_NOT_SOURCE_QUALIFIED")
    return document, hashlib.sha256(raw).hexdigest()

def validate_ratification_request(request, now, *, policy_sha):
    need(type(request) is dict and set(request)==REQUEST_FIELDS
         and request["schema"]==SCHEMA
         and request["chain_id"]=="wolo-1", "C08_RATIFICATION_DOMAIN_OR_FIELDS")
    need(type(request["source_commit"]) is str
         and HEX40.fullmatch(request["source_commit"]) is not None,
         "C08_SOURCE_COMMIT_UNPINNED")
    need(type(request["policy_sha256"]) is str
         and request["policy_sha256"]==policy_sha,
         "C08_SIGNED_POLICY_SHA_MISMATCH")
    need(request["public_notice_sha256"] == notice.EXACT_PUBLIC_BODY_SHA256
         and request["public_notice_uri"] == notice.ISSUE_URL
         and request["public_notice_not_before"] == notice.EARLIEST_UTC,
         "C08_SIGNED_PUBLIC_NOTICE_IDENTITY_DRIFT")
    must={
        "approval_scope":APPROVAL_SCOPE,
        "human_operator_count":1,
        "independent_human_review_claimed":False,
        "new_permission_version_required":True,
        "allow_legacy_8092_fallback":False,
        "historical_liabilities_waived":False,
        "funded_limit_uwolo":0,
        "c09_transaction_permit_present":False,
    }
    for key,expected in must.items():
        need(type(request[key]) is type(expected) and request[key]==expected,
             "C08_SIGNED_REQUEST_UNSAFE_SCOPE_"+key.upper())
    need(type(request["nonce"]) is str
         and NONCE.fullmatch(request["nonce"]) is not None
         and request["nonce"] != "0"*32, "C08_NONCE_NOT_UNIQUE_FORM")
    begin,expiry=solo.utc(request["not_before"]),solo.utc(request["expires_at"])
    notice_time=solo.utc(notice.EARLIEST_UTC)
    need(begin>=notice_time and begin<=now<expiry
         and timedelta()<expiry-begin<=timedelta(seconds=120),
         "C08_RATIFICATION_INTENT_WINDOW_INVALID")

def review(*, policy_raw, notice_issue, notice_repository, owner_enrollment_raw,
           signed_packet_raw, pinned_enrollment_sha256, pinned_owner_der_sha256,
           now=None, openssl_path="openssl"):
    current=datetime.now(timezone.utc) if now is None else now
    need(type(current) is datetime and current.tzinfo is not None
         and current.utcoffset()==timedelta(),
         "C08_TRUSTED_UTC_REQUIRED")
    document, policy_sha = load_policy(policy_raw)
    try:
        notice_report=notice.inspect_notice(notice_issue,notice_repository,now=current)
    except notice.NoticeStop as exc:
        raise Stop("C08_PUBLIC_NOTICE_SOURCE_UNVERIFIED") from exc
    need(notice_report["status"]=="PASS_NOTICE_TIME_ONLY_ALL_FINANCIAL_GATES_HOLD"
         and notice_report["financial_release_authorized"] is False
         and notice_report["source_policy_ratified"] is False,
         "C08_PUBLIC_NOTICE_24H_NOT_AUTHENTICATED_MATURE")
    try:
        _,q,_=solo.authenticate_owner(
            owner_enrollment_raw,signed_packet_raw,
            pinned_enrollment_sha256=pinned_enrollment_sha256,
            pinned_owner_der_sha256=pinned_owner_der_sha256,
            packet_schema=PACKET,domain=DOMAIN,
            validate_request=lambda request,t: validate_ratification_request(
                request,t,policy_sha=policy_sha),
            now=current,openssl_path=openssl_path)
    except (solo.AuthorityHold, OSError) as exc:
        raise Stop("C08_OWNER_SIGNATURE_OR_ENROLLMENT_UNVERIFIED") from exc
    # Signature authenticity does NOT establish whether caller-supplied owner
    # public identity was independently enrolled or whether runtime supports
    # the proposed governance. No financial permit is issued or consumed.
    return {
        "schema":REPORT,
        "status":"HOLD_C08_SIGNATURE_VALID_RUNTIME_AND_AUTHORITY_NOT_RATIFIED",
        "public_notice_24h_verified":True,
        "proposal_exact_schema_validated":True,
        "proposed_policy_sha256":policy_sha,
        "owner_intent_signature_cryptographically_verified":True,
        "owner_enrollment_external_pin_independently_trusted":False,
        "signed_source_commit_independently_authenticated":False,
        "one_human_centralized_control_disclosed":True,
        "independent_human_reviewer_available":False,
        "intent_commitment_sha256":hashlib.sha256(solo.canonical(q)).hexdigest(),
        "one_use_offhost_nonce_consumed":False,
        "governance_runtime_policy_implemented_and_ratified":False,
        "old_five_human_permits_converted":False,
        "c03_fenced":False,"c04_finality_proven":False,"c05_solvency_proven":False,
        "c06_c07_same_capture_restored":False,
        "c09_exact_transfer_permit_present":False,
        "funded_8094_8095_authorized":False,
        "financial_release_authorized":False,
        "production_mutated":False,
    }

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--owner-enrollment",type=Path,required=True)
    p.add_argument("--owner-ratification-packet",type=Path,required=True)
    p.add_argument("--pinned-enrollment-sha256",required=True)
    p.add_argument("--pinned-owner-der-sha256",required=True)
    args=p.parse_args(argv)
    try:
        policy_path=Path(__file__).resolve().parents[1]/POLICY_RELATIVE
        policy_raw=policy_path.read_bytes()
        issue,repo=notice.live_fetch()
        result=review(
            policy_raw=policy_raw,notice_issue=issue,notice_repository=repo,
            owner_enrollment_raw=solo.read_private(args.owner_enrollment),
            signed_packet_raw=solo.read_private(args.owner_ratification_packet),
            pinned_enrollment_sha256=args.pinned_enrollment_sha256,
            pinned_owner_der_sha256=args.pinned_owner_der_sha256)
    except (Stop,solo.AuthorityHold,notice.NoticeStop,
            UnicodeError,OSError,ValueError,KeyError,TypeError,
            subprocess.TimeoutExpired):
        print(json.dumps({"schema":REPORT,"status":"STOP_C08_RATIFICATION_INTENT_UNVERIFIED",
                          "governance_runtime_policy_implemented_and_ratified":False,
                          "financial_release_authorized":False,
                          "production_mutated":False},sort_keys=True))
        return 2
    print(json.dumps(result,sort_keys=True,separators=(",",":")))
    return 3

if __name__=="__main__":
    sys.exit(main())

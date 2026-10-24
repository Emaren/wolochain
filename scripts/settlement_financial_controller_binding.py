#!/usr/bin/env python3
"""Actual Wolo maintenance CLI authority admission boundary, NOT a new verifier.

This is called from settlement_financial_maintenance.main under its root-only
global lock, BEFORE any production side effect. Reuses the existing five-human
Ed25519 verification, phased evidence review and O_EXCL nonce reservation.

No source-pinned real-world enrollment or independently monotonic off-host
nonce witness is installed: production admission therefore fails closed.
"""
from __future__ import annotations

import base64
import json
from pathlib import Path

import settlement_human_authority_verify as human
import settlement_maintenance_phase_review as phase
import settlement_maintenance_nonce_store as nonce_store

# A real independent external witness integration MUST be added to the
# production controller before a live operator can receive positive authority.
# A local signed snapshot is insufficient: root could restore its old bytes.
def independently_consume_remote_nonce(*_args, **_kwargs):
    raise human.Refusal("INDEPENDENT_MONOTONIC_NONCE_WITNESS_UNAVAILABLE")


MODE_TO_PHASE = {
    "capture": "live_capture",
    "offline-restore": "offline_verify",
    "resume": "resume",
}
PROCEDURE_SCHEMA = "wolo.financial-controller-execution-procedure.v1"
PROCEDURE_KEYS = {
    "schema", "mode", "fence_receipt_path", "output_path",
    "legacy_permit_core_sha256", "source_drift_disposition_sha256",
    "writer_inventory_sha256",
}
PINNED_DIGESTS = {
    "registry_sha256", "host_identity_sha256", "source_commit",
    "source_drift_disposition_sha256",
}
REQUIRED_PINS = PINNED_DIGESTS | {"revoked_key_ids"}


def require(condition, why):
    if not condition:
        raise human.Refusal(why)


def exact_private(path, root):
    """Root-owned no-follow source, including all ancestor permission guards."""
    from settlement_financial_maintenance import private_read
    p, parent = Path(path), Path(root)
    require(p.is_absolute() and parent.is_absolute() and
            (p == parent or parent in p.parents),
            "AUTHORITY_INPUT_OUTSIDE_PROTECTED_ROOT")
    return private_read(p, limit=1<<20)


P1_DISPOSITION_SCHEMA = "wolo.financial-maintenance-source-drift-disposition.v1"
P1_DISPOSITION_FIELDS = frozenset({
    "schema", "p1_resolved", "runtime_binary_provenance_verified",
    "settlement_journal_and_signer_compatibility_verified",
    "vps_source_commit", "candidate_source_commit",
    "running_node_sha256", "running_primary_settlement_sha256",
    "running_founder_settlement_sha256",
    "source_difference_evidence_sha256",
    "independent_chain_review_sha256", "independent_source_review_sha256",
})


def require_resolved_p1_disposition(raw, expected_commit):
    """A pinned digest of an unresolved HOLD document is not clearance.

    This structural control does NOT authenticate human identity or certify
    that external binary provenance exists. Those are separate hard gates.
    """
    d = phase.decode(raw, P1_DISPOSITION_SCHEMA, P1_DISPOSITION_FIELDS)
    require(d["p1_resolved"] is True and
            d["runtime_binary_provenance_verified"] is True and
            d["settlement_journal_and_signer_compatibility_verified"] is True,
            "SOURCE_P1_UNRESOLVED")
    for field in ("vps_source_commit", "candidate_source_commit"):
        require(type(d[field]) is str and human.HEX40.fullmatch(d[field]),
                "SOURCE_COMMIT_PROVENANCE_INVALID")
    require(d["candidate_source_commit"] == expected_commit,
            "SOURCE_COMMIT_DISPOSITION_MISMATCH")
    proofs = ("running_node_sha256", "running_primary_settlement_sha256",
              "running_founder_settlement_sha256",
              "source_difference_evidence_sha256",
              "independent_chain_review_sha256", "independent_source_review_sha256")
    require(all(type(d[k]) is str and human.HEX64.fullmatch(d[k]) and
                d[k] != "0"*64 for k in proofs) and
            d["independent_chain_review_sha256"] != d["independent_source_review_sha256"],
            "SOURCE_P1_INDEPENDENT_EVIDENCE_UNVERIFIED")
    return d


def signed_core(permit):
    """Exclude ONLY cyclic metadata; all real DB/image/budget scope is signed."""
    excluded = {"packet_sha256", "procedure_sha256", "approval_refs"}
    require(set(excluded).issubset(permit), "LEGACY_PERMIT_FIELDS_INCOMPLETE")
    return {key:value for key,value in permit.items() if key not in excluded}


def authenticate_and_reserve(args, *, mode, source_tool_sha256, scope_sha256,
                             anchors, root, nonce_root,
                             independent_consumer=None, now=None):
    """Five genuine signatures + separately pinned code/host/enrollment + burn.

    The independent_consumer test seam is used ONLY on throwaway fixtures;
    the actual CLI NEVER supplies it. Default external consumer refuses.
    """
    from settlement_financial_maintenance import (private_json, private_read,
        validate_permit, verify_retained_fence, BACKUPS, digest, canonical)
    require(mode in MODE_TO_PHASE, "UNAPPROVED_FINANCIAL_OPERATION")
    require(type(anchors) is dict and set(anchors)==REQUIRED_PINS,
            "AUTHORITY_ANCHOR_SCHEMA_INVALID")
    require(all(type(anchors[k]) is str and
        (human.HEX40.fullmatch(anchors[k]) if k=="source_commit" else
         human.HEX64.fullmatch(anchors[k])) and
        anchors[k] not in ("0"*40,"0"*64) for k in PINNED_DIGESTS),
        "INDEPENDENT_TRUST_AND_SOURCE_ENROLLMENT_MISSING")
    require(type(anchors["revoked_key_ids"]) in (tuple,list) and
            len(anchors["revoked_key_ids"])==len(set(anchors["revoked_key_ids"])) and
            all(type(x) is str and human.ID.fullmatch(x)
                for x in anchors["revoked_key_ids"]),
            "REVOCATION_ANCHOR_INVALID")
    root=Path(root)
    require(root.is_absolute(), "PRIVATE_AUTHORITY_ROOT_REQUIRED")

    required_inputs=("registry","packet","nonce_ledger","evidence","procedure",
                     "host_identity","source_drift_disposition")
    for key in required_inputs:
        require(getattr(args,key,None) is not None,
                "COMPLETE_SIGNED_AUTHORITY_FILES_REQUIRED")
    registry_raw=exact_private(args.registry,root)
    packet_raw=exact_private(args.packet,root)
    ledger_raw=exact_private(args.nonce_ledger,root)
    evidence=exact_private(args.evidence,root)
    procedure=exact_private(args.procedure,root)
    host=exact_private(args.host_identity,root)
    source_drift=exact_private(args.source_drift_disposition,root)
    require(digest(registry_raw)==anchors["registry_sha256"] and
            digest(host)==anchors["host_identity_sha256"] and
            digest(source_drift)==anchors["source_drift_disposition_sha256"],
            "SOURCE_HOST_TRUST_OR_DISPOSITION_DRIFT")
    require_resolved_p1_disposition(source_drift, anchors["source_commit"])
    registry=human.parse_json(registry_raw)
    require(all(type(p) is dict and p.get("key_id") not in anchors["revoked_key_ids"]
                for p in registry.get("principals",[])),
            "REVOKED_HUMAN_APPROVER")
    packet=human.parse_json(packet_raw)
    ledger=human.parse_json(ledger_raw)
    request=packet.get("request")
    require(type(request) is dict and request.get("phase")==MODE_TO_PHASE[mode],
            "OPERATION_PHASE_MISMATCH")

    proc=phase.decode(procedure,PROCEDURE_SCHEMA,frozenset(PROCEDURE_KEYS))
    require(proc["mode"]==mode and proc["fence_receipt_path"]==str(args.fence_receipt)
            and proc["output_path"]==(str(args.output) if args.output else None)
            and proc["source_drift_disposition_sha256"]==digest(source_drift),
            "SIGNED_PROCEDURE_OPERATION_MISMATCH")
    # No partial or unclassified writer-owner inventory can pass admission.
    inventory_path=root/"independent-writer-coverage.json"
    inventory=exact_private(inventory_path,root)
    require(proc["writer_inventory_sha256"]==digest(inventory),
            "INDEPENDENT_WRITER_COVERAGE_DIGEST_MISMATCH")
    covered=human.parse_json(inventory)
    required_owners={"hd_web_api","de_web_api","seven_timer_service_pairs",
        "postgres_dba","manual_sql_and_ssh","cron_and_user_systemd",
        "ci_and_deployment","settlement_8092_8093_bearers",
        "offhost_wallet_and_chain_signers","auxiliary_settlement_and_indexers",
        "hasura_secondary_targets","legacy_and_de_manual_executors"}
    require(set(covered)=={"schema","writers"} and
            covered["schema"]=="wolo.financial-writer-independent-coverage.v1" and
            type(covered["writers"]) is dict and
            set(covered["writers"])==required_owners,
            "FINANCIAL_WRITER_COVERAGE_INCOMPLETE")
    # Every inventory SHA MUST resolve to actual, canonical, private evidence
    # for the exact signed source, scope, writer category and phase window.
    # A well-formed hash string alone is NOT a witness observation.
    writer_evidence_fields=frozenset({
        "schema","category","owner_id","independent_reviewer_id",
        "excluded_during_window","scope_sha256","source_commit",
        "not_before","expires_at","observation_sha256",
        "independent_witness_sha256",
    })
    for category,item in covered["writers"].items():
        require(type(item) is dict and
            set(item)=={"owner_id","independent_reviewer_id",
                        "excluded_during_window","evidence_sha256"} and
            type(item["owner_id"]) is str and 3<=len(item["owner_id"])<=120 and
            type(item["independent_reviewer_id"]) is str and
            item["independent_reviewer_id"] != item["owner_id"] and
            item["excluded_during_window"] is True and
            type(item["evidence_sha256"]) is str and
            human.HEX64.fullmatch(item["evidence_sha256"]),
            "FINANCIAL_WRITER_OWNER_UNATTESTED")
        try:
            raw=exact_private(root/"writer-coverage"/(category+".json"),root)
        except (OSError, KeyError):
            raise human.Refusal("WRITER_EVIDENCE_FILE_UNAVAILABLE") from None
        require(digest(raw)==item["evidence_sha256"],
                "WRITER_EVIDENCE_FILE_HASH_MISMATCH")
        doc=phase.decode(raw,"wolo.financial-writer-coverage-evidence.v1",
                         writer_evidence_fields)
        require(doc["category"]==category and
                doc["owner_id"]==item["owner_id"] and
                doc["independent_reviewer_id"]==item["independent_reviewer_id"] and
                doc["excluded_during_window"] is True and
                doc["scope_sha256"]==scope_sha256 and
                doc["source_commit"]==anchors["source_commit"] and
                doc["not_before"]==request["not_before"] and
                doc["expires_at"]==request["expires_at"],
                "WRITER_EVIDENCE_SCOPE_OR_PHASE_MISMATCH")
        require(all(type(doc[k]) is str and human.HEX64.fullmatch(doc[k]) and
                    doc[k]!="0"*64 for k in (
                    "observation_sha256","independent_witness_sha256")) and
                doc["observation_sha256"]!=doc["independent_witness_sha256"],
                "WRITER_WITNESS_EVIDENCE_MISSING")

    if mode=="capture":
        require(args.permit is not None and args.output is not None and
                args.output.parent==BACKUPS, "CAPTURE_BUDGETED_OUTPUT_REQUIRED")
        permit,permit_sha=private_json(args.permit)
        validate_permit(permit,now=now)
        require(proc["legacy_permit_core_sha256"]==digest(canonical(signed_core(permit)))
                and permit["tool_sha256"]==source_tool_sha256
                and permit["scope_sha256"]==scope_sha256,
                "SIGNED_PERMIT_SOURCE_SCOPE_MISMATCH")
        require(permit["packet_sha256"]==digest(human.canonical(packet)) and
                permit["procedure_sha256"]==digest(procedure) and
                permit["max_total_bytes"]==request["max_total_bytes"] and
                permit["not_before"]==request["not_before"] and
                permit["expires_at"]==request["expires_at"],
                "PERMIT_NOT_BOUND_TO_SIGNED_APPROVALS")
        by_role={a["role"]:a for a in packet.get("approvals",[]) if type(a) is dict}
        require(set(by_role)==set(permit["approval_refs"]), "PERMIT_APPROVER_SET_MISMATCH")
        for role,ref in permit["approval_refs"].items():
            signed=by_role[role]
            try: sig=base64.b64decode(signed["signature_b64"],validate=True)
            except Exception: raise human.Refusal("SIGNATURE_ENCODING_INVALID") from None
            require(ref["identity"]==signed["person_id"] and
                    ref["approval_sha256"]==digest(sig),
                    "PERMIT_APPROVAL_NOT_CRYPTOGRAPHICALLY_BOUND")
        capture=fence=restore=previous=None
    else:
        require(args.output is not None and args.output.is_dir() and
                args.output.parent==BACKUPS, "OFFLINE_ARCHIVE_OUTPUT_INVALID")
        require(args.capture_manifest is not None and args.previous_review is not None,
                "SEALED_CAPTURE_LINEAGE_REQUIRED")
        capture=exact_private(args.capture_manifest,root) # independently sealed root-private copy
        previous=exact_private(args.previous_review,root)
        fence=exact_private(args.fence_receipt,root)
        # The independently signed sealed copy MUST equal the exact archived
        # capture actually selected for restore, not a caller-chosen document.
        from settlement_financial_maintenance import file_sha
        require(digest(capture)==file_sha(args.output/"backup.json"),
                "SIGNED_CAPTURE_NOT_THE_ARCHIVE_BEING_RESTORED")
        restore=(exact_private(args.restore_receipt,root) if
                 mode=="resume" and args.restore_receipt else None)
        if mode=="resume":
            require(restore is not None and
                    digest(restore)==file_sha(args.output/"restore.json"),
                    "SIGNED_RESTORE_NOT_THE_VERIFIED_RECEIPT")
        require(proc["legacy_permit_core_sha256"] is None,
                "OFFLINE_CANNOT_REISSUE_LEGACY_PERMIT")
        # Retained HOLD and exact 18-unit scope must be independently observed.
        # This check is read-only and cannot renew the expired capture permit.
        verify_retained_fence(args.fence_receipt,scope_sha256)

    expected={"registry":anchors["registry_sha256"],
              "source":source_tool_sha256, "scope":scope_sha256,
              "host":anchors["host_identity_sha256"],
              "source_commit":anchors["source_commit"]}
    result=phase.review(packet,registry,registry_raw,
        ledger,expected,evidence,procedure,
        capture=capture,fence=fence,restore=restore,previous=previous,now=now)
    require(result["status"]=="REVIEWED_NONAUTHORIZING" and
            result["production_action_authorized"] is False,
            "UNEXPECTED_AUTHORIZATION_CLAIM")
    phase_evidence=phase.decode(evidence,phase.EVIDENCE_SCHEMA,phase.EVIDENCE_FIELDS)
    require(phase_evidence["writers_and_external_signers_independently_checked"] is True,
            "INDEPENDENT_WRITER_AND_SIGNER_COVERAGE_NOT_CERTIFIED")
    if mode=="offline-restore":
        # Evidence must be exactly the first-phase produced original sealed
        # archives, not a checksum-shaped file or partial capture.
        from settlement_financial_maintenance import FENCE_SCHEMA
        fence_receipt,_=private_json(args.fence_receipt)
        require(fence_receipt.get("schema")==FENCE_SCHEMA and
                fence_receipt.get("resume_authorized") is False,
                "CAPTURE_FENCE_RECEIPT_UNVERIFIED")
    if mode=="resume":
        raise human.Refusal("INDEPENDENT_RESUME_EXECUTOR_NOT_APPROVED")

    # Cryptographic validity is still NOT authority: an *online* independent
    # monotonic witness must atomically attest THIS nonce as fresh. Its
    # not-yet-wired production default always refuses, regardless of signatures.
    consume=independent_consumer or independently_consume_remote_nonce
    witness=consume(request["nonce"],digest(human.canonical(packet)),mode,
                    source_tool_sha256,scope_sha256)
    require(type(witness) is dict and witness.get("fresh_consumption_confirmed") is True
            and witness.get("nonce")==request["nonce"] and
            witness.get("signed_packet_sha256")==digest(human.canonical(packet)),
            "INDEPENDENT_NONCE_CONSUMPTION_NOT_ATTESTED")
    local=nonce_store.reserve_once(nonce_root,request["nonce"],
        digest(human.canonical(packet)),request["phase"])
    require(local["nonce_reserved"] is True and local["production_operation_authorized"] is False,
            "LOCAL_NONCE_BURN_FAILED")
    return request

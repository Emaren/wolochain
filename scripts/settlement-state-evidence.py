#!/usr/bin/env python3
"""Bounded read-only settlement state evidence; never a drain/release certificate.

Inputs are explicit state directories, not env files or keyrings. No networking,
subprocess, signing, repair, lock deletion or state mutation is performed.
source_tree_sha256 binds the bounded observed STATE tree, not a Git revision or
an atomic snapshot. Concurrent activity may happen before/after observation.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys

VERSION = "wolo.settlement.state-evidence.v1"
MAX_ROOTS = 2
MAX_ENTRIES = 10000
MAX_FILE_BYTES = 1 << 20
MAX_TOTAL_BYTES = 16 << 20
FOCUS_MAX_MATCHES = 2500
FOCUS_RECENT_LIMIT = 16
FOCUS_ACCEPTED_LIMIT = 16
MAX_JSON_DEPTH = 32
MAX_JSON_NODES = 100000
ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{2,127}\Z")
HASH = re.compile(r"[a-fA-F0-9]{64}\Z")
AMOUNT = re.compile(r"[1-9][0-9]{0,18}\Z")
DIRECTORIES = {"requests", "runs", "challenge-settlements", "confirmation-receipts",
               "locks", "run-locks", "challenge-locks"}
LOCK_DIRECTORIES = {"locks", "run-locks", "challenge-locks"}
REQUEST_FIELDS = ("request_id", "to_address", "amount_uwolo", "memo", "signer_role")
RUN_FIELDS = ("settlement_run_id", "source_app", "source_event_id", "note", "memo", "signer_role", "payouts")
PAYOUT_FIELDS = ("index", "request_id", "to_address", "amount_uwolo", "memo")
STATUSES = {"confirmed", "accepted", "failed", "refused", "rejected", "unverifiable", "pending", "partial"}


class EvidenceError(ValueError):
    """Stable public error label; never expose a path or file contents."""


def fail(code):
    raise EvidenceError(code)


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            fail("DUPLICATE_JSON_KEY")
        result[key] = value
    return result


def _json(data):
    try:
        value = json.loads(data.decode("utf8"), object_pairs_hook=_object,
                           parse_constant=lambda _: fail("INVALID_JSON_NUMBER"))
    except EvidenceError:
        raise
    except (ValueError, UnicodeError, RecursionError):
        fail("INVALID_JSON")
    stack, count = [(value, 0)], 0
    while stack:
        node, depth = stack.pop()
        count += 1
        if count > MAX_JSON_NODES or depth > MAX_JSON_DEPTH:
            fail("JSON_RESOURCE_LIMIT")
        if isinstance(node, dict):
            stack.extend((item, depth + 1) for item in node.values())
            stack.extend((key, depth + 1) for key in node)
        elif isinstance(node, str):
            try:
                node.encode("utf8")
            except UnicodeError:
                fail("INVALID_JSON_UNICODE")
        elif isinstance(node, list):
            stack.extend((item, depth + 1) for item in node)
    if not isinstance(value, dict):
        fail("INVALID_RECORD_SHAPE")
    return value


def _signature(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_size,
            info.st_mtime_ns, info.st_ctime_ns)


def _open_root(path):
    # Resolve components using O_NOFOLLOW, including ancestors. Retain only the
    # opened root fd: replacing a pathname cannot redirect subsequent reads.
    absolute = os.path.abspath(os.fspath(path))
    fd = os.open(os.path.sep, os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in Path(absolute).parts[1:]:
            nxt = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = nxt
        return fd
    except BaseException:
        os.close(fd)
        raise


def _names(fd, budget):
    before = _signature(os.fstat(fd))
    names = []
    with os.scandir(fd) as entries:
        for entry in entries:
            budget[0] += 1
            if budget[0] > MAX_ENTRIES:
                fail("ENTRY_LIMIT")
            names.append(entry.name)
    if _signature(os.fstat(fd)) != before:
        fail("STATE_CHANGED_DURING_READ")
    return sorted(names), before


def _read(fd, name, budget):
    info = os.stat(name, dir_fd=fd, follow_symlinks=False)
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        fail("UNSAFE_STATE_ENTRY")
    if info.st_size > MAX_FILE_BYTES:
        fail("FILE_SIZE_LIMIT")
    child = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
    try:
        opened = os.fstat(child)
        if _signature(opened) != _signature(info):
            fail("STATE_CHANGED_DURING_READ")
        chunks, size = [], 0
        while True:
            chunk = os.read(child, min(65536, MAX_FILE_BYTES + 1 - size))
            if not chunk:
                break
            chunks.append(chunk)
            size += len(chunk)
            if size > MAX_FILE_BYTES:
                fail("FILE_SIZE_LIMIT")
        budget[1] += size
        if budget[1] > MAX_TOTAL_BYTES:
            fail("TOTAL_SIZE_LIMIT")
        if _signature(os.fstat(child)) != _signature(opened):
            fail("STATE_CHANGED_DURING_READ")
        if _signature(os.stat(name, dir_fd=fd, follow_symlinks=False)) != _signature(opened):
            fail("STATE_CHANGED_DURING_READ")
        return b"".join(chunks)
    finally:
        os.close(child)


def _go_json(value):
    # encoding/json.Marshal's compact UTF-8 and HTML escaping, for the explicit
    # ordered string-only normalized request schemas below. No generic Go JSON
    # decoder or payment parser is reimplemented here.
    text = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    for char, escaped in (("<", r"\u003c"), (">", r"\u003e"), ("&", r"\u0026"),
                          ("\u2028", r"\u2028"), ("\u2029", r"\u2029")):
        text = text.replace(char, escaped)
    return text.encode("utf8")


def _request(request, fields=REQUEST_FIELDS):
    if not isinstance(request, dict) or set(request) - set(fields):
        fail("UNSUPPORTED_REQUEST_SCHEMA")
    ordered = {}
    for key in fields:
        value = request.get(key, "")
        if not isinstance(value, str):
            fail("INVALID_REQUEST_SHAPE")
        if key in ("memo", "signer_role") and value == "":
            continue
        ordered[key] = value
    if not ID.fullmatch(ordered.get("request_id", "")):
        fail("INVALID_REQUEST_ID")
    amount = ordered.get("amount_uwolo", "")
    if not AMOUNT.fullmatch(amount) or int(amount) > (1 << 63) - 1 or not ordered.get("to_address"):
        fail("INVALID_REQUEST_CONTEXT")
    if ordered.get("signer_role", "payout") not in ("payout", "escrow"):
        fail("UNSUPPORTED_SIGNER_ROLE")
    return ordered


def _run_request(request):
    if not isinstance(request, dict) or set(request) - set(RUN_FIELDS):
        fail("UNSUPPORTED_RUN_SCHEMA")
    ordered = {}
    for key in RUN_FIELDS:
        value = request.get(key, "")
        if key == "payouts":
            if not isinstance(value, list):
                fail("INVALID_RUN_CONTEXT")
            payouts, seen = [], set()
            for index, payout in enumerate(value):
                if not isinstance(payout, dict) or set(payout) - set(PAYOUT_FIELDS) or type(payout.get("index")) is not int or payout["index"] != index:
                    fail("INVALID_RUN_CONTEXT")
                normalized = _request({key: item for key, item in payout.items() if key != "index"}, REQUEST_FIELDS[:-1])
                if normalized["request_id"] in seen:
                    fail("DUPLICATE_RUN_REQUEST")
                seen.add(normalized["request_id"])
                payouts.append({"index": index, **normalized})
            ordered[key] = payouts
        else:
            if not isinstance(value, str):
                fail("INVALID_RUN_CONTEXT")
            if key != "settlement_run_id" and value == "":
                continue
            ordered[key] = value
    if not ID.fullmatch(ordered.get("settlement_run_id", "")):
        fail("INVALID_REQUEST_ID")
    if ordered.get("signer_role", "payout") not in ("payout", "escrow"):
        fail("UNSUPPORTED_SIGNER_ROLE")
    return ordered


def _fingerprint(record, request, signer=None):
    expected = hashlib.sha256(_go_json(request if signer is None else {"request": request, "signer": signer})).hexdigest()
    if record.get("fingerprint") != expected:
        fail("REQUEST_FINGERPRINT_MISMATCH")
    return expected


def _response(response, counts, blockers):
    if not isinstance(response, dict) or not isinstance(response.get("status"), str) or type(response.get("ok")) is not bool or type(response.get("retryable")) is not bool:
        fail("INVALID_RESPONSE_SHAPE")
    status = response["status"]
    counts["recorded_status_" + (status if status in STATUSES else "unknown")] += 1
    tx = response.get("tx_hash", "")
    if not isinstance(tx, str) or (tx and not HASH.fullmatch(tx)):
        fail("INVALID_TX_HASH")
    code = response.get("code", 0)
    if type(code) is not int or code < 0 or code > (1 << 32) - 1:
        fail("INVALID_RECORDED_EXECUTION_CODE")
    if status == "confirmed":
        if not response["ok"] or not tx or response["retryable"] or not response.get("signer_address") or code != 0 or response.get("confirmation_status", "confirmed") != "confirmed":
            fail("INCONSISTENT_RECORDED_CONFIRMATION")
        counts["recorded_payment_not_reverified"] += 1
        blockers.add("CHAIN_OUTCOMES_NOT_REVERIFIED")
    elif status in {"failed", "refused", "rejected"} and response["ok"]:
        fail("INCONSISTENT_RECORDED_FAILURE")
    elif status in {"accepted", "pending", "unverifiable", "partial"} or status not in {"failed", "refused", "rejected"}:
        blockers.add("UNRESOLVED_RECORDED_OUTCOME")
    elif tx:
        counts["recorded_chain_failure_not_reverified"] += 1
        blockers.add("CHAIN_OUTCOMES_NOT_REVERIFIED")
    else:
        counts["recorded_local_failure_not_payment"] += 1
    if response["retryable"]:
        blockers.add("RETRYABLE_RECORD_REQUIRES_RECONCILIATION")
    if status == "unverifiable" and not tx and not response["retryable"]:
        counts["nonretryable_nohash_holds"] += 1
    return tx.upper()


def _unavailable_accounting():
    # Unknown must remain null, never a zero inferred from a failed observation.
    return {
        "amount_groups": [], "leaf_record_requested_principal_uwolo": None,
        "deduplicated_observed_requested_principal_uwolo": None,
        "unique_obligation_count": None, "deduplicated_aggregate_references": None,
        "aggregate_only_obligation_count": None,
        "complete_for_observed_requests_and_runs": False,
        "observed_execution_principal_min_uwolo": None,
        "observed_execution_principal_max_uwolo": None,
        "observed_execution_principal_scope": "at_most_one_canonical_principal_effect_per_observed_obligation_not_historical_bank_outflow",
        "historical_outflow_upper_bound_uwolo": None,
        "global_liability_upper_bound_uwolo": None,
        "global_liability_bound": "UNBOUNDED_NOT_PROVEN",
        "recorded_status_is_chain_proof": False, "fees_included": False,
        "gaps": ["OBSERVATION_UNAVAILABLE"],
    }


def _accounting(leaves, run_children, blockers):
    # The identity is a lane-local durable request, not a tx hash or an aggregate
    # parent. A repeated reference never creates another amount or nets a debt.
    # Neither the lower bound nor the upper bound describes actual bank outflow:
    # historical attempts, fees and unobserved obligations remain unbounded.
    accounting = _unavailable_accounting()
    gap_codes = {
        "TRANSACTION_REUSED_BY_DISTINCT_REQUESTS", "CROSS_LANE_RECEIPT_REUSE",
        "RECEIPT_WITHOUT_OBSERVED_REQUEST", "RECEIPT_REQUEST_OWNERSHIP_MISMATCH",
        "RECEIPT_WITHOUT_FINAL_REQUEST_OUTCOME", "LOCK_PRESENT_NOT_SAFE_TO_DELETE",
        "TEMPORARY_STATE_UNRESOLVED", "CHALLENGE_CONTEXT_NOT_INDEPENDENTLY_VALIDATED",
        "RETRYABLE_RECORD_REQUIRES_RECONCILIATION",
    }
    gaps = blockers & gap_codes
    obligations = dict(leaves)
    aggregate_only, deduplicated = set(), 0
    for identity, context in run_children:
        if identity in obligations:
            deduplicated += 1
            if obligations[identity][0] != context:
                gaps.add("ACCOUNTING_OBLIGATION_CONTEXT_CONFLICT")
        else:
            obligations[identity] = (context, "aggregate_only")
            aggregate_only.add(identity)
    if aggregate_only:
        gaps.add("AGGREGATE_CHILD_WITHOUT_REQUEST_RECORD")
    groups = collections.defaultdict(lambda: [0, 0])
    for (lane, _), (context, status) in obligations.items():
        role, _, amount, _ = context
        if status not in STATUSES and status != "aggregate_only":
            status = "unknown"
            gaps.add("UNKNOWN_RECORDED_STATUS")
        row = groups[(lane, role, status)]
        row[0] += 1
        row[1] += int(amount)
    leaf_total = sum(int(context[2]) for context, _ in leaves.values())
    observed_total = sum(int(context[2]) for context, _ in obligations.values())
    conflict = "ACCOUNTING_OBLIGATION_CONTEXT_CONFLICT" in gaps
    accounting.update({
        "amount_groups": [{"lane_index": lane, "signer_role": role,
                           "recorded_status": status, "request_count": value[0],
                           "recorded_requested_principal_uwolo": str(value[1])}
                          for (lane, role, status), value in sorted(groups.items())],
        "leaf_record_requested_principal_uwolo": str(leaf_total),
        "deduplicated_observed_requested_principal_uwolo": None if conflict else str(observed_total),
        "unique_obligation_count": len(obligations),
        "deduplicated_aggregate_references": deduplicated,
        "aggregate_only_obligation_count": len(aggregate_only),
        "complete_for_observed_requests_and_runs": not gaps,
        "observed_execution_principal_min_uwolo": "0",
        "observed_execution_principal_max_uwolo": None if gaps else str(observed_total),
        "gaps": sorted(gaps),
    })
    return accounting


def _economic_context(request, role):
    return (role, request["to_address"], request["amount_uwolo"], request.get("memo", ""))


def _reader_identity():
    # stdin is intentionally supported without writing a remote script. Its
    # exact bytes must be bound by the authenticated caller's separate receipt.
    unavailable = {"reader_source_sha256": None,
                   "reader_source_identity": "EXTERNAL_EXACT_SOURCE_PROVENANCE_REQUIRED"}
    source = globals().get("__file__")
    if not isinstance(source, str) or source in ("<stdin>", "-", ""):
        return unavailable
    fd = None
    try:
        fd = os.open(source, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_size > MAX_FILE_BYTES:
            return unavailable
        data = bytearray()
        while len(data) <= MAX_FILE_BYTES:
            chunk = os.read(fd, min(65536, MAX_FILE_BYTES + 1 - len(data)))
            if not chunk:
                break
            data.extend(chunk)
        if len(data) > MAX_FILE_BYTES or _signature(os.fstat(fd)) != _signature(before):
            return unavailable
        if _signature(os.stat(source, follow_symlinks=False)) != _signature(before):
            return unavailable
        return {"reader_source_sha256": hashlib.sha256(data).hexdigest(),
                "reader_source_identity": "OBSERVED_MODULE_SOURCE_BYTES"}
    except OSError:
        return unavailable
    finally:
        if fd is not None:
            os.close(fd)


def inspect_state(roots, *, focus_escrow_100=False, escrow_identity_manifest=False):
    if (type(focus_escrow_100) is not bool or
            type(escrow_identity_manifest) is not bool or
            (escrow_identity_manifest and not focus_escrow_100)):
        fail("INVALID_FOCUS_MODE")
    if not 1 <= len(roots) <= MAX_ROOTS:
        fail("ROOT_COUNT_LIMIT")
    counts, blockers = collections.Counter(), {"LOCAL_STATE_CANNOT_CERTIFY_GLOBAL_DRAIN"}
    manifest, requests, receipts, observed_hashes, budget = [], {}, [], {}, [0, 0]
    leaves, run_children, focused_escrow = {}, [], []
    seen_roots = set()
    try:
        for lane, root in enumerate(roots):
            fd = _open_root(root)
            try:
                root_info = os.fstat(fd)
                identity = (root_info.st_dev, root_info.st_ino)
                if identity in seen_roots:
                    fail("DUPLICATE_STATE_ROOT")
                seen_roots.add(identity)
                names, before = _names(fd, budget)
                manifest.append([lane, "", "directory"])
                for dirname in names:
                    if dirname not in DIRECTORIES:
                        fail("UNSUPPORTED_STATE_LAYOUT")
                    child = os.open(dirname, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                    try:
                        entries, dir_before = _names(child, budget)
                        manifest.append([lane, dirname, "directory"])
                        for name in entries:
                            data = _read(child, name, budget)
                            manifest.append([lane, dirname + "/" + name, len(data), hashlib.sha256(data).hexdigest()])
                            counts["files"] += 1
                            if dirname in LOCK_DIRECTORIES or name.endswith(".lock"):
                                counts["locks"] += 1
                                blockers.add("LOCK_PRESENT_NOT_SAFE_TO_DELETE")
                                continue
                            if name.endswith(".tmp"):
                                counts["temporary_files"] += 1
                                blockers.add("TEMPORARY_STATE_UNRESOLVED")
                                continue
                            if not name.endswith(".json"):
                                fail("UNSUPPORTED_STATE_LAYOUT")
                            record = _json(data)
                            counts[dirname] += 1
                            if dirname == "confirmation-receipts":
                                required = {"version", "chain_id", "tx_hash", "transfer_index", "request_id", "signer_address", "fingerprint"}
                                if set(record) != required or record["version"] != "wolo.settlement.confirmation.v1" or record["chain_id"] != "wolo-1" or not isinstance(record["tx_hash"], str) or not HASH.fullmatch(record["tx_hash"]) or type(record["transfer_index"]) is not int or record["transfer_index"] != 0 or name != record["tx_hash"].upper() + "-0.json" or not isinstance(record["request_id"], str) or not ID.fullmatch(record["request_id"]) or not isinstance(record["signer_address"], str) or not record["signer_address"] or not isinstance(record["fingerprint"], str) or not HASH.fullmatch(record["fingerprint"]):
                                    fail("INVALID_RECEIPT_CONTEXT")
                                receipts.append((lane, record))
                                blockers.add("LEGACY_BINARY_IGNORES_CONFIRMATION_RECEIPTS")
                                continue
                            request, response = record.get("request"), record.get("response")
                            if not isinstance(request, dict):
                                fail("INVALID_RECORD_SHAPE")
                            if dirname == "requests":
                                request = _request(request)
                                request_id = request["request_id"]
                                if name != request_id + ".json" or not isinstance(response, dict) or response.get("request_id") != request_id or response.get("chain_id") != "wolo-1":
                                    fail("REQUEST_IDENTITY_MISMATCH")
                                signer = response.get("signer_address", "")
                                if not isinstance(signer, str):
                                    fail("INVALID_REQUEST_CONTEXT")
                                request_role = request.get("signer_role", "payout")
                                response_role = response.get("signer_role", "payout")
                                if not isinstance(response_role, str) or (response_role.strip().lower() or "payout") != request_role:
                                    fail("REQUEST_ROLE_MISMATCH")
                                for field in ("to_address", "amount_uwolo"):
                                    if field in response and response[field] != request[field]:
                                        fail("REQUEST_CONTEXT_MISMATCH")
                                fingerprint = _fingerprint(record, request, signer)
                                tx = _response(response, counts, blockers)
                                if (focus_escrow_100 and request_role == "escrow"
                                        and request["amount_uwolo"] == "100000000"
                                        and response["status"] in ("accepted", "confirmed")):
                                    if len(focused_escrow) >= FOCUS_MAX_MATCHES:
                                        fail("FOCUS_MATCH_LIMIT")
                                    # The entry mtime is solely an untrusted ordering
                                    # hint; it is NOT a transfer or creation timestamp.
                                    updated = os.stat(name, dir_fd=child,
                                                      follow_symlinks=False)
                                    if not stat.S_ISREG(updated.st_mode):
                                        fail("FOCUS_ENTRY_CHANGED")
                                    focused_escrow.append({
                                        "laneIndex": lane,
                                        "recordedStatus": response["status"],
                                        "recordedRequestedPrincipalUwolo": "100000000",
                                        "requestIdSha256": hashlib.sha256(
                                            request_id.encode("utf8")).hexdigest(),
                                        "requestRecordSha256": hashlib.sha256(data).hexdigest(),
                                        "recordedPublicTxHash": tx or None,
                                        "filesystemMtimeNsHint": str(updated.st_mtime_ns),
                                        "recordedStatusIsChainProof": False,
                                        "retryAuthorized": False,
                                    })
                                requests[(lane, request_id)] = (fingerprint, signer, tx)
                                leaves[(lane, request_id)] = (_economic_context(request, request_role), response["status"])
                                if tx:
                                    owner = (lane, request_id)
                                    if tx in observed_hashes and observed_hashes[tx] != owner:
                                        blockers.add("TRANSACTION_REUSED_BY_DISTINCT_REQUESTS")
                                    observed_hashes[tx] = owner
                            else:
                                # Aggregate records are evidence, not proof of every
                                # child transfer, signer, funding source or obligation.
                                request_id = request.get("settlement_run_id")
                                if not isinstance(request_id, str) or not ID.fullmatch(request_id) or name != request_id + ".json" or not isinstance(response, dict) or response.get("settlement_run_id") != request_id:
                                    fail("REQUEST_IDENTITY_MISMATCH")
                                if dirname == "runs":
                                    normalized = _run_request(request)
                                    _fingerprint(record, normalized)
                                    role = normalized.get("signer_role", "payout")
                                    run_children.extend(((lane, child["request_id"]), _economic_context(child, role))
                                                        for child in normalized["payouts"])
                                else:
                                    if not isinstance(record.get("fingerprint"), str) or not HASH.fullmatch(record["fingerprint"]):
                                        fail("INVALID_REQUEST_FINGERPRINT")
                                    blockers.add("CHALLENGE_CONTEXT_NOT_INDEPENDENTLY_VALIDATED")
                                # Aggregate success has no top-level tx_hash; inspect
                                # status without mislabelling it a paid transfer.
                                status = response.get("status")
                                if status == "unverifiable":
                                    blockers.add("LEGACY_AGGREGATE_UNVERIFIABLE_NOT_FINAL")
                                counts["aggregate_status_" + (status if status in {"confirmed", "accepted", "failed", "partial", "unverifiable"} else "unknown")] += 1
                                blockers.add("AGGREGATE_CHILD_OUTCOMES_REQUIRE_RECONCILIATION")
                                if type(response.get("ok")) is not bool or type(response.get("retryable")) is not bool:
                                    fail("INVALID_RESPONSE_SHAPE")
                        if _signature(os.fstat(child)) != dir_before:
                            fail("STATE_CHANGED_DURING_READ")
                    finally:
                        os.close(child)
                if _signature(os.fstat(fd)) != before:
                    fail("STATE_CHANGED_DURING_READ")
            finally:
                os.close(fd)
    except EvidenceError:
        raise
    except OSError:
        fail("STATE_UNAVAILABLE_OR_UNSAFE")
    receipt_keys = set()
    for lane, receipt in receipts:
        owner = requests.get((lane, receipt["request_id"]))
        if owner is None:
            blockers.add("RECEIPT_WITHOUT_OBSERVED_REQUEST")
        elif owner[:2] != (receipt["fingerprint"], receipt["signer_address"]) or (owner[2] and owner[2] != receipt["tx_hash"].upper()):
            blockers.add("RECEIPT_REQUEST_OWNERSHIP_MISMATCH")
        elif not owner[2]:
            blockers.add("RECEIPT_WITHOUT_FINAL_REQUEST_OUTCOME")
        key = (receipt["chain_id"], receipt["tx_hash"].upper(), receipt["transfer_index"])
        if key in receipt_keys:
            blockers.add("CROSS_LANE_RECEIPT_REUSE")
        receipt_keys.add(key)
    result = {
        "version": VERSION, "status": "HELD", "observation_complete": True,
        "observation_atomic": False, "roots_observed": len(roots),
        "source_tree_sha256": hashlib.sha256(_go_json(manifest)).hexdigest(),
        "source_tree_scope": "bounded_observed_state_tree_not_git_or_atomic_snapshot",
        **_reader_identity(),
        "bytes_observed": budget[1], "counts": dict(sorted(counts.items())),
        "blockers": sorted(blockers), "request_fingerprint_algorithm": "Go_normalized_request_schema_v1",
        "chain_proof_verified": False, "all_historical_paths_covered": False,
        "founder_889_resolved": False, "financial_drained": False,
        "rollback_compatible": False, "release_authorized": False,
        "retry_authorized": False, "filesystem_writes": False,
        "accounting": _accounting(leaves, run_children, blockers),
    }
    if focus_escrow_100:
        # Include EVERY accepted 100-WOLO request, then a bounded selection
        # of confirmed records using untrusted filesystem mtime. No inference
        # that these are the eight new Oct18→Oct20 ledger additions is allowed.
        accepted = [row for row in focused_escrow
                    if row["recordedStatus"] == "accepted"]
        if len(accepted) > FOCUS_ACCEPTED_LIMIT:
            fail("FOCUS_ACCEPTED_LIMIT")
        confirmed = [row for row in focused_escrow
                     if row["recordedStatus"] == "confirmed"]
        confirmed.sort(key=lambda x: (int(x["filesystemMtimeNsHint"]),
                                       x["requestIdSha256"]), reverse=True)
        result["escrow100Focus"] = {
            "mode": "PRIVACY_MINIMIZED_READ_ONLY_100_WOLO_RECONCILIATION_LEADS",
            "matchedAcceptedCount": len(accepted),
            "matchedConfirmedCount": len(confirmed),
            "acceptedRecords": sorted(accepted, key=lambda x: x["requestIdSha256"]),
            "recentlyModifiedConfirmedRecords": confirmed[:FOCUS_RECENT_LIMIT],
            "confirmedRecordsOmitted": max(0, len(confirmed) - FOCUS_RECENT_LIMIT),
            "selectionProvesLatest8NewRequests": False,
            "mtimeIsTrustedTransferTime": False,
            "individualRequestRecordIdsEmitted": False,
            "individualWalletAddressesOrMemosEmitted": False,
            "publicTxHashesAreUnauthenticatedJournalClaims": True,
            "independentChainProofVerified": False,
            "globalObligationsReconciled": False,
            "financialReleaseAuthorized": False,
            "retryAuthorized": False,
        }
    if escrow_identity_manifest:
        # Full scoped identity list, never user wallet/memo/private request ID.
        # The count is bounded by the existing FOCUS_MATCH_LIMIT. This gives a
        # future independent reader exact record-delta leads, not chain finality
        # or proof that a particular request arrived between observations.
        rows = sorted((
            {"laneIndex": row["laneIndex"],
             "recordedStatus": row["recordedStatus"],
             "requestIdSha256": row["requestIdSha256"],
             "requestRecordSha256": row["requestRecordSha256"]}
            for row in focused_escrow
        ), key=lambda row: (row["laneIndex"], row["requestIdSha256"]))
        result["escrow100IdentityManifest"] = {
            "schema": "wolo.settlement.escrow100-identity-manifest.v1",
            "count": len(rows),
            "complete_for_observed_100_wolo_requests": True,
            "records": rows,
            "private_request_ids_or_wallets_emitted": False,
            "authoritative_chain_evidence": False,
            "financial_release_authorized": False,
        }
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-root", action="append", required=True, type=Path)
    parser.add_argument("--focus-escrow-100", action="store_true",
                        help="Include bounded, nonauthorizing public tx leads without wallets/memos")
    parser.add_argument("--full-escrow-100-manifest", action="store_true",
                        help="Add all bounded hashed request identities for future nonauthorizing delta comparison")
    args = parser.parse_args(argv)
    try:
        output = inspect_state(args.state_root,
                               focus_escrow_100=(args.focus_escrow_100 or args.full_escrow_100_manifest),
                               escrow_identity_manifest=args.full_escrow_100_manifest)
    except EvidenceError as error:
        print(json.dumps({"version": VERSION, "status": "HELD", "observation_complete": False,
                          "error": str(error), "release_authorized": False, "retry_authorized": False,
                          "accounting": _unavailable_accounting()}, sort_keys=True))
        return 2
    print(json.dumps(output, sort_keys=True, indent=2))
    return 3


if __name__ == "__main__":
    sys.exit(main())

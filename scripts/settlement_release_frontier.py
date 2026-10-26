#!/usr/bin/env python3
"""Bounded release-frontier projection; the six-control checklist stays authoritative.

No SSH, wallet, chain query, signer, nonce, financial value or production write.
GitHub refresh is explicit and read-only. An operator packet never becomes a
TOOL_OBSERVED fact merely because its JSON claims a successful observation.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import re
import selectors
import signal
import stat
import subprocess
import time

from financial_release_checklist_audit import audit, safe_read, json_object, INDEX, AuditFailure

SCHEMA = "aoe2war.release-frontier.observation.v1"
OPERATOR_SCHEMA = "aoe2war.release-frontier.operator-observation.v1"
SHA = re.compile(r"[0-9a-f]{40}\Z")
DIGEST = re.compile(r"[0-9a-f]{64}\Z")
LABEL = re.compile(r"[A-Za-z0-9_.:-]{1,96}\Z")
MAX_BYTES = 262144
MAX_AGE = 900
GITHUB_BUDGET = 25
TARGETS = (("wolo", "Emaren/wolochain", 111), ("funded_hd", "Emaren/app-prodn", 931),
           ("kingdom_index", "Emaren/app-prodn", 930), ("general_inspections", "Emaren/app-prodn", 884))
CONTROL_OWNERS = {
    "hd_de_producers_isolated": "OWNER_OPERATOR_AND_RECOVERY_ENGINEERING",
    "inflight_requests_and_accepted_tx_reconciled": "OWNER_FINANCE_AND_EXTERNAL_CHAIN_EVIDENCE",
    "claim_889_liability_preserved_and_release_reviewed": "OWNER_FINANCE",
    "fresh_quiesced_backup_hash_verified": "OWNER_OPERATOR_AND_RECOVERY_ENGINEERING",
    "reviewed_code_only_rollback_rehearsed": "OWNER_OPERATOR_AND_RECOVERY_ENGINEERING",
    "bank_solvent_and_independently_checked": "OWNER_FINANCE_AND_EXTERNAL_CHAIN_EVIDENCE",
}
GAPS = (
    ("historical_finality", "EXTERNAL_CHAIN_EVIDENCE_ISSUER", "HOLD_EXTERNAL_TRUST_EVIDENCE",
     "Externally anchored wolo-1 header/checkpoint at historical height 1078913, commit/validator evidence, original accepted intent and authentic archival/as-of provenance. Same-operator RPC agreement and the expired IBC client cannot supply this."),
    ("same_height_solvency", "OWNER_FINANCE_AND_EXTERNAL_CHAIN_EVIDENCE", "HOLD_FINANCIAL_SOLVENCY",
     "Native SDK bank proofs at one state height H committed by H+1; fresh independent trust provenance; custody rights; nonoverlapping HD/shared-DE liabilities, uncertain effects, fee/gas and external exposure. Unknown scope is not zero."),
    ("dedicated_custody", "OWNER_CUSTODY_OPERATOR", "HOLD_CUSTODY_EVIDENCE",
     "Actual non-root wolo-satchel service, private 127.0.0.1:8094, separate vault/keyring and durable journal, exact executable, ownership/key ceremony, isolated wager/withdrawal/execution roles and signed revocable custody permit. Source examples are not installed custody."),
    ("writer_exclusion_and_recovery", "OWNER_OPERATOR_AND_RECOVERY_ENGINEERING", "HOLD_ENGINEERING",
     "Signed 18-unit identity-bound capture plus all external writers, no in-flight operations, full protected backups/isolated restore and source-qualified bounded resume. Armed timers are not quiescence; never directly replay financial oneshots."),
    ("funded_canary", "OWNER_TRANSACTION_SIGNER", "HOLD_TRANSACTION_SPECIFIC_AUTHORITY",
     "Only after the preceding controls: a new exact-source transaction-specific signed intent, chain/denom/recipient/amount/gas/exposure ceiling, one-use nonce/expiry and stop-on-unknown mechanism. Never reuse the disputed historical 100-WOLO effect."),
)


class FrontierFailure(ValueError):
    pass


def require(ok, reason):
    if not ok:
        raise FrontierFailure(reason)


def timestamp(value):
    require(type(value) is str and len(value) <= 40, "OBSERVATION_TIMESTAMP_INVALID")
    try:
        at = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise FrontierFailure("OBSERVATION_TIMESTAMP_INVALID") from exc
    require(at.tzinfo is not None and at.utcoffset().total_seconds() == 0,
            "OBSERVATION_UTC_REQUIRED")
    return at


def age(value, now):
    seconds = (now - timestamp(value)).total_seconds()
    return {"observed_at_utc": value, "age_seconds": max(0, int(seconds)),
            "freshness": "CLOCK_INVALID" if seconds < -5 else
            "STALE" if seconds > MAX_AGE else "RECENT_RECORDED",
            "current_runtime_verified": False}


def valid_sha(value, pattern=SHA):
    return type(value) is str and pattern.fullmatch(value) is not None and set(value) != {"0"}


def private_operator_packet(filename):
    p = Path(filename)
    require(p.is_absolute() and p == p.resolve(strict=True), "CANONICAL_OPERATOR_PATH_REQUIRED")
    fd = os.open(p, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        before = os.fstat(stream.fileno())
        require(stat.S_ISREG(before.st_mode) and before.st_uid == os.geteuid() and
                stat.S_IMODE(before.st_mode) == 0o600 and before.st_nlink == 1 and
                0 < before.st_size <= MAX_BYTES, "PRIVATE_OPERATOR_FILE_REQUIRED")
        raw = stream.read(MAX_BYTES + 1)
        after = os.fstat(stream.fileno())
        require(len(raw) == before.st_size and all(getattr(before, k) == getattr(after, k)
                for k in ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")),
                "OPERATOR_FILE_CHANGED")
    packet = json_object(raw)
    allowed = {"schema", "observed_at_utc", "website", "custody", "producer_counts", "storage"}
    require(set(packet) <= allowed and packet.get("schema") == OPERATOR_SCHEMA and
            "observed_at_utc" in packet, "OPERATOR_PACKET_SCHEMA_INVALID")
    timestamp(packet["observed_at_utc"])
    result = {"schema": OPERATOR_SCHEMA, "observed_at_utc": packet["observed_at_utc"]}
    if "website" in packet:
        row = packet["website"]
        require(type(row) is dict and set(row) == {"source_sha", "build_id", "compiled_version"}
                and valid_sha(row["source_sha"]) and all(type(row[k]) is str and LABEL.fullmatch(row[k])
                    for k in ("build_id", "compiled_version")), "OPERATOR_WEBSITE_INVALID")
        result["website"] = row
    if "custody" in packet:
        row = packet["custody"]
        require(type(row) is dict and set(row) == {"service_state", "private_8094_listener"} and
                row["service_state"] in {"NOT_FOUND", "INACTIVE", "ACTIVE", "UNKNOWN"} and
                (row["private_8094_listener"] is None or type(row["private_8094_listener"]) is bool),
                "OPERATOR_CUSTODY_INVALID")
        result["custody"] = row
    if "producer_counts" in packet:
        row = packet["producer_counts"]
        limits = {"scoped_units": 18, "active_apps": 4, "armed_timers": 7, "inactive_oneshots": 7}
        require(type(row) is dict and set(row) == set(limits) and
                all(type(row[k]) is int and 0 <= row[k] <= n for k, n in limits.items()) and
                row["scoped_units"] == 18, "OPERATOR_PRODUCER_COUNTS_INVALID")
        result["producer_counts"] = row
    if "storage" in packet:
        row = packet["storage"]
        require(type(row) is dict and set(row) == {"bounded_total_bytes", "bounded_available_bytes"}
                and all(type(v) is int and 0 <= v <= 1 << 40 for v in row.values()) and
                row["bounded_available_bytes"] <= row["bounded_total_bytes"], "OPERATOR_STORAGE_INVALID")
        result["storage"] = row
    return result


def bounded_command(argv, deadline):
    remaining = min(8, deadline - time.monotonic())
    require(remaining > 0, "GITHUB_REFRESH_BUDGET_EXHAUSTED")
    process = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                               stderr=subprocess.DEVNULL, start_new_session=True)
    output = bytearray()
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ)
    try:
        end = time.monotonic() + remaining
        while selector.get_map():
            require(time.monotonic() < end, "GITHUB_SOURCE_TIMEOUT")
            for key, _ in selector.select(min(.1, max(0, end - time.monotonic()))):
                chunk = os.read(key.fileobj.fileno(), 65536)
                if not chunk:
                    selector.unregister(key.fileobj)
                else:
                    output.extend(chunk)
                    require(len(output) <= MAX_BYTES, "GITHUB_SOURCE_SIZE_LIMIT")
        require(process.wait(timeout=max(.01, end - time.monotonic())) == 0, "GITHUB_SOURCE_UNAVAILABLE")
        return json_object(bytes(output))
    finally:
        if process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()
        selector.close()
        process.stdout.close()


def gh_api(endpoint, projection, deadline):
    return bounded_command(["gh", "api", "--hostname", "github.com", endpoint, "--jq", projection], deadline)


def github_sources(now, api=gh_api):
    deadline = time.monotonic() + GITHUB_BUDGET
    result = {}
    for label, repo, number in TARGETS:
        try:
            endpoint = f"repos/{repo}/pulls/{number}"
            projection = "{head:.head.sha,base:.base.sha,url:.html_url,state:.state}"
            pr = api(endpoint, projection, deadline)
            require(set(pr) == {"head", "base", "url", "state"} and valid_sha(pr["head"]) and
                    valid_sha(pr["base"]) and pr["url"] == f"https://github.com/{repo}/pull/{number}"
                    and pr["state"] in {"open", "closed"}, "GITHUB_PR_IDENTITY_INVALID")
            checks = api(f"repos/{repo}/commits/{pr['head']}/check-runs?per_page=100&filter=latest",
                         "{total_count,checks:[.check_runs[]|{head_sha,status,conclusion}]}", deadline)
            rows = checks.get("checks")
            require(type(rows) is list and type(checks.get("total_count")) is int and
                    len(rows) == checks["total_count"] <= 100, "GITHUB_CHECKS_INCOMPLETE")
            counts = {"success": 0, "failed": 0, "pending": 0, "neutral_or_skipped": 0}
            for row in rows:
                require(type(row) is dict and set(row) == {"head_sha", "status", "conclusion"} and
                        row["head_sha"] == pr["head"] and row["status"] in
                        {"queued", "in_progress", "completed"}, "GITHUB_CHECK_HEAD_MISMATCH")
                if row["status"] != "completed": counts["pending"] += 1
                elif row["conclusion"] == "success": counts["success"] += 1
                elif row["conclusion"] in {"neutral", "skipped"}: counts["neutral_or_skipped"] += 1
                else: counts["failed"] += 1
            after = api(endpoint, projection, deadline)
            require(after == pr, "GITHUB_SOURCE_CHANGED_DURING_REFRESH")
            result[label] = {**pr, "provenance": "TOOL_OBSERVED", "observed_at_utc": now.isoformat(),
                             "check_counts": counts, "required_check_completeness": "NOT_EVALUATED", "source_ci": "FAIL" if counts["failed"] else
                             "PENDING" if counts["pending"] else "PASS" if counts["success"] else "UNKNOWN"}
        except (AuditFailure, FrontierFailure, OSError, ValueError, subprocess.SubprocessError):
            result[label] = {"provenance": "TOOL_OBSERVED", "status": "UNKNOWN",
                             "reason": "GITHUB_IDENTITY_OR_CHECKS_UNAVAILABLE_OR_CHANGED"}
    for label, repo in (("wolo_main", "Emaren/wolochain"), ("hd_main", "Emaren/app-prodn")):
        try:
            row = api(f"repos/{repo}/commits/main", "{sha}", deadline)
            require(set(row) == {"sha"} and valid_sha(row["sha"]), "GITHUB_MAIN_IDENTITY_INVALID")
            result[label] = {"source_sha": row["sha"], "provenance": "TOOL_OBSERVED",
                             "observed_at_utc": now.isoformat()}
        except (AuditFailure, FrontierFailure, OSError, ValueError, subprocess.SubprocessError):
            result[label] = {"status": "UNKNOWN", "provenance": "TOOL_OBSERVED"}
    return result


def frontier(root, *, refresh_github=False, operator_observation=None, now=None):
    at = now or datetime.now(timezone.utc)
    require(at.tzinfo is not None and at.utcoffset().total_seconds() == 0, "UTC_REPORT_CLOCK_REQUIRED")
    raw = safe_read(root, INDEX)
    audit(root)  # Never replace, promote or skip the canonical six-control contract.
    require(safe_read(root, INDEX) == raw, "CHECKLIST_CHANGED_DURING_READ")
    checklist = json_object(raw)
    historical = []
    for name, record in checklist["evidence"].items():
        if "runtime-observation" not in name:
            continue
        evidence = safe_read(root, record["path"])
        require(hashlib.sha256(evidence).hexdigest() == record["sha256"], "EVIDENCE_CHANGED_DURING_READ")
        value = json_object(evidence)
        stamp = value.get("observed_utc", value.get("observed_at_utc"))
        if stamp is None:
            continue
        item = {"provenance": "HISTORICAL", "evidence_path": record["path"],
                "evidence_sha256": record["sha256"], **age(stamp, at)}
        for output, names in (("wolo_checkout_sha", ("wolo_source_commit", "vps_checkout")),
                              ("hd_source_sha", ("hd_source_commit",))):
            v = next((value[k] for k in names if k in value), None)
            if v is not None:
                require(valid_sha(v), "RECORDED_SOURCE_IDENTITY_INVALID")
                item[output] = v
        build = value.get("hd_build_id")
        if build is not None:
            require(type(build) is str and LABEL.fullmatch(build), "RECORDED_BUILD_ID_INVALID")
            item["hd_build_id"] = build
        processes = value.get("processes", {})
        services = {}
        for name in ("wolochain-mainnet-settlement.service", "wolochain-founder-rewards-settlement.service",
                     "wolochaind-mainnet.service"):
            if name not in processes:
                continue
            row = processes[name]
            require(type(row) is dict and valid_sha(row.get("executable_sha256"), DIGEST)
                    and row.get("active") in {"active", "inactive", "failed", "unknown"},
                    "RECORDED_EXECUTABLE_IDENTITY_INVALID")
            services[name] = {"state": row["active"], "executable_sha256": row["executable_sha256"]}
        if services:
            item["wolo_services"] = services
        historical.append(item)
    observed = None
    if operator_observation is not None:
        packet = private_operator_packet(operator_observation)
        observed = {k: v for k, v in packet.items() if k != "schema"}
        observed.update(provenance="OPERATOR_REPORTED", **age(packet["observed_at_utc"], at))
    controls = [{"id": name, "status": row["status"], "severity": "P0",
                 "owner": CONTROL_OWNERS[name], "evidence_refs": row["evidence"],
                 "unknown_count": len(row["unknowns"])}
                for name, row in sorted(checklist["controls"].items())]
    return {"schema": SCHEMA, "generated_at_utc": at.isoformat(), "status": "HOLD",
            "role": "READ_ONLY_PROJECTION_NOT_A_READINESS_REGISTRY_OR_PERMIT",
            "canonical_authority": {"issue": "https://github.com/Emaren/wolochain/issues/5",
                "path": INDEX, "sha256": hashlib.sha256(raw).hexdigest(),
                "provenance": "HISTORICAL", "updated_at_utc": checklist.get("updated_at_utc")},
            "github": github_sources(at) if refresh_github else {"status": "NOT_REFRESHED"},
            "recorded_runtime": sorted(historical, key=lambda r: r["observed_at_utc"]),
            "operator_observation": observed, "controls": controls,
            "financial_evidence_gaps": [{"id": key, "owner": owner, "status": state,
                "required_evidence": evidence, "provenance": "INFERRED"} for key, owner, state, evidence in GAPS],
            "financial_totals": {k: None for k in ("authenticated_height", "bank_assets", "nonoverlapping_hd_liabilities",
                "legacy_uncertain_exposure", "reserve_required", "solvency_surplus_or_deficit")},
            "global_solvency": "UNKNOWN", "custody_capability": "UNAVAILABLE",
            "quarantine": ["original_accepted_100_wolo", "founder_claim_889", "refund_8477",
                           "reused_payout_hash_references", "ambiguous_founder_pairs"],
            "external_health": {"general_inspections": "UNKNOWN", "kingdom_intelligence": "UNKNOWN",
                                "kingdom_index_current_certified_grades": None},
            "financial_release_authorized": False, "website_release_authorized": False,
            "production_mutated": False, "wallet_accessed": False, "nonce_consumed": False,
            "next": "Complete independent evidence and recovery engineering; do not issue live finance or capture approval from this projection."}

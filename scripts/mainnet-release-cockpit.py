#!/usr/bin/env python3
"""Read-only Wolo legacy settlement cockpit. No financial or release authority.

Run on the authorized Wolo VPS. Missing privileges yield UNVERIFIED, never PASS.
The historical executable hashes prove continuity only, not source provenance.
"""
from __future__ import annotations

import argparse
import json
import os
import stat
from datetime import datetime, timezone
import re
import subprocess

SOURCE = "/var/www/WoloChain-wolo-1"
HISTORICAL_SOURCE = "78c25985420ee41a6678c42fab8ea8d6c3b1b519"
HISTORICAL_SETTLEMENT = "040126a2884946caf1651a50b7d8115c5a6fb2d5aa94fcbbe150694602d451a5"
HISTORICAL_CONSENSUS = "4b77f622191db7550cb87cafb8f1886a0aadebee3eb6565f9f90036f809e61d3"
SERVICES = {
    "wolochain-mainnet-settlement.service": HISTORICAL_SETTLEMENT,
    "wolochain-founder-rewards-settlement.service": HISTORICAL_SETTLEMENT,
    "wolochaind-mainnet.service": HISTORICAL_CONSENSUS,
}
TIMERS = (
    "aoe2hdbets-bet-stake-reconcile.timer",
    "aoe2hdbets-challenge-reconcile.timer",
    "aoe2hdbets-replay-auto-recovery.timer",
    "aoe2hdbets-staking-rewards.timer",
    "aoe2hdbets-trophy-tributes.timer",
    "aoe2-wolo-transfer-heartbeat.timer",
)
GATES = (
    "hd_de_producers_isolated",
    "inflight_requests_and_accepted_tx_reconciled",
    "claim_889_liability_preserved_and_release_reviewed",
    "fresh_quiesced_backup_hash_verified",
    "reviewed_code_only_rollback_rehearsed",
    "bank_solvent_and_independently_checked",
)
SHA = re.compile(r"^[0-9a-f]{64}$")
GIT = re.compile(r"^[0-9a-f]{40}$")
MAX_RECEIPT_BYTES = 512 * 1024
INTAKE_SCHEMA = "wolo.mainnet.independent-review-intake.v1"
REVIEWER_ROLES = ("owner", "chain_reviewer", "finance_reviewer", "recovery_witness")
REVIEW_EVIDENCE = (
    "external_historical_header_sha256",
    "external_validator_set_sha256",
    "independent_tx_100_effects_sha256",
    "independent_claim_889_disposition_sha256",
    "complete_nonoverlapping_bank_liabilities_sha256",
    "hd_de_external_producer_fence_scope_sha256",
    "fresh_quiesced_backup_receipt_sha256",
    "witnessed_paired_recovery_receipt_sha256",
)


def command(args: list[str]) -> str | None:
    """Allowlisted caller arguments; never shell, secret files or command output errors."""
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=15, check=False)
        return result.stdout.strip() if result.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def props(unit: str, names: tuple[str, ...]) -> dict[str, str]:
    raw = command(["systemctl", "show", unit, "--no-pager", *["--property=" + x for x in names]])
    if raw is None:
        return {}
    result: dict[str, str] = {}
    for line in raw.splitlines():
        key, sep, value = line.partition("=")
        if sep and key in names:
            result[key] = value
    return result


def executable_digest(pid: str) -> str | None:
    if not pid.isdecimal() or int(pid) <= 0:
        return None
    value = command(["sha256sum", f"/proc/{pid}/exe"])
    if not value:
        return None
    digest = value.split(maxsplit=1)[0]
    return digest if SHA.fullmatch(digest) else None


def observe_service(unit: str, expected_sha: str) -> dict:
    names = ("ActiveState", "MainPID", "ExecMainStartTimestampMonotonic")
    first = props(unit, names)
    pid = first.get("MainPID", "")
    digest = executable_digest(pid) if first.get("ActiveState") == "active" else None
    last = props(unit, names)
    stable = bool(first and first == last and pid.isdecimal() and int(pid) > 0)
    verdict = (
        "UNVERIFIED" if not stable or digest is None else
        "MATCH_HISTORICAL" if digest == expected_sha else "DIFFERENT_FROM_HISTORICAL"
    )
    return {
        "activeState": first.get("ActiveState", "UNAVAILABLE"),
        "pid": int(pid) if pid.isdecimal() and int(pid) > 0 else None,
        "processStable": stable,
        "executableSha256": digest if stable else None,
        "historicalComparison": verdict,
    }


def observe_timer(unit: str) -> dict:
    p = props(unit, ("ActiveState", "Unit", "LastTriggerUSec", "NextElapseUSecRealtime"))
    return {
        "activeState": p.get("ActiveState", "UNAVAILABLE"),
        "triggers": p.get("Unit") or "UNAVAILABLE",
        "lastTrigger": p.get("LastTriggerUSec") or "UNAVAILABLE",
        "nextCalendar": p.get("NextElapseUSecRealtime") or None,
    }


def load_bounded_json(path: str) -> dict:
    """Read at most 512 KiB; reject symlinks/nonregular files and malformed JSON."""
    # An attacker-provided FIFO would block in open() before fstat can reject
    # it. O_NONBLOCK makes the descriptor acquisition fail-closed for pipes,
    # while leaving regular file reads unchanged.
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0))
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_RECEIPT_BYTES:
            raise ValueError("not a bounded regular evidence file")
        with os.fdopen(fd, "rb", closefd=False) as stream:
            data = stream.read(MAX_RECEIPT_BYTES + 1)
        if len(data) > MAX_RECEIPT_BYTES:
            raise ValueError("evidence exceeds 512 KiB")
    finally:
        os.close(fd)
    try:
        result = json.loads(data.decode("utf-8"))
    except RecursionError as exc:
        # Deep nesting must be INVALID_INPUT, never an uncaught cockpit crash.
        raise ValueError("evidence JSON nesting exceeds parser limits") from exc
    if not isinstance(result, dict):
        raise ValueError("evidence root is not an object")
    return result


def write_new_receipt(path: str, data: str) -> None:
    """Create one private immutable-named receipt; never truncate an existing file."""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                 getattr(os, "O_NOFOLLOW", 0), 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        stream.write(data)


def gate_source_details(path: str | None) -> dict:
    """Observational evidence board; displayed source actions are NEVER executable grants."""
    unavailable = {
        gate: {
            "status": "UNVERIFIED",
            "sourceObservedAtUtc": None,
            "sourceReportedNextAction": None,
            "sourceReportedRequiresProductionApproval": None,
        }
        for gate in GATES
    }
    if not path:
        return unavailable
    try:
        payload = load_bounded_json(path)
        if payload.get("schema") != "aoe2war.wolo.financial-release-checklist.v1":
            return unavailable
        controls = payload.get("controls")
        if not isinstance(controls, dict):
            return unavailable
    except (OSError, ValueError, UnicodeError, TypeError, AttributeError):
        return unavailable

    result = {}
    for gate in GATES:
        ctrl = controls.get(gate)
        if not isinstance(ctrl, dict):
            result[gate] = unavailable[gate]
            continue
        status = ctrl.get("status")
        if status not in ("BLOCKED", "UNKNOWN", "ATTESTED"):
            status = "UNVERIFIED"
        reported = ctrl.get("observed_at_utc")
        if not isinstance(reported, str) or len(reported) > 48:
            reported = None
        else:
            try:
                moment = datetime.fromisoformat(reported.replace("Z", "+00:00"))
                if moment.utcoffset() is None:
                    reported = None
            except ValueError:
                reported = None
        action = ctrl.get("next_action")
        if not isinstance(action, str) or len(action) > 750 or any(
            ord(char) < 32 for char in action
        ):
            action = None
        approval = ctrl.get("requires_production_approval")
        result[gate] = {
            "status": status,
            "sourceObservedAtUtc": reported,
            "sourceReportedNextAction": action,
            "sourceReportedRequiresProductionApproval": approval
            if isinstance(approval, bool) else None,
        }
    return result


def read_gate_index(path: str | None) -> dict:
    """Backwards-compatible statuses from the NONAUTHORITATIVE source ledger."""
    return {key: value["status"] for key, value in gate_source_details(path).items()}

def reviewer_intake_template() -> dict:
    """Only evidence fingerprints and independent reviewer IDs, never secrets."""
    return {
        "schema": INTAKE_SCHEMA,
        "reviewers": {role: {"identity_sha256": None} for role in REVIEWER_ROLES},
        "evidence": {name: None for name in REVIEW_EVIDENCE},
        "historical_chain_id": "wolo-1",
        "historical_tx_height": 1078913,
        "maintenance_window_start_utc": None,
        "maintenance_window_end_utc": None,
    }


def parse_utc_window(value: object) -> datetime | None:
    """Require explicit UTC Z and second resolution, never infer local timezone."""
    if not isinstance(value, str) or not re.fullmatch(
        r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", value
    ):
        return None
    try:
        moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return moment if moment.utcoffset().total_seconds() == 0 else None
    except (ValueError, OverflowError):
        return None


def review_intake(path: str | None) -> dict:
    """Presence checks for the independent review HANDOFF ONLY, never a permit.

    The submitted fingerprints can be forged and are not signature or chain
    verification. No content, names, keys, receipts or private path is printed.
    """
    expected = reviewer_intake_template()
    missing = []
    conflicts = []
    supplied = 0
    total = len(REVIEWER_ROLES) + len(REVIEW_EVIDENCE) + 1
    result = {
        "classification": "NOT_PROVIDED",
        "submissionProgress": {"submitted": 0, "expected": total},
        "missing": [],
        "conflicts": [],
        "authority": "UNVERIFIED_INDEPENDENT_REVIEWER_INTAKE_ONLY",
        "historicalChainVerified": False,
        "historicalBankEffectsVerified": False,
        "maintenanceApproved": False,
        "financialReleaseAuthorized": False,
    }
    if path is None:
        result["missing"] = [f"reviewers.{key}.identity_sha256" for key in REVIEWER_ROLES] + [
            f"evidence.{key}" for key in REVIEW_EVIDENCE
        ] + ["maintenance_window_start_utc+end_utc"]
        return result
    try:
        packet = load_bounded_json(path)
    except (OSError, ValueError, TypeError, UnicodeError):
        return {**result, "classification": "INVALID_INTAKE", "conflicts": ["INTAKE_UNREADABLE_OR_INVALID"]}
    if packet.get("schema") != INTAKE_SCHEMA:
        return {**result, "classification": "INVALID_INTAKE", "conflicts": ["UNSUPPORTED_SCHEMA"]}
    if packet.get("historical_chain_id") != "wolo-1" or (
        packet.get("historical_tx_height") != 1078913
        or isinstance(packet.get("historical_tx_height"), bool)
    ):
        conflicts.append("HISTORICAL_CHAIN_OR_HEIGHT_MISMATCH")
    reviewers = packet.get("reviewers")
    reviewers = reviewers if isinstance(reviewers, dict) else {}
    identities = []
    for role in REVIEWER_ROLES:
        row = reviewers.get(role)
        value = row.get("identity_sha256") if isinstance(row, dict) else None
        if isinstance(value, str) and SHA.fullmatch(value):
            supplied += 1
            identities.append(value)
        else:
            missing.append(f"reviewers.{role}.identity_sha256")
    if len(identities) != len(set(identities)):
        conflicts.append("REVIEWER_IDENTITY_FINGERPRINT_REUSED")
    evidence = packet.get("evidence")
    evidence = evidence if isinstance(evidence, dict) else {}
    for name in REVIEW_EVIDENCE:
        value = evidence.get(name)
        if isinstance(value, str) and SHA.fullmatch(value):
            supplied += 1
        else:
            missing.append(f"evidence.{name}")
    start = parse_utc_window(packet.get("maintenance_window_start_utc"))
    end = parse_utc_window(packet.get("maintenance_window_end_utc"))
    if start is not None and end is not None and (
        0 < (end - start).total_seconds() <= 30 * 60
    ):
        supplied += 1
    else:
        missing.append("maintenance_window_start_utc+end_utc")
        if start is not None and end is not None:
            conflicts.append("MAINTENANCE_WINDOW_NOT_POSITIVE_OR_OVER_30_MIN")
    result["submissionProgress"] = {"submitted": supplied, "expected": total}
    result["missing"] = missing
    result["conflicts"] = conflicts
    result["classification"] = (
        "CONFLICTING_INTAKE" if conflicts else
        "SUBMITTED_UNVERIFIED" if not missing else "INCOMPLETE_INTAKE"
    )
    return result


def assess(checklist: str | None = None, reviewer_packet: str | None = None) -> dict:
    source = command(["git", "-C", SOURCE, "rev-parse", "HEAD"])
    source = source if source and GIT.fullmatch(source) else None
    tracked = command(["git", "-C", SOURCE, "status", "--porcelain", "--untracked-files=no"])
    tracked_state = "UNVERIFIED" if tracked is None else "DIRTY" if tracked else "CLEAN"
    gate_details = gate_source_details(checklist)
    services = {name: observe_service(name, sha) for name, sha in SERVICES.items()}
    timers = {name: observe_timer(name) for name in TIMERS}
    observed = [v["historicalComparison"] for v in services.values()]
    continuity = (
        "DIFFERENT_FROM_HISTORICAL" if "DIFFERENT_FROM_HISTORICAL" in observed else
        "UNVERIFIED" if "UNVERIFIED" in observed else "MATCH_HISTORICAL_ONLY"
    )
    armed = sorted(name for name, value in timers.items() if value["activeState"] == "active")
    unknown_timers = sorted(name for name, value in timers.items()
                            if value["activeState"] not in ("active", "inactive"))
    return {
        "schema": "wolo.mainnet.release-cockpit.readonly.v1",
        "observedAtUtc": datetime.now(timezone.utc).isoformat(),
        "sourceCheckout": source,
        "sourceTrackedWorktreeState": tracked_state,
        "historicalCheckoutComparison": "MATCH" if source == HISTORICAL_SOURCE else
            "UNVERIFIED" if source is None else "DIFFERENT",
        "runtimeContinuity": continuity,
        "services": services,
        "financialTimers": timers,
        "activeFinancialTimers": armed,
        "unverifiedTimerUnits": unknown_timers,
        "financialProducerIsolation": "NOT_FENCED" if armed else "UNVERIFIED_NOT_CERTIFIED",
        "canonicalGateIndexSnapshot": {
            name: detail["status"] for name, detail in gate_details.items()
        },
        "sourceReportedGateDetails": gate_details,
        "unresolvedSourceReportedGateActions": [
            {"gate": name, **detail}
            for name, detail in gate_details.items()
            if detail["status"] != "ATTESTED"
        ],
        "unresolvedSourceReportedGateCount": sum(
            detail["status"] != "ATTESTED" for detail in gate_details.values()
        ),
        "gateIndexProvenance": checklist or "NOT_PROVIDED",
        "gateIndexTrust": "UNAUTHENTICATED_SOURCE_REPORT_NOT_RELEASE_APPROVAL",
        "independentReviewIntake": review_intake(reviewer_packet),
        "financialReleaseAuthorized": False,
        "custodyCertified": False,
        "mainnetCanaryAuthorized": False,
        "conclusion": "FINANCIAL_HARD_HOLD",
        "limitations": "Historical executable matches are not build/source provenance, bank finality, solvency, or independent operator approval. Timer state cannot prove complete producer isolation. Gate index is source-reported, not independently attested.",
    }


def delta(prior: dict, current: dict) -> list[str]:
    """Review-only differences; a missing prior observation never means safe."""
    changes = []
    if prior.get("sourceCheckout") != current["sourceCheckout"]:
        changes.append("SOURCE_CHECKOUT_CHANGED")
    if prior.get("sourceTrackedWorktreeState") != current["sourceTrackedWorktreeState"]:
        changes.append("TRACKED_SOURCE_WORKTREE_CHANGED_OR_UNVERIFIED")
    for name in SERVICES:
        a, b = prior.get("services", {}).get(name, {}), current["services"][name]
        if a.get("executableSha256") != b["executableSha256"]:
            changes.append("EXECUTABLE_CHANGED_OR_UNAVAILABLE:" + name)
        if a.get("pid") != b["pid"] or a.get("activeState") != b["activeState"]:
            changes.append("SERVICE_PROCESS_OR_STATE_CHANGED:" + name)
    for name in TIMERS:
        a, b = prior.get("financialTimers", {}).get(name, {}), current["financialTimers"][name]
        if a.get("activeState") != b["activeState"] or a.get("triggers") != b["triggers"]:
            changes.append("TIMER_AUTHORITY_CHANGED_OR_UNAVAILABLE:" + name)
    old_intake = prior.get("independentReviewIntake", {})
    new_intake = current["independentReviewIntake"]
    for key in ("classification", "submissionProgress", "missing", "conflicts"):
        if old_intake.get(key) != new_intake[key]:
            changes.append("INDEPENDENT_REVIEW_INTAKE_CHANGED:" + key)
    for gate in GATES:
        if prior.get("canonicalGateIndexSnapshot", {}).get(gate) != current["canonicalGateIndexSnapshot"][gate]:
            changes.append("GATE_INDEX_STATUS_CHANGED_REQUIRES_WITNESS:" + gate)
        a = prior.get("sourceReportedGateDetails", {}).get(gate, {})
        b = current["sourceReportedGateDetails"][gate]
        if a.get("sourceReportedNextAction") != b["sourceReportedNextAction"] or (
            a.get("sourceObservedAtUtc") != b["sourceObservedAtUtc"]
        ):
            changes.append("GATE_SOURCE_EVIDENCE_OR_ACTION_CHANGED_REVIEW:" + gate)
    return changes



def render_brief(snapshot: dict) -> str:
    """A bounded human triage view of existing READ-ONLY observations.

    Deliberately excludes source-supplied next-action text, receipt paths,
    reviewer IDs and evidence digests. It must never translate an index status,
    absence of active timers, or intake submission into release authority.
    """
    gates = snapshot.get("canonicalGateIndexSnapshot", {})
    gates = gates if isinstance(gates, dict) else {}
    intake = snapshot.get("independentReviewIntake", {})
    intake = intake if isinstance(intake, dict) else {}
    progress = intake.get("submissionProgress", {})
    progress = progress if isinstance(progress, dict) else {}
    valid_statuses = {"BLOCKED", "UNKNOWN", "UNVERIFIED", "ATTESTED"}
    rows = ["WOLO MAINNET — READ-ONLY RELEASE FRONTIER",
            "FINANCIAL_HARD_HOLD | CUSTODY UNAVAILABLE | NO RELEASE AUTHORITY",
            "Gate labels are UNAUTHENTICATED SOURCE REPORTS, not attestations.",
            ""]
    state = snapshot.get("sourceTrackedWorktreeState")
    state = state if state in ("CLEAN", "DIRTY") else "UNVERIFIED"
    revision = snapshot.get("sourceCheckout")
    revision = revision[:12] if isinstance(revision, str) and GIT.fullmatch(revision) else "UNVERIFIED"
    rows.append(f"Source: {revision} | tracked worktree: {state}")
    continuity = snapshot.get("runtimeContinuity")
    if continuity not in ("MATCH_HISTORICAL_ONLY", "DIFFERENT_FROM_HISTORICAL", "UNVERIFIED"):
        continuity = "UNVERIFIED"
    rows.append(f"Historical runtime comparison: {continuity} (not code certification)")
    armed = snapshot.get("activeFinancialTimers")
    unknown = snapshot.get("unverifiedTimerUnits")
    armed = len(armed) if isinstance(armed, list) else "UNVERIFIED"
    unknown = len(unknown) if isinstance(unknown, list) else "UNVERIFIED"
    rows.append(f"Financial timers: active={armed}, unverified={unknown}; this never certifies a full producer fence")
    rows.append("")
    rows.append("SOURCE-REPORTED FINANCIAL GATES:")
    for gate in GATES:
        status = gates.get(gate, "UNVERIFIED")
        if status not in valid_statuses:
            status = "UNVERIFIED"
        rows.append(f"  {status:10s} {gate}")
    rows.append("")
    classification = intake.get("classification")
    if classification not in (
        "NOT_PROVIDED", "INVALID_INTAKE", "INCOMPLETE_INTAKE",
        "CONFLICTING_INTAKE", "SUBMITTED_UNVERIFIED"
    ):
        classification = "UNVERIFIED"
    supplied = progress.get("submitted")
    expected = progress.get("expected")
    # Never trust bool as a numeric progress counter from an external snapshot.
    if type(supplied) is not int or type(expected) is not int or supplied < 0 or expected < 0 or supplied > expected:
        supplied, expected = "?", "?"
    missing = intake.get("missing")
    conflicts = intake.get("conflicts")
    missing_count = len(missing) if isinstance(missing, list) else "?"
    conflict_count = len(conflicts) if isinstance(conflicts, list) else "?"
    rows.append(f"Independent-review intake: {classification}; fingerprints {supplied}/{expected}; missing={missing_count}; conflicts={conflict_count}")
    rows.append("Fingerprints are NOT signatures, authenticated proofs, approvals, or custody.")
    changes = snapshot.get("changesSincePrevious")
    if changes is None:
        rows.append("Changes since previous: NOT CHECKED (supply --previous)")
    elif not isinstance(changes, list) or not all(isinstance(s, str) for s in changes):
        rows.append("Changes since previous: UNVERIFIED")
    elif changes == ["PREVIOUS_SNAPSHOT_UNAVAILABLE"]:
        rows.append("Changes since previous: PREVIOUS_SNAPSHOT_UNAVAILABLE")
    elif not changes:
        rows.append("Changes since previous: NONE OBSERVED (not evidence of financial safety)")
    else:
        rows.append(f"Changes since previous: {len(changes)} review item(s)")
        # Only emit contract-defined delta labels; never print arbitrary
        # untrusted previous-snapshot strings or source-reported action text.
        prefixes = (
            "SOURCE_CHECKOUT_CHANGED",
            "TRACKED_SOURCE_WORKTREE_CHANGED_OR_UNVERIFIED",
            "EXECUTABLE_CHANGED_OR_UNAVAILABLE:",
            "SERVICE_PROCESS_OR_STATE_CHANGED:",
            "TIMER_AUTHORITY_CHANGED_OR_UNAVAILABLE:",
            "INDEPENDENT_REVIEW_INTAKE_CHANGED:",
            "GATE_INDEX_STATUS_CHANGED_REQUIRES_WITNESS:",
            "GATE_SOURCE_EVIDENCE_OR_ACTION_CHANGED_REVIEW:",
        )
        safe_names = set(SERVICES) | set(TIMERS) | set(GATES)
        for item in changes:
            safe = item in prefixes[:2] or (
                any(item == prefix + name for prefix in prefixes[2:5] for name in safe_names)
                or any(item == prefix + name for prefix in prefixes[6:] for name in GATES)
                or item in {
                    "INDEPENDENT_REVIEW_INTAKE_CHANGED:classification",
                    "INDEPENDENT_REVIEW_INTAKE_CHANGED:submissionProgress",
                    "INDEPENDENT_REVIEW_INTAKE_CHANGED:missing",
                    "INDEPENDENT_REVIEW_INTAKE_CHANGED:conflicts",
                }
            )
            rows.append("  " + (item if safe else "UNVERIFIED_DELTA_ITEM"))
    rows.extend(("", "Verdict: FINANCIAL_HARD_HOLD. Separate financial/chain/recovery approvals required."))
    return "\n".join(rows) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gate-index", help="Optional canonical financial-release-checklist.json; NEVER a permit")
    parser.add_argument("--reviewer-intake", help="Optional private reviewer/checkpoint/maintenance fingerprint index; never an approval")
    parser.add_argument("--print-reviewer-intake-template", action="store_true", help="Print empty private packet template; do not fill in public GitHub")

    parser.add_argument("--previous", help="Optional previous cockpit JSON for observed delta")
    parser.add_argument("--output", help="Optional path to save local JSON evidence; no default write")
    parser.add_argument("--brief", action="store_true", help="Print sanitized operator summary of existing read-only observations; still exits HOLD (3)")
    args = parser.parse_args(argv)
    if args.print_reviewer_intake_template:
        print(json.dumps(reviewer_intake_template(), indent=2, sort_keys=True))
        return 3
    result = assess(args.gate_index, args.reviewer_intake)
    if args.previous:
        try:
            previous = load_bounded_json(args.previous)
            if previous.get("schema") != result["schema"]:
                raise ValueError("invalid prior schema")
            result["changesSincePrevious"] = delta(previous, result)
        except (OSError, ValueError, UnicodeError, TypeError, AttributeError):
            result["changesSincePrevious"] = ["PREVIOUS_SNAPSHOT_UNAVAILABLE"]
    raw = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        try:
            write_new_receipt(args.output, raw)
        except OSError as exc:
            parser.error(f"private output receipt unavailable: {exc.strerror or type(exc).__name__}")
    print(render_brief(result) if args.brief else raw, end="")
    return 3  # Read-only observation complete, financial release deliberately HELD.


if __name__ == "__main__":
    raise SystemExit(main())

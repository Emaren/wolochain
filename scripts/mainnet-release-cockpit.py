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
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
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
    result = json.loads(data.decode("utf-8"))
    if not isinstance(result, dict):
        raise ValueError("evidence root is not an object")
    return result


def write_new_receipt(path: str, data: str) -> None:
    """Create one private immutable-named receipt; never truncate an existing file."""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                 getattr(os, "O_NOFOLLOW", 0), 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        stream.write(data)


def read_gate_index(path: str | None) -> dict:
    if not path:
        return {gate: "UNVERIFIED" for gate in GATES}
    try:
        payload = load_bounded_json(path)
        if payload.get("schema") != "aoe2war.wolo.financial-release-checklist.v1":
            raise ValueError("wrong schema")
        controls = payload["controls"]
        return {gate: controls[gate]["status"] if controls[gate]["status"] in
                ("BLOCKED", "UNKNOWN", "ATTESTED") else "UNVERIFIED" for gate in GATES}
    except (OSError, ValueError, UnicodeError, TypeError, KeyError, AttributeError):
        return {gate: "UNVERIFIED" for gate in GATES}


def assess(checklist: str | None = None) -> dict:
    source = command(["git", "-C", SOURCE, "rev-parse", "HEAD"])
    source = source if source and GIT.fullmatch(source) else None
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
        "historicalCheckoutComparison": "MATCH" if source == HISTORICAL_SOURCE else
            "UNVERIFIED" if source is None else "DIFFERENT",
        "runtimeContinuity": continuity,
        "services": services,
        "financialTimers": timers,
        "activeFinancialTimers": armed,
        "unverifiedTimerUnits": unknown_timers,
        "financialProducerIsolation": "NOT_FENCED" if armed else "UNVERIFIED_NOT_CERTIFIED",
        "canonicalGateIndexSnapshot": read_gate_index(checklist),
        "gateIndexProvenance": checklist or "NOT_PROVIDED",
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
    for gate in GATES:
        if prior.get("canonicalGateIndexSnapshot", {}).get(gate) != current["canonicalGateIndexSnapshot"][gate]:
            changes.append("GATE_INDEX_STATUS_CHANGED_REQUIRES_WITNESS:" + gate)
    return changes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gate-index", help="Optional canonical financial-release-checklist.json; NEVER a permit")
    parser.add_argument("--previous", help="Optional previous cockpit JSON for observed delta")
    parser.add_argument("--output", help="Optional path to save local JSON evidence; no default write")
    args = parser.parse_args(argv)
    result = assess(args.gate_index)
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
    print(raw, end="")
    return 3  # Read-only observation complete, financial release deliberately HELD.


if __name__ == "__main__":
    raise SystemExit(main())

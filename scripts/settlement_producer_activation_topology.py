#!/usr/bin/env python3
"""Fail-closed read-only systemd activation topology for shared HD/DE finances.

Only whitelisted unit names and whitelisted unit-property values are displayed.
Never reads Environment, EnvironmentFiles, ExecStart, credentials, process argv,
private paths, wallet, requests, or state. Never starts/stops/reloads any unit.
Not a proof of all financial writers or maintenance authorization.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import re
import subprocess
import sys

SCHEMA = "wolo.financial.producer-activation-topology.v1"
PREFIXES = ("aoe2hdbets-", "aoe2dewarwagers-", "aoe2war-", "aoe2-wolo-")
PROTECTED = (
    "wolochaind-mainnet.service",
    "wolochain-mainnet-settlement.service",
    "wolochain-founder-rewards-settlement.service",
)
UNIT = re.compile(r"[a-zA-Z0-9_.@:-]{1,120}\.(?:service|timer)\Z")
EDGE = re.compile(r"[a-zA-Z0-9_.@:\\-]{1,160}\.(?:service|timer|target|socket|mount|path|slice|scope|device|automount|swap)\Z")
STATES = frozenset({
    "active", "inactive", "failed", "activating", "deactivating",
    "reloading", "maintenance", "unknown", "not-found", "loaded", "masked",
    "static", "enabled", "disabled", "indirect", "generated", "transient",
    "linked", "linked-runtime", "enabled-runtime", "masked-runtime",
})
RELATIONS = ("Triggers", "TriggeredBy", "PartOf", "Requires", "Wants", "OnFailure")
PROPS = ("Id", "LoadState", "ActiveState", "SubState", "UnitFileState",
         "MainPID", "Restart", *RELATIONS)
MAX_UNITS = 100
MAX_OUTPUT = 96_000
MAX_RELATIONS = 150
MAX_PROP_BYTES = 16_000
EXPECTED = frozenset({
    "aoe2-wolo-transfer-heartbeat.service",
    "aoe2-wolo-transfer-heartbeat.timer",
    "aoe2dewarwagers-api.service",
    "aoe2dewarwagers-web.service",
    "aoe2hdbets-api.service",
    "aoe2hdbets-bet-stake-reconcile-plan.service",
    "aoe2hdbets-bet-stake-reconcile.service",
    "aoe2hdbets-bet-stake-reconcile.timer",
    "aoe2hdbets-challenge-reconcile.service",
    "aoe2hdbets-challenge-reconcile.timer",
    "aoe2hdbets-replay-auto-recovery.service",
    "aoe2hdbets-replay-auto-recovery.timer",
    "aoe2hdbets-staking-rewards.service",
    "aoe2hdbets-staking-rewards.timer",
    "aoe2hdbets-trophy-tributes.service",
    "aoe2hdbets-trophy-tributes.timer",
    "aoe2hdbets-web.service",
    "aoe2war-prewarm.service",
    "aoe2war-prewarm.timer",
})


class TopologyError(ValueError):
    pass


def run(*args: str) -> str:
    try:
        completed = subprocess.run(
            ["systemctl", "--no-pager", *args],
            capture_output=True, text=True, timeout=12, check=False
        )
    except (OSError, subprocess.TimeoutExpired):
        raise TopologyError("SYSTEMD_QUERY_UNAVAILABLE") from None
    if completed.returncode != 0 or len(completed.stdout) > MAX_OUTPUT:
        raise TopologyError("SYSTEMD_QUERY_INCOMPLETE")
    return completed.stdout


def discover(raw: str) -> list[str]:
    names: list[str] = []
    for line in raw.splitlines():
        fields = line.strip().split()
        if not fields:
            continue
        name = fields[0].lstrip("●").strip()
        if not any(name.startswith(p) for p in PREFIXES):
            continue
        if not UNIT.fullmatch(name) or name in names:
            raise TopologyError("UNSAFE_OR_DUPLICATE_FINANCIAL_UNIT")
        names.append(name)
        if len(names) > MAX_UNITS:
            raise TopologyError("UNBOUNDED_FINANCIAL_UNIT_SET")
    return sorted(names)


def parse_show(raw: str, expected: str) -> dict:
    if len(raw) > MAX_PROP_BYTES or not UNIT.fullmatch(expected):
        raise TopologyError("UNSAFE_UNIT_PROPERTIES")
    fields = {}
    for line in raw.splitlines():
        if not line or "=" not in line:
            raise TopologyError("INVALID_UNIT_PROPERTIES")
        key, value = line.split("=", 1)
        if key not in PROPS or key in fields:
            raise TopologyError("UNEXPECTED_UNIT_PROPERTY")
        fields[key] = value
    # MainPID and Restart belong to service units; systemd may omit them
    # entirely for timers. Absence is not proof of an inert timer.
    required = set(PROPS) - {"MainPID", "Restart"}
    if not required.issubset(fields) or fields["Id"] != expected:
        raise TopologyError("INCOMPLETE_OR_WRONG_UNIT")
    if fields["LoadState"] not in STATES or fields["ActiveState"] not in STATES:
        raise TopologyError("UNRECOGNIZED_SYSTEMD_STATUS")
    pid = fields.get("MainPID", "")
    if pid and not pid.isdecimal():
        raise TopologyError("INVALID_PID")
    if expected.endswith(".service") and not pid:
        raise TopologyError("SERVICE_PID_UNOBSERVED")
    # SubState/UnitFileState/Restart are never printed verbatim, so unusual
    # values cannot smuggle sensitive strings into the redacted report.
    edges: dict[str, list[str]] = {}
    for rel in RELATIONS:
        raw_values = fields[rel].split()
        if len(raw_values) > MAX_RELATIONS or any(not EDGE.fullmatch(x) for x in raw_values):
            raise TopologyError("INVALID_RELATION_NAMES")
        if len(set(raw_values)) != len(raw_values):
            raise TopologyError("DUPLICATED_RELATION")
        edges[rel] = sorted(raw_values)
    return {
        "unit": expected, "activeObserved": fields["ActiveState"] == "active",
        "loadedObserved": fields["LoadState"] == "loaded",
        "mainPidPresent": int(pid or "0") > 0,
        "unitType": "timer" if expected.endswith(".timer") else "service",
        "restartConfigured": fields.get("Restart", "") not in ("", "no"),
        "relations": edges,
        "owner": "DE" if expected.startswith("aoe2dewarwagers-") else "HD_OR_SHARED",
        "sourceRuntimeParityProven": False,
        "paymentCapabilityExcluded": False,
        "safeToStop": False,
    }


def topology(discovered: list[str], observations: list[dict],
             observed_at: datetime | None = None) -> dict:
    if len(discovered) != len(observations) or not discovered or len(discovered) > MAX_UNITS:
        raise TopologyError("INCOMPLETE_TOPOLOGY")
    unit_names = [o.get("unit") for o in observations if isinstance(o, dict)]
    if unit_names != discovered or any(not UNIT.fullmatch(name) for name in discovered):
        raise TopologyError("TOPOLOGY_IDENTITY_CHANGED")
    name_set = set(unit_names)
    if len(name_set) != len(discovered):
        raise TopologyError("DUPLICATE_TOPOLOGY")
    triggers = sorted({
        target
        for o in observations
        for rel in ("Triggers", "TriggeredBy", "PartOf", "Requires", "Wants")
        for target in o["relations"][rel]
        if target in name_set
    })
    active_timers = sorted(o["unit"] for o in observations
                           if o["unitType"] == "timer" and o["activeObserved"])
    unknown = sorted(name_set - EXPECTED)
    missing = sorted(EXPECTED - name_set)
    return {
        "schema": SCHEMA,
        "observedAtUtc": (observed_at or datetime.now(timezone.utc)).astimezone(
            timezone.utc).isoformat(),
        "mode": "READ_ONLY_UNAUTHORIZED_TOPOLOGY_EVIDENCE",
        "status": "HOLD",
        "unitsObserved": len(discovered),
        "activeTimerUnits": active_timers,
        "knownActivationGraphUnitNames": triggers,
        "newOrUnmappedUnits": unknown,
        "expectedAbsentUnitNames": missing,
        "units": observations,
        "cronUserContainersAndExternalSignersCovered": False,
        "financialIngressFenced": False,
        "paymentsReconciled": False,
        "independentBankSolvencyProven": False,
        "protectedWoloUnitsAlwaysExcluded": list(PROTECTED),
        "systemdMutationsPerformed": False,
        "cutoverAuthorized": False,
        "satchelActivationAuthorized": False,
        "note": "Observed dependency names are not authorization to stop timers or apps.",
    }


def inspect() -> dict:
    raw = run("list-units", "--all", "--type=service", "--type=timer",
              "--no-legend", "--plain")
    names = discover(raw)
    observations = []
    for name in names:
        lines = run("show", "--property=" + ",".join(PROPS), name)
        observations.append(parse_show(lines, name))
    return topology(names, observations)


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if args not in ([], ["--inspect"]):
        print("BLOCKED: this is read-only --inspect only", file=sys.stderr)
        return 2
    try:
        result = inspect()
    except (TopologyError, OSError, ValueError):
        print(json.dumps({"status":"STOP","cutoverAuthorized":False,
                          "reason":"INCOMPLETE_OR_UNSAFE_SYSTEMD_TOPOLOGY"},sort_keys=True))
        return 2
    print(json.dumps(result,sort_keys=True,indent=2))
    return 3  # Observed dependency graph is not writer isolation proof.


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Read-only shared WOLO settlement writer candidate inventory for HD and DE.

Reports systemd unit NAMES, active state, PID presence, and allowlisted
environment KEY NAMES only. Never prints environment values, credentials,
wallets, DB URLs, signer locations, request records, or private file paths.

The script cannot prove that an omitted/idle/external writer is inert.
No service stop, restart, app modification, financial action or approval exists.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import sys

NAME = re.compile(r"^[A-Za-z0-9_.@:-]+\.(?:service|timer)$")
APP_PREFIXES = ("aoe2hdbets-", "aoe2war-", "aoe2dewarwagers-", "aoe2-wolo-")
EXACT_APP = {
    "aoe2hdbets-web.service",
    "aoe2hdbets-api.service",
    "aoe2dewarwagers-web.service",
    "aoe2dewarwagers-api.service",
    "aoe2hdbets.timer",
    "aoe2hdbets.service",
    "aoe2war.timer",
    "aoe2war.service",
}
PROTECTED_WOLO = {
    "wolochain-mainnet-settlement.service",
    "wolochain-founder-rewards-settlement.service",
    "wolochaind-mainnet.service",
}
EXPOSED_KEYS = {
    "DATABASE_URL",
    "DIRECT_URL",
    "WOLO_SETTLEMENT_URL",
    "WOLO_SETTLEMENT_AUTH_TOKEN",
    "WOLO_FOUNDER_SETTLEMENT_URL",
    "WOLO_FOUNDER_SETTLEMENT_AUTH_TOKEN",
    "WOLO_INTERNAL_RPC_URL",
    "WOLO_BET_PAYOUT_ADDRESS",
    "WOLO_PAYOUT_MNEMONIC",
    "WOLO_BET_PAYOUT_MNEMONIC",
    "WOLO_STAKING_WALLET_MNEMONIC",
    "WOLO_STAKING_ALLOW_PAYOUT_MNEMONIC_FALLBACK",
    "WOLO_LOCAL_PAYOUT_SIGNER_FALLBACK",
    "WOLO_STAKING_HOME",
    "WOLO_STAKING_CLI",
    "WOLO_STAKING_KEY_NAME",
    "WOLO_FAUCET_HOME",
    "WOLO_FAUCET_CLI",
}
MAX_ENV = 1024 * 1024
MAX_UNITS = 5000


def run_systemctl(args: list[str]) -> str:
    result = subprocess.run(
        ["systemctl", *args, "--no-pager"], timeout=12,
        check=True, capture_output=True, text=True,
    )
    return result.stdout


def relevant(name: str) -> bool:
    return bool(NAME.fullmatch(name) and (
        name in EXACT_APP or any(name.startswith(x) for x in APP_PREFIXES)
    ))


def discover_units() -> list[str]:
    listed = run_systemctl([
        "list-units", "--all", "--type=service", "--type=timer", "--plain", "--no-legend",
    ])
    installed = run_systemctl([
        "list-unit-files", "--type=service", "--type=timer", "--no-legend",
    ])
    names: set[str] = set()
    for payload in (listed, installed):
        lines = payload.splitlines()
        if len(lines) > MAX_UNITS:
            raise ValueError("unit list exceeds bounded limit")
        for line in lines:
            fields = line.strip().split()
            if not fields:
                continue
            name = fields[0]
            if relevant(name):
                names.add(name)
    # Do not invent missing units. systemctl show on fabricated service names
    # can itself fail; log missing exact names separately for operator review.
    return sorted(names)


def process_keys(pid: str) -> tuple[bool, list[str]]:
    if not pid.isdecimal() or int(pid) <= 0:
        return False, []
    path = Path("/proc") / pid / "environ"
    try:
        with path.open("rb") as file:
            data = file.read(MAX_ENV + 1)
    except OSError:
        return False, []
    if len(data) > MAX_ENV:
        return False, []
    found = set()
    for entry in data.split(b"\0"):
        key, sep, value = entry.partition(b"=")
        if not sep or not value.strip():
            continue
        try:
            name = key.decode("ascii")
        except UnicodeDecodeError:
            continue
        if name in EXPOSED_KEYS:
            found.add(name)
    return True, sorted(found)


def info(unit: str) -> dict:
    if not relevant(unit):
        raise ValueError("unit not in HD/DE inventory scope")
    raw = run_systemctl(["show", unit, "-p", "MainPID", "-p", "ActiveState",
                         "-p", "LoadState", "-p", "UnitFileState"])
    fields = dict(line.split("=", 1) for line in raw.splitlines() if "=" in line)
    pid = fields.get("MainPID", "")
    inspectable, keys = process_keys(pid)
    active = fields.get("ActiveState") == "active"
    return {
        "unit": unit,
        "isTimer": unit.endswith(".timer"),
        "active": active,
        "loadState": fields.get("LoadState", "unknown"),
        "unitFileState": fields.get("UnitFileState", "unknown"),
        "mainPidPresent": bool(pid.isdecimal() and int(pid) > 0),
        "processEnvironmentInspectable": inspectable,
        "configuredFinancialKeyNames": keys,
        "isCandidateForExplicitMaintenanceReview": active or bool(keys),
    }


def inspect() -> dict:
    discovered = discover_units()
    units = []
    incomplete_units = []
    for name in discovered:
        try:
            units.append(info(name))
        except (OSError, ValueError, subprocess.SubprocessError):
            # Keep the successful inventory visible but NEVER silently conclude
            # a failed inspection is safe or that a writer is inert.
            incomplete_units.append(name)
    candidates = sorted(
        x["unit"] for x in units if x["isCandidateForExplicitMaintenanceReview"]
    )
    return {
        "mode": "READ_ONLY_SHARED_HD_DE_PAYOUT_INGRESS_INVENTORY",
        "observedAtUtc": datetime.now(timezone.utc).isoformat(),
        "appUnits": units,
        "activeCandidateUnitsToReview": candidates,
        "expectedNamedUnitsNotFound": sorted(EXACT_APP - set(discovered)),
        "unitsWithIncompleteInspection": incomplete_units,
        "inventoryCompleteForDiscoveredUnits": len(incomplete_units) == 0,
        "neverAutomaticStop": sorted(PROTECTED_WOLO),
        "cannotProve": [
            "no external or independently signed payout origin",
            "no unlisted cron, user-level systemd or container writer",
            "no queued transaction, event worker or database-triggered payment",
            "no active HTTP session or future wallet execution",
            "financial drain, reserve solvency, independent chain finality",
        ],
        "financialProducersFenced": False,
        "financialDrainCertified": False,
        "liveRollbackRehearsed": False,
        "productionCutoverAuthorized": False,
        "secretsOrEnvironmentValuesPrinted": False,
        "commandsMutatedServices": False,
    }


def main() -> int:
    if sys.argv[1:] not in ([], ["--inspect"]):
        print("BLOCKED: only read-only --inspect supported", file=sys.stderr)
        return 2
    if os.geteuid() != 0:
        print("BLOCKED: root required to inspect bounded private process metadata",
              file=sys.stderr)
        return 2
    try:
        report = inspect()
    except (ValueError, OSError, subprocess.SubprocessError):
        print("BLOCKED: incomplete systemd unit inventory", file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2))
    if report["unitsWithIncompleteInspection"]:
        print("BLOCKED: some discovered units could not be inspected", file=sys.stderr)
        return 2
    return 3  # deliberately noncertifying even if no units appear active


if __name__ == "__main__":
    raise SystemExit(main())

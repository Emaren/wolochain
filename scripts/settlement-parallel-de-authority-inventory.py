#!/usr/bin/env python3
"""Read-only, intentionally non-certifying inventory of the DE sister site's
WOLO authority on the shared VPS.

Never prints environment values, keyring files, DB URLs, mnemonics, passwords,
token strings, balances, addresses, or wallet home paths. Does not modify
services, repo, app environment, keys, files, or chain.

A process/environment inventory is NOT proof that DE payout operations are
safely drained. The guarded two-service promotion must remain BLOCKED until
DE has its own independently reviewed ingress freeze/resume & signer audit.
"""
import json
import os
import pathlib
import re
import subprocess
import sys
from datetime import datetime, timezone

DE_UNITS = (
    "aoe2dewarwagers-web.service",
    "aoe2dewarwagers-api.service",
)
GROUPS = {
    "signing_secrets": (
        "WOLO_BET_PAYOUT_MNEMONIC",
        "WOLO_STAKING_MNEMONIC",
        "WOLO_FAUCET_MNEMONIC",
        "WOLO_PAYOUT_MNEMONIC",
        "WOLO_LOCAL_PAYOUT_SIGNER_FALLBACK",
    ),
    "external_keyring_signers": (
        "WOLO_STAKING_CLI",
        "WOLO_STAKING_HOME",
        "WOLO_FAUCET_CLI",
        "WOLO_FAUCET_HOME",
    ),
    "remote_settlement_authority": (
        "WOLO_SETTLEMENT_URL",
        "WOLO_SETTLEMENT_AUTH_TOKEN",
        "WOLO_FOUNDER_SETTLEMENT_URL",
        "WOLO_FOUNDER_SETTLEMENT_AUTH_TOKEN",
    ),
    "payout_account_configuration": (
        "WOLO_BET_PAYOUT_ADDRESS",
        "WOLO_STAKING_ADDRESS",
        "WOLO_FAUCET_ADDRESS",
        "WOLO_MAINNET_PAYOUT_ADDRESS",
    ),
    "database_authority": ("DATABASE_URL", "DIRECT_URL"),
}
APP_CONFIGS = (".env.production", ".env.local", ".env", "app/.env.production")
ENV_NAME = re.compile(rb"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=")
MAX_ENV_FILE_BYTES = 256 * 1024
MAX_PROCESS_ENV_BYTES = 1024 * 1024


def configured(raw: bytes) -> bool:
    value = raw.strip()
    return value not in (b"", b"''", b'""')


def parse_process_env(data: bytes) -> set[str]:
    """Read only keys of nonempty variables from a bounded /proc snapshot."""
    result = set()
    for entry in data.split(b"\0"):
        if b"=" not in entry:
            continue
        key, value = entry.split(b"=", 1)
        if re.fullmatch(rb"[A-Za-z_][A-Za-z0-9_]*", key) and configured(value):
            result.add(key.decode("ascii"))
    return result


def parse_dotenv_keys(data: bytes) -> set[str]:
    result = set()
    for raw in data.splitlines():
        match = ENV_NAME.match(raw)
        if not match:
            continue
        rest = raw[match.end():].strip()
        if configured(rest):
            result.add(match.group(1).decode("ascii"))
    return result


def read_bounded(path: pathlib.Path, maximum: int) -> tuple[bytes, bool]:
    with path.open("rb") as handle:
        payload = handle.read(maximum + 1)
    return payload[:maximum], len(payload) > maximum


def service_info(unit: str) -> dict[str, str]:
    r = subprocess.run(
        ["systemctl", "show", unit,
         "-p", "MainPID", "-p", "ActiveState", "-p", "WorkingDirectory",
         "--no-pager"], check=True, capture_output=True, text=True, timeout=8
    )
    fields = dict(line.split("=", 1) for line in r.stdout.splitlines() if "=" in line)
    return {k: fields.get(k, "") for k in ("MainPID", "ActiveState", "WorkingDirectory")}


def summarize_keys(keys: set[str]) -> dict[str, list[str]]:
    """Only the name of an allowlisted config variable can appear here."""
    return {
        group: sorted(k for k in allowlist if k in keys)
        for group, allowlist in GROUPS.items()
    }


def inspect_unit(unit: str) -> dict:
    info = service_info(unit)
    pid = info["MainPID"]
    result = {
        "unit": unit,
        "active": info["ActiveState"] == "active",
        "mainPidPresent": bool(pid.isdecimal() and int(pid) > 0),
        "processEnvInspectable": False,
        "appLocalEnvFilesFound": 0,
        "appLocalEnvFilesUnreadable": 0,
        "appLocalEnvFilesTruncated": False,
        "configurationKeysPresentInProcess": summarize_keys(set()),
        "configurationKeysPresentInAppEnv": summarize_keys(set()),
        "limits": "Startup environment and local dotenv metadata are incomplete evidence; external/keyring signing may still be possible.",
    }
    if result["mainPidPresent"]:
        try:
            data, truncated = read_bounded(
                pathlib.Path("/proc") / pid / "environ", MAX_PROCESS_ENV_BYTES)
            if truncated:
                result["processEnvTruncated"] = True
            else:
                result["processEnvInspectable"] = True
                result["configurationKeysPresentInProcess"] = summarize_keys(
                    parse_process_env(data))
        except (OSError, PermissionError):
            pass
    # Read app-local .env names, never values or contents; do not follow
    # service-provided arbitrary directory into privileged /etc or /proc.
    wd = info["WorkingDirectory"]
    if wd.startswith(("/var/www/", "/srv/")):
        work = pathlib.Path(wd)
        for part in APP_CONFIGS:
            file = work / part
            try:
                if file.is_symlink() or not file.is_file():
                    continue
                result["appLocalEnvFilesFound"] += 1
                data, truncated = read_bounded(file, MAX_ENV_FILE_BYTES)
                if truncated:
                    result["appLocalEnvFilesTruncated"] = True
                    continue
                found = parse_dotenv_keys(data)
                for group, names in summarize_keys(found).items():
                    existing = set(result["configurationKeysPresentInAppEnv"][group])
                    result["configurationKeysPresentInAppEnv"][group] = sorted(
                        existing.union(names))
            except (OSError, PermissionError):
                result["appLocalEnvFilesUnreadable"] += 1
    return result


def de_units_seen() -> list[str]:
    """Names only; never dump unit Environment, ExecStart, or file contents."""
    try:
        p = subprocess.run(
            ["systemctl", "list-units", "--all", "--type=service", "--type=timer",
             "--no-legend", "--no-pager", "--plain"],
            check=True, capture_output=True, text=True, timeout=8
        )
    except (OSError, subprocess.SubprocessError):
        return []
    names = []
    for line in p.stdout.splitlines():
        head = line.strip().split(maxsplit=1)
        if head and "aoe2dewarwagers" in head[0].lower() and (
            head[0].endswith(".service") or head[0].endswith(".timer")
        ):
            names.append(head[0])
    return sorted(set(names))


def main() -> int:
    if os.geteuid() != 0:
        print("BLOCKED: root required for private /proc metadata", file=sys.stderr)
        return 2
    try:
        units = [inspect_unit(name) for name in DE_UNITS]
        other_units = de_units_seen()
    except (OSError, ValueError, subprocess.SubprocessError):
        print("BLOCKED: service metadata unreadable", file=sys.stderr)
        return 2
    output = {
        "observedAtUtc": datetime.now(timezone.utc).isoformat(),
        "mode": "READ_ONLY_PARALLEL_DE_PAYMENT_AUTHORITY_INVENTORY",
        "units": units,
        "deServiceAndTimerNames": other_units,
        "conclusion": "NOT_CERTIFIED_FOR_SHARED_WOLO_SETTLEMENT_DOWNTIME",
        "reason": (
            "Configuration presence/absence cannot attest signer isolation, "
            "all app-loaded dotenvs, active HTTP ingress, queued payouts, "
            "keyring access or transaction-free maintenance."
        ),
        "writesPerformed": False,
        "servicesChanged": False,
        "tokensMoved": False,
        "promotionAuthorized": False,
    }
    print(json.dumps(output, indent=2))
    # Explicitly nonzero even when no configured keys observed.
    return 3


if __name__ == "__main__":
    sys.exit(main())

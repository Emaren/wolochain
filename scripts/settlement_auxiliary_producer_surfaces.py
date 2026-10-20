#!/usr/bin/env python3
"""Root-host read-only inventory of cron/user-systemd/container activation surfaces.

Prints only allowlisted metadata, counts and user-unit/container NAMES.
Cron commands, secrets, process arguments, systemd ExecStart, env values,
container configuration and filesystem contents are NEVER emitted.
An observation returns 3 (HOLD), an invalid/incomplete critical query 2.
No network probes, daemon changes, money movement or database mutations.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import pwd
import re
import stat
import subprocess
import sys

UNIT = re.compile(r"[a-zA-Z0-9_.@:-]{1,120}\.(?:service|timer)\Z")
CONTAINER = re.compile(r"[a-zA-Z0-9_.-]{1,120}\Z")
USER_MANAGER = re.compile(r"user@([0-9]{1,8})\.service\Z")
CRON_FILE = re.compile(r"[a-zA-Z0-9_.-]{1,100}\Z")
ENV_ASSIGN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\s*=")
MONEY_CUE = re.compile(r"wolo|stake|settle|faucet|payout|transfer|bet|treasury|wallet|reward|crypto|chain", re.I)
MAX_BYTES = 131072
MAX_OUTPUT = 96000
MAX_UNITS = 150
MAX_USERS = 20
MAX_FILES = 150


class InventoryError(ValueError):
    pass


def command(args: list[str], *, environment: dict | None = None) -> tuple[int, str]:
    if not args or not all(isinstance(x, str) and x for x in args):
        raise InventoryError("UNSAFE_COMMAND")
    try:
        p = subprocess.run(args, capture_output=True, text=True, timeout=12,
                           check=False, env=environment)
    except (OSError, subprocess.TimeoutExpired, UnicodeError):
        return 127, ""
    if len(p.stdout) > MAX_OUTPUT:
        raise InventoryError("TOO_MUCH_COMMAND_OUTPUT")
    return p.returncode, p.stdout


def unit_names(raw: str) -> list[tuple[str, bool]]:
    found = []
    seen = set()
    for line in raw.splitlines():
        parts = line.strip().lstrip("●").split()
        if not parts or not parts[0].endswith((".service", ".timer")):
            continue
        name = parts[0]
        if not UNIT.fullmatch(name) or name in seen:
            raise InventoryError("UNSAFE_OR_DUPLICATE_UNIT")
        if len(parts) < 3 or parts[2] not in {"active", "inactive", "failed",
                                               "activating", "deactivating",
                                               "reloading", "maintenance"}:
            raise InventoryError("UNKNOWN_UNIT_STATUS")
        seen.add(name)
        found.append((name, parts[2] == "active"))
        if len(found) > MAX_UNITS:
            raise InventoryError("TOO_MANY_UNITS")
    return sorted(found)


def user_managers() -> list[dict]:
    status, raw = command(["systemctl", "--no-pager", "list-units", "--all",
                           "--type=service", "--plain", "--no-legend",
                           "user@*.service"])
    if status:
        raise InventoryError("SYSTEM_USER_MANAGERS_UNOBSERVED")
    managers = []
    for name, active in unit_names(raw):
        matched = USER_MANAGER.fullmatch(name)
        if not matched:
            raise InventoryError("UNEXPECTED_USER_MANAGER")
        uid = int(matched.group(1))
        if len(managers) >= MAX_USERS or any(x["uid"] == uid for x in managers):
            raise InventoryError("INVALID_USER_MANAGER_LIST")
        try:
            username = pwd.getpwuid(uid).pw_name
        except KeyError:
            managers.append({"uid":uid, "managerActive":active,
                             "status":"ACCOUNT_UNKNOWN", "userUnits":[],
                             "activeUserTimers":[], "financialWriterExcluded":False})
            continue
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", username):
            raise InventoryError("UNSAFE_USERNAME")
        record = {"uid":uid, "managerActive":active, "status":"NOT_INSPECTED",
                  "userUnits":[], "activeUserTimers":[],
                  "financialWriterExcluded":False}
        if active:
            # No shell, sudo commands, login environment, unit contents or secrets.
            # A missing user DBUS session is recorded UNKNOWN, not "no jobs".
            env = ["env", f"XDG_RUNTIME_DIR=/run/user/{uid}",
                   f"DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/{uid}/bus"]
            code, listing = command(["runuser", "-u", username, "--", *env,
                "systemctl", "--user", "--no-pager", "list-units", "--all",
                "--type=service", "--type=timer", "--plain", "--no-legend"])
            if code == 0:
                units = unit_names(listing)
                record["status"] = "OBSERVED_ONLY"
                record["userUnits"] = [name for name, _ in units]
                record["activeUserTimers"] = [name for name, active in units
                                               if active and name.endswith(".timer")]
        managers.append(record)
    return managers


def safe_file_lines(path: Path) -> list[str]:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    fd = os.open(str(path), flags)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_size > MAX_BYTES or before.st_nlink != 1:
            raise InventoryError("UNSAFE_CRON_FILE")
        with os.fdopen(os.dup(fd), "rb") as f:
            data = f.read(MAX_BYTES + 1)
        after = os.fstat(fd)
        if (len(data) > MAX_BYTES or len(data) != before.st_size or
            before.st_ino != after.st_ino or before.st_mtime_ns != after.st_mtime_ns):
            raise InventoryError("CRON_CHANGED_DURING_READ")
        return data.decode("utf-8").splitlines()
    finally:
        os.close(fd)


def cron_count(lines: list[str]) -> dict:
    jobs = 0
    cues = 0
    # Every job remains review-required even if no keyword matched.
    for line in lines:
        item = line.strip()
        if not item or item.startswith("#") or ENV_ASSIGN.match(item):
            continue
        jobs += 1
        if MONEY_CUE.search(item):
            cues += 1
    return {"jobLinesObserved":jobs, "financialKeywordLines":cues,
            "jobsWhoseFinancialAuthorityIsExcluded":0,
            "requiresHumanClassification":bool(jobs)}


def cron_sources() -> dict:
    paths = [Path("/etc/crontab"), Path("/var/spool/cron/crontabs/tony"),
             Path("/var/spool/cron/crontabs/root")]
    directory = Path("/etc/cron.d")
    seen = []
    if directory.is_dir():
        sources = sorted(directory.iterdir(), key=lambda p: p.name)
        if len(sources) > MAX_FILES:
            raise InventoryError("TOO_MANY_CRON_FILES")
        for source in sources:
            if not CRON_FILE.fullmatch(source.name):
                raise InventoryError("UNSAFE_CRON_FILENAME")
            paths.append(source)
    records = []
    for path in paths:
        if not path.exists() and not path.is_symlink():
            continue
        if path.is_symlink():
            raise InventoryError("SYMLINK_CRON_SOURCE")
        try:
            summary = cron_count(safe_file_lines(path))
        except (OSError, UnicodeError) as exc:
            raise InventoryError("CRON_FILE_UNOBSERVED") from exc
        records.append({"source":str(path), **summary})
    return {"filesObserved":len(records),
            "totalJobLines":sum(r["jobLinesObserved"] for r in records),
            "sources":records, "commandsOrVariablesPrinted":False,
            "otherSpoolAndNonstandardCronSourcesExcluded":False}


def container_inventory(engine: str) -> dict:
    code, listing = command([engine, "ps", "--format", "{{.Names}}"])
    if code == 127:
        return {"engine":engine, "status":"ENGINE_UNAVAILABLE",
                "names":[], "restartPolicyObserved":False}
    if code:
        return {"engine":engine, "status":"NOT_INSPECTED",
                "names":[], "restartPolicyObserved":False}
    names = listing.splitlines()
    if len(names) > MAX_UNITS or len(set(names)) != len(names) or any(
        not CONTAINER.fullmatch(x) for x in names
    ):
        raise InventoryError("UNSAFE_CONTAINER_LIST")
    records = []
    for name in sorted(names):
        rc, restart = command([engine, "inspect", "--format",
                              "{{.HostConfig.RestartPolicy.Name}}", name])
        if rc or restart.strip() not in {"no", "always", "unless-stopped",
                                         "on-failure", ""}:
            return {"engine":engine, "status":"NOT_INSPECTED",
                    "names":[], "restartPolicyObserved":False}
        records.append({"name":name, "restartConfigured":restart.strip()
                        not in {"no", ""}, "potentialFinancialWriter":True})
    return {"engine":engine, "status":"OBSERVED_ONLY",
            "names":records, "restartPolicyObserved":True,
            "containerEnvOrMountsInspected":False}


def inspect() -> dict:
    return {
        "schema":"wolo.financial.auxiliary-producer-surfaces.v1",
        "observedAtUtc":datetime.now(timezone.utc).isoformat(),
        "mode":"READ_ONLY_NONAUTHORIZING",
        "status":"HOLD",
        "cron":cron_sources(),
        "userSystemd":user_managers(),
        "containers":[container_inventory("docker"),
                      container_inventory("podman")],
        "systemdSystemUnitTopologyCoveredBySeparateInspector":True,
        "externalAndManualSignersExcluded":False,
        "financialIngressFenced":False,
        "historicalFinancialObligationsReconciled":False,
        "allFinancialWritersIdentified":False,
        "financialReleaseAuthorized":False,
        "satchelActivationAuthorized":False,
        "productionMutated":False,
        "next":"CLASSIFY_CRON_USER_SYSTEMD_CONTAINER_HTTP_AND_EXTERNAL_FINANCIAL_AUTHORITY",
    }


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if args not in ([], ["--inspect"]):
        print("BLOCKED: read-only --inspect only",file=sys.stderr)
        return 2
    try:
        result=inspect()
    except (InventoryError, OSError, ValueError):
        print(json.dumps({"status":"STOP","financialReleaseAuthorized":False,
            "reason":"INCOMPLETE_OR_UNSAFE_AUXILIARY_PRODUCER_INVENTORY"},sort_keys=True))
        return 2
    print(json.dumps(result,indent=2,sort_keys=True))
    return 3


if __name__=="__main__":
    raise SystemExit(main())

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

class StagedInventoryError(InventoryError):
    """Source-classified failure; original exception text is never published."""

    def __init__(self, stage: str, code: str):
        super().__init__(code)
        self.stage = stage
        self.code = code


# These are audited constant strings from this source file, never raw exception
# text. Paths, command output, filenames, and environment values are forbidden.
SAFE_FAILURE_CODES = frozenset((
    "CRON_CHANGED_DURING_READ",
    "CRON_FILE_UNOBSERVED",
    "CRON_PERIODIC_ENTRY_UNOBSERVED",
    "INVALID_USER_MANAGER_LIST",
    "SCHEDULER_DIRECTORY_UNOBSERVED",
    "SCHEDULER_ENTRY_UNOBSERVED",
    "SYMLINK_CRON_SOURCE",
    "SYSTEM_USER_MANAGERS_UNOBSERVED",
    "TOO_MANY_AT_JOBS",
    "TOO_MANY_CRON_FILES",
    "TOO_MANY_SCHEDULER_ENTRIES",
    "TOO_MANY_UNITS",
    "TOO_MUCH_COMMAND_OUTPUT",
    "UNEXPECTED_SPOOL_ROOT",
    "UNEXPECTED_USER_MANAGER",
    "UNKNOWN_UNIT_STATUS",
    "UNSAFE_COMMAND",
    "UNSAFE_CONTAINER_LIST",
    "UNSAFE_CRON_FILE",
    "UNSAFE_OR_DUPLICATE_UNIT",
    "UNSAFE_SCHEDULER_DIRECTORY",
    "UNSAFE_SCHEDULER_ENTRY",
    "UNSAFE_SCHEDULER_FILENAME",
    "UNSAFE_USERNAME",
    "HOST_INTERFACE_UNOBSERVED",
    "INVENTORY_EXCEPTION_REDACTED",
))


def observed_section(stage: str, fn):
    """Preserve the strict STOP and report only known, sanitized failure codes."""
    if stage not in {"CRON", "USER_SYSTEMD", "DOCKER", "PODMAN"}:
        raise InventoryError("UNSAFE_COMMAND")
    try:
        return fn()
    except InventoryError as exc:
        code = str(exc)
        if code not in SAFE_FAILURE_CODES:
            code = "INVENTORY_EXCEPTION_REDACTED"
        raise StagedInventoryError(stage, code) from None
    except (OSError, ValueError):
        raise StagedInventoryError(stage, "HOST_INTERFACE_UNOBSERVED") from None



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


# Schedule entrypoints are a potential financial writer even if their command
# body has no financial keyword. Names and paths below are fixed operator-known
# directories, not values supplied through remote requests.
CRON_SCHEDULE_DIRS = ("cron.hourly", "cron.daily", "cron.weekly",
                      "cron.monthly", "cron.yearly")
SPOOL_DIR_NAMES = ("crontabs", "cron")
# Ordinary Ubuntu at(1) queue storage: directories, never crontab sources.
# Their payloads are intentionally not read; atq is inspected separately.
AT_SPOOL_DIRECTORY_NAMES = ("atjobs", "atspool")
RUN_PARTS_NAME = re.compile(r"[A-Za-z0-9_-]{1,100}\Z")


def _list_regular_entries(folder: Path, *, allow_dot_names: bool = False,
                          skip_expected_child: str | None = None,
                          allow_at_spool_dirs: bool = False) -> list[Path] | None:
    """Bounded local listing. A missing directory is UNKNOWN, never an empty proof."""
    try:
        info = folder.lstat()
    except FileNotFoundError:
        return None
    if not stat.S_ISDIR(info.st_mode) or folder.is_symlink():
        raise InventoryError("UNSAFE_SCHEDULER_DIRECTORY")
    try:
        entries = sorted(folder.iterdir(), key=lambda item: item.name)
    except OSError as exc:
        raise InventoryError("SCHEDULER_DIRECTORY_UNOBSERVED") from exc
    if len(entries) > MAX_FILES:
        raise InventoryError("TOO_MANY_SCHEDULER_ENTRIES")
    for entry in entries:
        name = entry.name
        if not CRON_FILE.fullmatch(name) or (not allow_dot_names and name.startswith(".")):
            raise InventoryError("UNSAFE_SCHEDULER_FILENAME")
        try:
            info = entry.lstat()
        except OSError as exc:
            raise InventoryError("SCHEDULER_ENTRY_UNOBSERVED") from exc
        if (skip_expected_child is not None and name == skip_expected_child and
                stat.S_ISDIR(info.st_mode) and not entry.is_symlink()):
            # This child is independently enumerated as a different spool root.
            continue
        if allow_at_spool_dirs and name in AT_SPOOL_DIRECTORY_NAMES:
            # Only the two known *real directories* in the top-level cron
            # spool are recognized. They are not crontab files and their
            # pending payloads remain uninspected/non-excluded. Wrong types,
            # symlinks, and any unexpected directories still fail closed.
            if not stat.S_ISDIR(info.st_mode) or entry.is_symlink():
                raise InventoryError("UNSAFE_SCHEDULER_ENTRY")
            continue
        if not stat.S_ISREG(info.st_mode) or entry.is_symlink() or info.st_nlink != 1:
            # An unknown nested cron source/symlink must not quietly become
            # "zero known financial writers".
            raise InventoryError("UNSAFE_SCHEDULER_ENTRY")
    return [
        entry for entry in entries
        if entry.name != skip_expected_child
        and not (allow_at_spool_dirs and entry.name in AT_SPOOL_DIRECTORY_NAMES)
    ]


def _periodic_cron_scripts(etc_root: Path) -> dict:
    """Names-only scheduling surface census; never read script source bodies."""
    covered = []
    missing = []
    scripts = 0
    eligible_executable = 0
    for name in CRON_SCHEDULE_DIRS:
        entries = _list_regular_entries(etc_root / name, allow_dot_names=True)
        if entries is None:
            missing.append(name)
            continue
        covered.append(name)
        for entry in entries:
            scripts += 1
            try:
                info = entry.lstat()
            except OSError as exc:
                raise InventoryError("CRON_PERIODIC_ENTRY_UNOBSERVED") from exc
            if RUN_PARTS_NAME.fullmatch(entry.name) and info.st_mode & 0o111:
                eligible_executable += 1
    return {"directoriesObserved": covered,
            "directoriesMissingOrUnverified": missing,
            "filesObserved": scripts,
            "runPartsNameAndExecutableCandidates": eligible_executable,
            "scriptBodiesReadOrPrinted": False,
            "financialWriterCapabilityExcluded": False}


def _at_queue() -> dict:
    # atq displays scheduled job IDs/user/time, never the underlying command.
    # Emit the COUNT only. Missing/inaccessible atq remains unresolved.
    code, listing = command(["atq"])
    if code != 0:
        return {"status": "UNOBSERVED", "pendingJobs": None,
                "financialWriterCapabilityExcluded": False}
    lines = [line for line in listing.splitlines() if line.strip()]
    if len(lines) > MAX_FILES:
        raise InventoryError("TOO_MANY_AT_JOBS")
    return {"status": "OBSERVED_ONLY", "pendingJobs": len(lines),
            "financialWriterCapabilityExcluded": False}


def cron_sources(
    etc_root: Path = Path("/etc"),
    spool_roots: tuple[Path, ...] = (
        Path("/var/spool/cron/crontabs"), Path("/var/spool/cron"),
    ),
) -> dict:
    """Count all enumerable user crontabs, cron.d and periodic entrypoints.

    This is still NOT evidence that every scheduler/financial signer on the VPS
    is known. Do not label any source financially harmless by keyword matching.
    """
    paths = [etc_root / "crontab", etc_root / "anacrontab"]
    cron_d = _list_regular_entries(etc_root / "cron.d", allow_dot_names=True)
    if cron_d is not None:
        paths.extend(cron_d)

    spool_observed = []
    spool_missing = []
    spool_files = 0
    for spool in spool_roots:
        if spool.name not in SPOOL_DIR_NAMES:
            raise InventoryError("UNEXPECTED_SPOOL_ROOT")
        entries = _list_regular_entries(
            spool,
            skip_expected_child="crontabs" if spool.name == "cron" else None,
            allow_at_spool_dirs=spool.name == "cron",
        )
        if entries is None:
            spool_missing.append(spool.name)
            continue
        spool_observed.append(spool.name)
        # The parent /var/spool/cron may contain the child directory
        # 'crontabs'; treat that specifically as an already-inspected sibling,
        # never as a cron file or silent evidence omission.
        paths.extend(entries)
        spool_files += len(entries)
    if len(paths) > MAX_FILES:
        raise InventoryError("TOO_MANY_CRON_FILES")

    # Metadata only. Do not inspect at-job payloads: the atq count is a
    # separate untrusted observation and neither path proves financial
    # writer capability absent. Existence must be an actual non-symlink dir.
    at_spool_dirs_observed: list[str] = []
    at_spool_dirs_missing: list[str] = []
    for spool in spool_roots:
        if spool.name != "cron":
            continue
        for name in AT_SPOOL_DIRECTORY_NAMES:
            candidate = spool / name
            try:
                info = candidate.lstat()
            except FileNotFoundError:
                at_spool_dirs_missing.append(name)
                continue
            except OSError as exc:
                raise InventoryError("SCHEDULER_ENTRY_UNOBSERVED") from exc
            if not stat.S_ISDIR(info.st_mode) or candidate.is_symlink():
                raise InventoryError("UNSAFE_SCHEDULER_ENTRY")
            at_spool_dirs_observed.append(name)

    records = []
    for path in paths:
        try:
            path.lstat()
        except FileNotFoundError:
            continue
        if path.is_symlink():
            raise InventoryError("SYMLINK_CRON_SOURCE")
        try:
            summary = cron_count(safe_file_lines(path))
        except (OSError, UnicodeError) as exc:
            raise InventoryError("CRON_FILE_UNOBSERVED") from exc
        records.append({"source": str(path), **summary})
    periodic = _periodic_cron_scripts(etc_root)
    queue = _at_queue()
    return {"filesObserved": len(records),
            "totalJobLines": sum(r["jobLinesObserved"] for r in records),
            "sources": records, "commandsOrVariablesPrinted": False,
            "allEnumeratedSpoolUsersIncluded": True,
            "spoolCrontabsObserved": spool_files,
            "spoolDirectoriesObserved": spool_observed,
            "spoolDirectoriesMissingOrUnverified": spool_missing,
            "periodic": periodic, "atQueue": queue,
            "atSpoolDirectoriesObserved": at_spool_dirs_observed,
            "atSpoolDirectoriesMissingOrUnverified": at_spool_dirs_missing,
            "atSpoolJobPayloadsInspected": False,
            "atSpoolFinancialWriterCapabilityExcluded": False,
            "allFinancialWritersIdentified": False,
            "otherSpoolAndNonstandardCronSourcesExcluded": False}


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
        "cron":observed_section("CRON", cron_sources),
        "userSystemd":observed_section("USER_SYSTEMD", user_managers),
        "containers":[observed_section("DOCKER", lambda: container_inventory("docker")),
                      observed_section("PODMAN", lambda: container_inventory("podman"))],
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
    # The collector needs Linux systemd, user managers and cron spools.
    # On an operator's macOS shell it cannot observe the VPS at all.
    # Refuse before running any host inventory queries.
    if sys.platform != "linux":
        print(json.dumps({
            "status": "STOP",
            "reason": "WRONG_HOST_LINUX_REQUIRED",
            "financialReleaseAuthorized": False,
            "satchelActivationAuthorized": False,
            "productionMutated": False,
        }, sort_keys=True))
        return 2
    try:
        result=inspect()
    except StagedInventoryError as exc:
        print(json.dumps({
            "status": "STOP",
            "reason": "INCOMPLETE_OR_UNSAFE_AUXILIARY_PRODUCER_INVENTORY",
            "failureStage": exc.stage,
            "failureCode": exc.code,
            "financialReleaseAuthorized": False,
            "satchelActivationAuthorized": False,
            "productionMutated": False,
        }, sort_keys=True))
        return 2
    except (InventoryError, OSError, ValueError):
        print(json.dumps({"status":"STOP","financialReleaseAuthorized":False,
            "reason":"INCOMPLETE_OR_UNSAFE_AUXILIARY_PRODUCER_INVENTORY"},sort_keys=True))
        return 2
    print(json.dumps(result,indent=2,sort_keys=True))
    return 3


if __name__=="__main__":
    raise SystemExit(main())

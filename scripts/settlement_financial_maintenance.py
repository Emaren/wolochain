#!/usr/bin/env python3
"""Explicitly permitted HD/DE activation fence and quiesced backup foundations.

No default mutation, unfence, financial execution, consensus or settlement restart.
Root-private human permits authorize exact actions, not the truth of attestations.
A retained HOLD is intentional on every failure, expiry or interrupted process.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import resource
import secrets
import shutil
import selectors
import signal
import stat
import subprocess
import sys
import time
import types
from urllib.parse import unquote, urlsplit

APPS = ("aoe2hdbets-web.service", "aoe2hdbets-api.service",
        "aoe2dewarwagers-web.service", "aoe2dewarwagers-api.service")
FAMILIES = ("aoe2hdbets-bet-stake-reconcile", "aoe2hdbets-challenge-reconcile",
            "aoe2hdbets-replay-auto-recovery", "aoe2hdbets-staking-rewards",
            "aoe2hdbets-trophy-tributes", "aoe2war-prewarm",
            "aoe2-wolo-transfer-heartbeat")
TIMERS = tuple(x + ".timer" for x in FAMILIES)
ONESHOTS = tuple(x + ".service" for x in FAMILIES)
UNITS = APPS + ONESHOTS + TIMERS
HOLD = Path("/etc/wolochain-financial-maintenance/HOLD")
DROPIN = "90-wolo-financial-maintenance.conf"
SYSTEMD = Path("/etc/systemd/system")
VOLUME = Path("/mnt/HC_Volume_105319120")
BACKUPS = VOLUME / "wolochain-mainnet/financial-maintenance-backups"
SNAPSHOT_ROOT = VOLUME / "wolochain-mainnet/settlement-backups"
# Separately provisioned root-owned 0700 area on the OS disk, never Docker's
# state-volume data-root. This path cannot include any production secrets.
RESTORE_SCRATCH = Path("/var/lib/wolo-financial-restore")
RESTORE_OS_RESERVE = 8 << 30
RESTORE_DATA_FACTOR = 2
LOCK = Path("/run/lock/aoe2war-wolo-two-settlement-code-only.lock")
DOCKER = ["docker", "--host=unix:///var/run/docker.sock"]
SCHEMA = "wolo.financial-maintenance-permit.v1"
FENCE_SCHEMA = "wolo.financial-maintenance-fence.v1"
SHA = re.compile(r"[0-9a-f]{64}\Z")
IDENT = re.compile(r"[a-z][a-z0-9_]{0,62}\Z")
ROLE_NAMES = {"owner", "operator", "chain_reviewer", "finance_reviewer", "recovery_witness"}
ATTESTATIONS = {"external_ingress_fenced", "cron_user_managers_fenced",
                "container_writers_fenced", "all_database_writers_fenced",
                "inflight_and_unknown_operations_reviewed", "claim_889_preserved",
                "all_financial_tables_enumerated"}
MAX_IO = 1 << 20
SNAPSHOT_TOOL_SHA256 = "79b5226221ab8372e19c6b55e915d998f32a821d2b5f8d985d3fa0d85d6d43e5"
PG_OBSERVER_SHA256 = "b16c5b14d9aece8bf44c63f078af588aac841ee8662717162a3313c864214919"


class MaintenanceError(RuntimeError):
    pass


def require(ok, reason):
    if not ok:
        raise MaintenanceError(reason)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def scope_digest():
    return digest(canonical({"units": list(UNITS), "hold": str(HOLD),
                             "dropin": DROPIN, "resume_authorized": False}))


def utc(value):
    try:
        require(isinstance(value, str) and value.endswith("Z"), "UTC_TIMESTAMP_REQUIRED")
        result = datetime.fromisoformat(value[:-1] + "+00:00")
    except (ValueError, TypeError):
        raise MaintenanceError("INVALID_UTC_TIMESTAMP") from None
    return result


def clock():
    return datetime.now(timezone.utc)


def bounded_runner(runner, permit):
    def call(argv, **kwargs):
        remaining = (utc(permit["expires_at"]) - clock()).total_seconds()
        require(remaining > 0, "APPROVED_WINDOW_EXPIRED")
        kwargs["timeout"] = min(kwargs.get("timeout", 30), remaining)
        return runner(argv, **kwargs)
    return call


def private_read(path, limit=65536, source=False):
    """Stable root-owned no-follow file; secrets 0600, pinned code 0600/0644."""
    path = Path(path)
    require(path.is_absolute(), "ABSOLUTE_PROTECTED_PATH_REQUIRED")
    for parent in path.parents:
        meta = parent.lstat()
        require(stat.S_ISDIR(meta.st_mode) and meta.st_uid == 0 and
                not meta.st_mode & 0o022, "UNSAFE_PROTECTED_PARENT")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        a = os.fstat(fd)
        require(stat.S_ISREG(a.st_mode) and a.st_uid == a.st_gid == 0 and
                stat.S_IMODE(a.st_mode) in ((0o600, 0o644) if source else (0o600,)) and a.st_nlink == 1 and
                0 <= a.st_size <= limit, "ROOT_PRIVATE_REGULAR_FILE_REQUIRED")
        raw = os.read(fd, limit + 1)
        b = os.fstat(fd)
        fields = ("st_dev", "st_ino", "st_mode", "st_uid", "st_gid", "st_size",
                  "st_mtime_ns", "st_ctime_ns", "st_nlink")
        require(len(raw) == a.st_size and all(getattr(a, k) == getattr(b, k) for k in fields),
                "PROTECTED_FILE_CHANGED")
        c = path.lstat()
        require((a.st_dev, a.st_ino) == (c.st_dev, c.st_ino), "PROTECTED_PATH_CHANGED")
        return raw
    finally:
        os.close(fd)


def unique(pairs):
    out = {}
    for key, value in pairs:
        require(key not in out, "DUPLICATE_JSON_FIELD")
        out[key] = value
    return out


def private_json(path):
    try:
        raw = private_read(path)
        value = json.loads(raw, object_pairs_hook=unique)
        require(type(value) is dict, "OBJECT_REQUIRED")
        return value, digest(raw)
    except (OSError, UnicodeError, ValueError):
        raise MaintenanceError("PROTECTED_JSON_UNAVAILABLE") from None


def _validate_permit_contract(value):
    expected = {"schema", "action", "scope_sha256", "tool_sha256", "packet_sha256",
                "procedure_sha256", "not_before", "expires_at", "approval_refs",
                "attestations", "max_total_bytes", "databases", "restore_image"}
    require(set(value) == expected and value["schema"] == SCHEMA and
            value["action"] == "fence-backup-isolated-restore", "PERMIT_SCOPE_INVALID")
    require(value["scope_sha256"] == scope_digest() and
            value["tool_sha256"] == digest(Path(__file__).read_bytes()), "SOURCE_SCOPE_DRIFT")
    require(all(isinstance(value[k], str) and SHA.fullmatch(value[k]) and
                value[k] != "0" * 64 for k in ("packet_sha256", "procedure_sha256")),
            "EXACT_EVIDENCE_DIGESTS_REQUIRED")
    start, end = utc(value["not_before"]), utc(value["expires_at"])
    require(0 < (end - start).total_seconds() <= 1800, "APPROVED_WINDOW_UNAVAILABLE")
    approvals = value["approval_refs"]
    require(type(approvals) is dict and set(approvals) == ROLE_NAMES,
            "FIVE_SCOPED_HUMAN_APPROVALS_REQUIRED")
    for role, a in approvals.items():
        require(type(a) is dict and set(a) == {"identity", "approval_sha256"} and
                isinstance(a["identity"], str) and 3 <= len(a["identity"]) <= 120 and
                isinstance(a["approval_sha256"], str) and SHA.fullmatch(a["approval_sha256"]) and
                a["approval_sha256"] != "0" * 64, "HUMAN_APPROVAL_REFERENCE_INVALID")
    require(type(value["attestations"]) is dict and set(value["attestations"]) == ATTESTATIONS and
            all(x is True for x in value["attestations"].values()), "EXTERNAL_FENCES_UNATTESTED")
    require(type(value["max_total_bytes"]) is int and
            1 << 20 <= value["max_total_bytes"] <= 100 << 30, "BACKUP_BUDGET_INVALID")
    require(type(value["databases"]) is dict and set(value["databases"]) == {"hd", "de"},
            "TWO_DATABASES_REQUIRED")
    names = []
    for db in value["databases"].values():
        require(type(db) is dict and set(db) == {"env_path", "env_sha256", "database_sha256",
                                                "financial_tables", "postgres_major"},
                "DATABASE_CONTRACT_INVALID")
        require(isinstance(db["env_path"], str) and db["env_path"].startswith("/etc/") and
                all(isinstance(db[k], str) and SHA.fullmatch(db[k]) and db[k] != "0" * 64
                    for k in ("env_sha256", "database_sha256")), "DATABASE_AUTHORITY_INVALID")
        tables = db["financial_tables"]
        require(type(tables) is list and 1 <= len(tables) <= 100 and
                len(set(tables)) == len(tables) and
                all(isinstance(t, str) and IDENT.fullmatch(t) for t in tables),
                "FINANCIAL_TABLE_CENSUS_INVALID")
        require(type(db["postgres_major"]) is int and 14 <= db["postgres_major"] <= 18,
                "POSTGRES_MAJOR_UNQUALIFIED")
        names.append(db["database_sha256"])
    require(len(set(names)) == 2, "HD_DE_DATABASE_IDENTITY_COLLISION")
    require(len({db["postgres_major"] for db in value["databases"].values()}) == 1,
            "ONE_QUALIFIED_POSTGRES_MAJOR_REQUIRED")
    require(isinstance(value["restore_image"], str) and
            re.fullmatch(r"postgres@sha256:[0-9a-f]{64}", value["restore_image"]),
            "PINNED_EXISTING_RESTORE_IMAGE_REQUIRED")
    return value


def validate_permit(value, *, now=None):
    _validate_permit_contract(value)
    now = now or clock()
    require(now.tzinfo is not None and utc(value["not_before"]) <= now < utc(value["expires_at"]),
            "APPROVED_WINDOW_UNAVAILABLE")
    return value


def run(argv, *, env=None, input=None, timeout=30, file_limit=None, stdin_file=None):
    """Bounded child process; never echo argv, stderr, environment or DB secrets."""
    def limits():
        if file_limit is not None:
            resource.setrlimit(resource.RLIMIT_FSIZE, (file_limit, file_limit))
    require(input is None or stdin_file is None, "AMBIGUOUS_COMMAND_INPUT")
    source = open(stdin_file, "rb") if stdin_file is not None else None
    p = subprocess.Popen(argv, stdin=source if source is not None else
                         subprocess.PIPE if input is not None else subprocess.DEVNULL,
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env,
                         start_new_session=True, preexec_fn=limits)
    try:
        if input is not None:
            p.stdin.write(input.encode() if isinstance(input, str) else input)
            p.stdin.close()
        sel = selectors.DefaultSelector()
        for stream in (p.stdout, p.stderr):
            os.set_blocking(stream.fileno(), False)
            sel.register(stream, selectors.EVENT_READ)
        output = {p.stdout: bytearray(), p.stderr: bytearray()}
        deadline = time.monotonic() + timeout
        while sel.get_map():
            require(time.monotonic() < deadline, "BOUNDED_COMMAND_TIMEOUT")
            for key, _ in sel.select(min(0.1, max(0, deadline - time.monotonic()))):
                block = os.read(key.fileobj.fileno(), 65536)
                if not block:
                    sel.unregister(key.fileobj)
                else:
                    output[key.fileobj].extend(block)
                    require(sum(map(len, output.values())) <= MAX_IO, "COMMAND_OUTPUT_LIMIT")
        require(p.wait(timeout=max(0.01, deadline - time.monotonic())) == 0,
                "BOUNDED_COMMAND_FAILED")
        return output[p.stdout].decode("utf-8", errors="strict")
    except BaseException:
        try:
            os.killpg(p.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        p.wait()
        raise
    finally:
        for stream in (p.stdout, p.stderr):
            stream.close()
        if source is not None:
            source.close()


def expected_dropin():
    return ("# Owned Wolo financial maintenance; no automatic resumption\n"
            "[Unit]\nConditionPathExists=!" + str(HOLD) + "\n").encode()


def dropin(unit):
    require(unit in UNITS, "UNREVIEWED_UNIT")
    return SYSTEMD / (unit + ".d") / DROPIN


def show(unit, runner):
    raw = runner(["systemctl", "--no-pager", "show", "--property=Id,LoadState,ActiveState,"
                  "SubState,MainPID,ControlGroup,DropInPaths,UnitFileState,FragmentPath,"
                  "Triggers,TriggeredBy,Restart,Persistent", "--", unit])
    fields = {}
    for line in raw.splitlines():
        require("=" in line, "UNIT_PROPERTIES_INVALID")
        key, value = line.split("=", 1)
        require(key not in fields, "DUPLICATE_UNIT_PROPERTY")
        fields[key] = value
    require(fields.get("Id") == unit and fields.get("LoadState") == "loaded" and
            fields.get("FragmentPath", "").startswith(("/etc/systemd/system/", "/usr/lib/systemd/system/",
                                                        "/lib/systemd/system/")),
            "UNIT_IDENTITY_UNAVAILABLE")
    return fields


def effective_condition(unit, runner):
    # Inactive definitions may have been garbage-collected after `show`.
    # LoadUnit loads configuration only; it never starts an activation job.
    raw = runner(["busctl", "--system", "--json=short", "call", "org.freedesktop.systemd1",
                  "/org/freedesktop/systemd1", "org.freedesktop.systemd1.Manager",
                  "LoadUnit", "s", unit])
    obj = json.loads(raw)
    require(obj.get("type") == "o" and type(obj.get("data")) is list and
            len(obj["data"]) == 1 and re.fullmatch(r"/org/freedesktop/systemd1/unit/[A-Za-z0-9_]+",
                                                 obj["data"][0]), "UNIT_DBUS_IDENTITY_INVALID")
    obj = json.loads(runner(["busctl", "--system", "--json=short", "get-property",
                            "org.freedesktop.systemd1", obj["data"][0],
                            "org.freedesktop.systemd1.Unit", "Conditions"]))
    require(obj.get("type") == "a(sbbsi)" and type(obj.get("data")) is list and
            ["ConditionPathExists", False, True, str(HOLD), 0] in
            [x[:4] + [0] for x in obj["data"] if isinstance(x, list) and len(x) == 5],
            "ACTIVATION_GATE_NOT_EFFECTIVE")


def no_jobs(runner):
    # Fail on ALL pending jobs, including both protected settlement services.
    # systemctl --output formats journal entries, not the ListJobs table.
    # Use the actual typed manager API; never infer zero from human text.
    try:
        jobs = json.loads(runner(["busctl", "--system", "--json=short", "call",
            "org.freedesktop.systemd1", "/org/freedesktop/systemd1",
            "org.freedesktop.systemd1.Manager", "ListJobs"]))
    except (ValueError, TypeError):
        raise MaintenanceError("PENDING_OR_UNKNOWN_SYSTEMD_JOB") from None
    require(type(jobs) is dict and set(jobs) == {"type", "data"} and
            jobs["type"] == "a(usssoo)" and jobs["data"] == [[]],
            "PENDING_OR_UNKNOWN_SYSTEMD_JOB")


def wait_for_no_jobs(runner, permit, *, seconds=100):
    """Bounded drain of jobs caused by reload; final empty-job guard unchanged."""
    deadline = time.monotonic() + seconds
    while True:
        validate_permit(permit)
        try:
            no_jobs(runner)
            return
        except MaintenanceError as exc:
            if str(exc) != "PENDING_OR_UNKNOWN_SYSTEMD_JOB" or time.monotonic() >= deadline:
                raise
            time.sleep(min(.2, max(0, deadline - time.monotonic())))


def inactive_observation(runner):
    no_jobs(runner)
    out = {}
    for unit in UNITS:
        fields = show(unit, runner)
        require(fields.get("ActiveState") == "inactive" and
                fields.get("MainPID", "0") == "0" and
                str(dropin(unit)) in fields.get("DropInPaths", "").split(),
                "PRODUCER_NOT_FENCED")
        effective_condition(unit, runner)
        group = fields.get("ControlGroup", "")
        if group:
            require(group.startswith("/") and ".." not in Path(group).parts,
                    "CGROUP_PATH_INVALID")
            event = Path("/sys/fs/cgroup") / group.lstrip("/") / "cgroup.events"
            require(event.is_file() and "populated 0" in event.read_text().splitlines(),
                    "PRODUCER_CGROUP_POPULATED")
        out[unit] = fields
    no_jobs(runner)
    return out


def _verify_fence(receipt_path, expected_scope_sha256, *, now=None, runner=None, retained=False):
    runner = runner or run
    receipt, _ = private_json(receipt_path)
    require(set(receipt) == {"schema", "scope_sha256", "permit_path", "permit_sha256",
                            "hold_sha256", "prestate", "created_at", "resume_authorized"} and
            receipt["schema"] == FENCE_SCHEMA and receipt["resume_authorized"] is False and
            receipt["scope_sha256"] == expected_scope_sha256 == scope_digest(),
            "FENCE_RECEIPT_SCOPE_INVALID")
    permit, permit_sha = private_json(receipt["permit_path"])
    (_validate_permit_contract(permit) if retained else validate_permit(permit, now=now))
    if now is None and not retained:
        runner = bounded_runner(runner, permit)
    require(type(receipt["prestate"]) is dict and set(receipt["prestate"]) == set(UNITS),
            "FENCE_PRESTATE_INCOMPLETE")
    require(permit_sha == receipt["permit_sha256"], "FENCE_PERMIT_ROTATED")
    hold = private_read(HOLD)
    require(digest(hold) == receipt["hold_sha256"] and
            hold == canonical({"scope_sha256": scope_digest(), "permit_sha256": permit_sha}),
            "OWNED_HOLD_MISSING_OR_CHANGED")
    for unit in UNITS:
        require(private_read(dropin(unit)) == expected_dropin(), "OWNED_DROPIN_DRIFT")
    observed = inactive_observation(runner)
    (_validate_permit_contract(permit) if retained else validate_permit(permit, now=now))
    at = now or clock()
    return {"scope_sha256": scope_digest(), "units": observed,
            "permit": permit, "resume_authorized": False,
            "admission_authorized": False,
            "original_window_current": utc(permit["not_before"]) <= at < utc(permit["expires_at"])}


def verify_current_fence(receipt_path, expected_scope_sha256, *, now=None, runner=None):
    """Read-only import boundary; current original window is mandatory."""
    return _verify_fence(receipt_path, expected_scope_sha256, now=now, runner=runner)


def verify_retained_fence(receipt_path, expected_scope_sha256, *, runner=None):
    """NONAUTHORIZING retained-gate observation, including after old expiry.

    A separate fresh recovery authority must authenticate its own new window and
    scoped humans. This never renews the original permit, fences or resumes.
    """
    return _verify_fence(receipt_path, expected_scope_sha256, runner=runner, retained=True)


def write_new(path, raw):
    path = Path(path)
    require(path.is_absolute(), "ABSOLUTE_OUTPUT_REQUIRED")
    for parent in path.parents:
        info = parent.lstat()
        require(stat.S_ISDIR(info.st_mode) and info.st_uid == 0 and
                not info.st_mode & 0o022, "UNSAFE_OUTPUT_PARENT")
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(raw)
            f.flush()
            os.fsync(f.fileno())
        for parent in (path.parent, path.parent.parent):
            directory_fd = os.open(parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
    except BaseException:
        # Preserve any partial file as evidence. Never automatically remove a HOLD.
        raise


def fence(permit_path, receipt_path, *, runner=None):
    runner = runner or run
    permit, permit_sha = private_json(permit_path)
    validate_permit(permit)
    runner = bounded_runner(runner, permit)
    require(os.geteuid() == 0, "ROOT_REQUIRED")
    require(not HOLD.exists() and not HOLD.is_symlink(), "EXISTING_HOLD_REQUIRES_REVIEW")
    no_jobs(runner)
    prestate = {unit: show(unit, runner) for unit in UNITS}
    for unit in UNITS:
        require(not dropin(unit).exists() and not dropin(unit).is_symlink(), "FOREIGN_OR_EXISTING_GATE")
    HOLD.parent.mkdir(mode=0o700, exist_ok=True)
    require(HOLD.parent.lstat().st_uid == 0 and
            stat.S_IMODE(HOLD.parent.lstat().st_mode) == 0o700 and not HOLD.parent.is_symlink(),
            "UNSAFE_HOLD_DIRECTORY")
    hold = canonical({"scope_sha256": scope_digest(), "permit_sha256": permit_sha})
    write_new(HOLD, hold)
    # Install AND verify activation denial before stopping any producer. A crash
    # leaves HOLD/drop-ins in place; there is deliberately no cleanup/start trap.
    for unit in UNITS:
        validate_permit(permit)
        dropin(unit).parent.mkdir(mode=0o755, exist_ok=True)
        require(dropin(unit).parent.lstat().st_uid == 0 and
                not dropin(unit).parent.is_symlink() and
                not dropin(unit).parent.lstat().st_mode & 0o022, "UNSAFE_DROPIN_PARENT")
        write_new(dropin(unit), expected_dropin())
    runner(["systemctl", "daemon-reload"])
    for unit in UNITS:
        effective_condition(unit, runner)
    for unit in TIMERS + ONESHOTS + APPS:
        validate_permit(permit)
        runner(["systemctl", "stop", "--", unit])
    wait_for_no_jobs(runner, permit)
    inactive_observation(runner)
    validate_permit(permit)
    receipt = {"schema": FENCE_SCHEMA, "scope_sha256": scope_digest(),
               "permit_path": str(Path(permit_path)), "permit_sha256": permit_sha,
               "hold_sha256": digest(hold), "prestate": prestate,
               "created_at": clock().isoformat(), "resume_authorized": False}
    write_new(receipt_path, canonical(receipt))
    verify_current_fence(receipt_path, scope_digest(), runner=runner)
    return receipt


def pg_environment(contract):
    """Read ONLY DATABASE_URL from pre-provisioned root-private /etc authority."""
    raw = private_read(contract["env_path"])
    require(digest(raw) == contract["env_sha256"], "DATABASE_ENV_DRIFT")
    values = []
    for line in raw.decode().splitlines():
        if line.startswith("DATABASE_URL="):
            value = line.partition("=")[2].strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            values.append(value)
    require(len(values) == 1, "DATABASE_URL_UNAVAILABLE")
    u = urlsplit(values[0])
    require(u.scheme in {"postgres", "postgresql"} and u.hostname in {"127.0.0.1", "localhost", "::1"}
            and not u.fragment and not u.query and u.username and u.path.startswith("/"),
            "LOCAL_EXACT_DATABASE_REQUIRED")
    name = unquote(u.path[1:])
    require(IDENT.fullmatch(name) and digest(name.encode()) == contract["database_sha256"],
            "DATABASE_IDENTITY_MISMATCH")
    env = {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "PGHOST": u.hostname,
           "PGPORT": str(u.port or 5432), "PGUSER": unquote(u.username),
           "PGPASSWORD": unquote(u.password or ""), "PGDATABASE": name,
           "PGCONNECT_TIMEOUT": "5", "PGAPPNAME": "wolo_quiesced_backup",
           "PGOPTIONS": "-c default_transaction_read_only=on -c statement_timeout=60000 "
                        "-c lock_timeout=1000 -c TimeZone=UTC -c DateStyle=ISO -c row_security=off"}
    require(all("\x00" not in v and "\n" not in v for v in env.values()), "DATABASE_AUTHORITY_INVALID")
    return env


def psql(sql, env, runner):
    return runner(["psql", "--quiet", "--no-password", "--no-psqlrc", "--tuples-only", "--no-align",
                   "--set=ON_ERROR_STOP=1", "--set=AUTOCOMMIT=on"], env=env, input=sql, timeout=70).strip()


def pg_observer():
    """Load only the exact reviewed observer from protected, stable source bytes.

    Lazy loading lets source-only watchdog observations avoid PostgreSQL tooling.
    Never import an observer selected by cwd, PYTHONPATH or an unpinned file.
    """
    path = Path(__file__).with_name("settlement_pg_quiescence_observer.py")
    try:
        raw = private_read(path, 65536, True)
        require(digest(raw) == PG_OBSERVER_SHA256, "PG_OBSERVER_SOURCE_DRIFT")
        name = "_wolo_pinned_pg_observer_" + PG_OBSERVER_SHA256
        module = types.ModuleType(name)
        module.__file__ = str(path)
        sys.modules[name] = module  # dataclass resolves its defining module.
        exec(compile(raw, str(path), "exec"), module.__dict__)
        return module
    except (OSError, UnicodeError, SyntaxError):
        raise MaintenanceError("PG_OBSERVER_SOURCE_UNAVAILABLE") from None


def financial_census(contract, env, runner):
    """Full rows of reviewed financial tables, constraints and sequence state.

    Hashes canonical JSON rows rather than summing overlapping financial books.
    This verifies restored bytes/invariants, never whether debts are solvent.
    """
    observer = pg_observer()
    # psql runs one autocommitted statement: no old statistics snapshot. Include
    # every other session, even idle/background or NULL-hidden activity. Query
    # session details only for a role entitled to see the complete catalog.
    try:
        meta = json.loads(psql("WITH visibility AS (SELECT current_setting('is_superuser')='on' AS superuser, "
            "pg_has_role(current_user,'pg_read_all_stats','USAGE') AS all_stats) "
            "SELECT json_build_object('database',current_database(),"
            "'readonly',current_setting('transaction_read_only'),"
            "'major',current_setting('server_version_num')::int/10000,"
            "'privilege',json_build_array(superuser,all_stats),"
            "'existing',(SELECT COALESCE(json_agg(datname),'[]'::json) FROM pg_catalog.pg_database "
            "WHERE datname=current_database() AND datallowconn),"
            "'sessions',CASE WHEN superuser OR all_stats THEN (SELECT COALESCE(json_agg("
            "json_build_array(pid,datname,state,usename,backend_type)),'[]'::json) "
            "FROM pg_catalog.pg_stat_activity WHERE datname=current_database() AND pid<>pg_backend_pid()) "
            "ELSE NULL END,'prepared_transactions',(SELECT count(*) FROM pg_catalog.pg_prepared_xacts "
            "WHERE database=current_database())) FROM visibility;", env, runner))
        require(type(meta) is dict and isinstance(meta.get("database"), str) and
                digest(meta["database"].encode()) == contract["database_sha256"] and
                meta["readonly"] == "on" and type(meta["major"]) is int and
                meta["major"] == contract["postgres_major"], "DATABASE_NOT_EXCLUSIVELY_QUIESCED")
        observation = observer.validate_catalog_observation((meta["database"],), meta["privilege"],
            meta["existing"], meta["sessions"], meta["prepared_transactions"])
        require(observation.other_sessions == 0 and observation.prepared_transactions == 0,
                "DATABASE_NOT_EXCLUSIVELY_QUIESCED")
    except (observer.Hold, ValueError, TypeError, KeyError):
        raise MaintenanceError("DATABASE_NOT_EXCLUSIVELY_QUIESCED") from None
    out = {}
    for table in sorted(contract["financial_tables"]):
        require(IDENT.fullmatch(table), "UNSAFE_TABLE")
        row_hash = "encode(sha256(convert_to(to_jsonb(t)::text,'UTF8')),'hex')"
        sql = ("SELECT json_build_object('rows',count(*)::text,'sha256',"
               "encode(sha256(convert_to(COALESCE(string_agg(" + row_hash + ",'' ORDER BY " +
               row_hash + " COLLATE \"C\"),''),'UTF8')),'hex')) FROM public.\"" + table + "\" t;")
        out[table] = json.loads(psql(sql, env, runner))
    # Include constraint definitions and sequence values, not pg_restore --list.
    names = ",".join("'" + t + "'" for t in sorted(contract["financial_tables"]))
    constraints = psql("SELECT COALESCE(json_agg(x ORDER BY x::text), '[]'::json) FROM "
        "(SELECT n.nspname,c.relname,k.conname,pg_get_constraintdef(k.oid,true) AS definition,"
        "k.convalidated FROM pg_constraint k JOIN pg_class c ON c.oid=k.conrelid "
        "JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' "
        "AND c.relname IN (" + names + ")) x;", env, runner)
    sequences = psql("SELECT COALESCE(json_agg(x ORDER BY x::text), '[]'::json) FROM "
        "(SELECT schemaname,sequencename,start_value,min_value,max_value,increment_by,cycle,"
        "last_value FROM pg_sequences WHERE schemaname='public') x;", env, runner)
    return {"tables": out, "constraints_sha256": digest(canonical(json.loads(constraints))),
            "sequences_sha256": digest(canonical(json.loads(sequences))),
            "postgres_major": meta["major"]}


def file_sha(path):
    require(Path(path).is_file() and not Path(path).is_symlink(), "BACKUP_FILE_UNAVAILABLE")
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while block := f.read(1 << 20):
            h.update(block)
    return h.hexdigest()


def settlement_states_unchanged(snapshot, budget):
    def tree(path):
        require(path.is_dir() and not path.is_symlink(), "SETTLEMENT_TREE_UNAVAILABLE")
        files, size = {}, 0
        for item in sorted(path.rglob("*")):
            meta = item.lstat()
            require(not stat.S_ISLNK(meta.st_mode) and
                    (stat.S_ISDIR(meta.st_mode) or stat.S_ISREG(meta.st_mode)), "UNSAFE_SETTLEMENT_TREE")
            if stat.S_ISREG(meta.st_mode):
                require(not item.name.endswith(".lock"), "SETTLEMENT_REQUEST_STILL_LOCKED")
                size += meta.st_size
                require(len(files) < 100000 and size <= budget, "SETTLEMENT_TREE_BUDGET_EXCEEDED")
                before = (meta.st_ino, meta.st_size, meta.st_mtime_ns, meta.st_ctime_ns)
                files[str(item.relative_to(path))] = file_sha(item)
                after = item.lstat()
                require(before == (after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns),
                        "SETTLEMENT_TREE_CHANGED")
        return files
    for lane, dirname in (("primary", "settlement-state"), ("founder", "founder-rewards-settlement-state")):
        original = VOLUME / "wolochain-mainnet" / dirname
        require(tree(original) == tree(snapshot / "state" / lane), "SETTLEMENT_STATE_CHANGED_AFTER_SNAPSHOT")


def snapshot_footprint(path, budget):
    total, count = 0, 0
    for item in path.rglob("*"):
        meta = item.lstat()
        require(stat.S_ISDIR(meta.st_mode) or stat.S_ISREG(meta.st_mode), "UNSAFE_SNAPSHOT_MEMBER")
        if stat.S_ISREG(meta.st_mode):
            total += meta.st_size
            count += 1
            require(total <= budget and count <= 100000, "SNAPSHOT_FOOTPRINT_EXCEEDED")
    return total


def backup(receipt_path, output, *, runner=None):
    runner = runner or run
    observed = verify_current_fence(receipt_path, scope_digest(), runner=runner)
    permit = observed["permit"]
    runner = bounded_runner(runner, permit)
    output = Path(output)
    require(output.parent == BACKUPS and not output.exists() and not output.is_symlink(),
            "NEW_PROTECTED_BACKUP_DIRECTORY_REQUIRED")
    require(os.path.ismount(VOLUME) and BACKUPS.is_dir() and not BACKUPS.is_symlink(),
            "PROTECTED_MOUNT_UNAVAILABLE")
    require(os.statvfs(BACKUPS).f_bavail * os.statvfs(BACKUPS).f_frsize >=
            permit["max_total_bytes"] + (1 << 30), "BACKUP_CAPACITY_INSUFFICIENT")
    output.mkdir(mode=0o700)
    write_new(output / "INCOMPLETE", b"NOT VERIFIED; never restore production financial state\n")
    write_new(output / "authority.json", canonical({"fence_receipt_sha256": file_sha(receipt_path),
                                                  "scope_sha256": scope_digest()}))
    # Existing exact-version snapshot owns both state trees/config/binary receipts.
    snapshot_tool = Path(__file__).with_name("settlement-dual-service-snapshot.sh")
    snapshot_bytes = snapshot_tool.read_bytes()
    require(digest(snapshot_bytes) == SNAPSHOT_TOOL_SHA256, "SNAPSHOT_TOOL_SOURCE_DRIFT")
    raw = runner(["bash", "-s", "--", "--snapshot"], input=snapshot_bytes, timeout=180,
                 file_limit=permit["max_total_bytes"])
    prefix = "PASS private two-service snapshot completed at "
    paths = [Path(line[len(prefix):]) for line in raw.splitlines() if line.startswith(prefix)]
    require(len(paths) == 1 and paths[0].parent == SNAPSHOT_ROOT and paths[0].is_dir() and
            not (paths[0] / "INCOMPLETE").exists(), "SETTLEMENT_SNAPSHOT_UNVERIFIED")
    snapshots = paths[0]
    settlement_states_unchanged(snapshots, permit["max_total_bytes"])
    snapshot_bytes = snapshot_footprint(snapshots, permit["max_total_bytes"])
    require(snapshot_bytes < permit["max_total_bytes"], "NO_DATABASE_DUMP_BUDGET")
    censuses, dumps = {}, {}
    for lane in ("hd", "de"):
        verify_current_fence(receipt_path, scope_digest(), runner=runner)
        # HD and DE need not be similarly sized. Bound each child by the
        # aggregate bytes still available, rather than reserving half for each.
        remaining = permit["max_total_bytes"] - snapshot_bytes - sum(x["bytes"] for x in dumps.values())
        require(remaining > 0, "NO_DATABASE_DUMP_BUDGET")
        contract = permit["databases"][lane]
        env = pg_environment(contract)
        before = financial_census(contract, env, runner)
        dump = output / (lane + ".dump")
        runner(["pg_dump", "--no-password", "--format=custom", "--serializable-deferrable",
                "--file", str(dump)], env=env, timeout=300,
               file_limit=remaining)
        require(dump.stat().st_size > 0 and not dump.is_symlink(), "DATABASE_DUMP_EMPTY")
        require(dump.stat().st_size <= remaining, "BACKUP_FOOTPRINT_EXCEEDED")
        os.chmod(dump, 0o600)
        after = financial_census(contract, env, runner)
        require(before == after, "FINANCIAL_DATABASE_CHANGED_DURING_DUMP")
        censuses[lane] = before
        dumps[lane] = {"sha256": file_sha(dump), "bytes": dump.stat().st_size}
    verify_current_fence(receipt_path, scope_digest(), runner=runner)
    # Re-read both lanes after both dumps: separate transactions are not an
    # atomic distributed snapshot; equality plus witnessed quiescence is required.
    for lane in ("hd", "de"):
        require(financial_census(permit["databases"][lane],
                pg_environment(permit["databases"][lane]), runner) == censuses[lane],
                "CROSS_DATABASE_QUIESCENCE_LOST")
    settlement_states_unchanged(snapshots, permit["max_total_bytes"])
    require(snapshot_bytes + sum(x["bytes"] for x in dumps.values()) <= permit["max_total_bytes"],
            "BACKUP_FOOTPRINT_EXCEEDED")
    manifest = {"schema": "wolo.quiesced-financial-backup.v1", "fence_receipt_sha256": file_sha(receipt_path),
                "scope_sha256": scope_digest(), "databases": dumps, "financial_censuses": censuses,
                "settlement_snapshot": str(snapshots), "settlement_snapshot_receipt_sha256":
                file_sha(snapshots / "proof/RECEIPT.txt"), "isolated_restore_verified": False,
                "off_host_copy_verified": False, "financial_release_authorized": False}
    # Hashes/censuses are potentially slow I/O. Do not publish success using
    # fence authority checked before those reads completed.
    verify_current_fence(receipt_path, scope_digest(), runner=runner)
    write_new(output / "backup.json", canonical(manifest))
    # INCOMPLETE remains until an actual isolated restore and equality check.
    return manifest


def _bounded_restore_mount():
    """Verify a preprovisioned finite loop/ext4 device; NEVER create or mount it.

    Root-only wrapper and full-allocation backing file stay on the OS root.
    Disposable PostgreSQL data lives on the bounded ext4 child mount only.
    A missing/changed loop association, mount or image refuses all admission.
    """
    root_dev = Path("/").stat().st_dev
    require(os.path.ismount(VOLUME) and VOLUME.stat().st_dev != root_dev,
            "RESTORE_VOLUME_MOUNT_UNVERIFIED")
    require(RESTORE_SCRATCH == Path("/var/lib/wolo-financial-restore") and
            not RESTORE_SCRATCH.is_symlink() and not os.path.ismount(RESTORE_SCRATCH),
            "RESTORE_SCRATCH_PATH_UNSAFE")
    wrapper = RESTORE_SCRATCH.lstat()
    require(stat.S_ISDIR(wrapper.st_mode) and wrapper.st_uid == wrapper.st_gid == 0 and
            stat.S_IMODE(wrapper.st_mode) == 0o700 and wrapper.st_dev == root_dev,
            "RESTORE_SCRATCH_ROOT_NOT_QUALIFIED")
    mount = RESTORE_SCRATCH / "bounded"
    backing = RESTORE_SCRATCH / "bounded.ext4"
    require({item.name for item in RESTORE_SCRATCH.iterdir()} ==
            {"bounded", "bounded.ext4"}, "RESTORE_WRAPPER_EXTRA_MEMBERS")
    f = backing.lstat()
    require(stat.S_ISREG(f.st_mode) and not backing.is_symlink() and
            f.st_uid == f.st_gid == 0 and stat.S_IMODE(f.st_mode) == 0o600 and
            f.st_dev == root_dev and f.st_nlink == 1 and
            (8 << 30) <= f.st_size <= (64 << 30) and
            f.st_blocks * 512 >= f.st_size,
            "RESTORE_BACKING_NOT_FULLY_ALLOCATED")
    m = mount.lstat()
    require(stat.S_ISDIR(m.st_mode) and not mount.is_symlink() and
            m.st_uid == m.st_gid == 0 and stat.S_IMODE(m.st_mode) == 0o700 and
            m.st_dev != root_dev and m.st_dev != VOLUME.stat().st_dev and
            os.path.ismount(mount), "RESTORE_BOUNDED_MOUNT_UNVERIFIED")
    # Compare the kernel's exact mount identity and loop association, not
    # filesystem labels or human-supplied values. No shell or mount mutation.
    matches = []
    with open("/proc/self/mountinfo", encoding="utf-8") as source:
        for n, line in enumerate(source):
            require(n < 8192, "RESTORE_MOUNT_TABLE_TOO_LARGE")
            halves = line.rstrip("\n").split(" - ", 1)
            require(len(halves) == 2, "RESTORE_MOUNT_TABLE_UNVERIFIED")
            left, right = halves[0].split(), halves[1].split()
            require(len(left) >= 6 and len(right) >= 2,
                    "RESTORE_MOUNT_TABLE_UNVERIFIED")
            if left[4] == str(mount):
                matches.append((left, right))
    require(len(matches) == 1, "RESTORE_MOUNT_IDENTITY_UNVERIFIED")
    left, right = matches[0]
    major_minor = "%d:%d" % (os.major(m.st_dev), os.minor(m.st_dev))
    require(left[2] == major_minor and left[3] == "/" and
            right[0] == "ext4" and re.fullmatch(r"/dev/loop[0-9]+", right[1]) and
            {"rw", "nodev", "nosuid", "noexec"}.issubset(set(left[5].split(","))),
            "RESTORE_MOUNT_POLICY_UNVERIFIED")
    device = os.stat(right[1])
    require(stat.S_ISBLK(device.st_mode) and device.st_rdev == m.st_dev,
            "RESTORE_LOOP_DEVICE_MISMATCH")
    backing_file = Path("/sys/dev/block") / major_minor / "loop/backing_file"
    observed = backing_file.read_text(encoding="utf-8").strip()
    require(observed == str(backing) and os.path.realpath(observed) == str(backing),
            "RESTORE_LOOP_BACKING_MISMATCH")
    fs = os.statvfs(mount)
    require(0 < fs.f_blocks * fs.f_frsize <= f.st_size and
            fs.f_bavail * fs.f_frsize >= 0,
            "RESTORE_FINITE_CAPACITY_UNVERIFIED")
    return mount, f, fs


def _restore_scratch_admission(budget):
    """Admit only finite allocated loop storage with per-permit free capacity."""
    require(type(budget) is int and budget > 0 and budget <= 100 << 30,
            "RESTORE_CAPACITY_BUDGET_INVALID")
    mount, image, fs = _bounded_restore_mount()
    free = fs.f_bavail * fs.f_frsize
    require(free >= budget * RESTORE_DATA_FACTOR and
            fs.f_blocks * fs.f_frsize <= image.st_size,
            "RESTORE_BOUNDED_CAPACITY_INSUFFICIENT")
    root_fs = os.statvfs(RESTORE_SCRATCH)
    require(root_fs.f_bavail * root_fs.f_frsize >= RESTORE_OS_RESERVE,
            "RESTORE_OS_ROOT_CAPACITY_INSUFFICIENT")
    require(not any(p.name.startswith("restore-") for p in mount.iterdir()),
            "INTERRUPTED_RESTORE_SCRATCH_REQUIRES_SEPARATE_REVIEW")
    require(shutil.rmtree.avoids_symlink_attacks,
            "SYMLINK_SAFE_RESTORE_CLEANUP_UNAVAILABLE")
    return mount


def make_restore_scratch(budget):
    """Create only a new private PGDATA child on verified bounded ext4."""
    mount = _restore_scratch_admission(budget)
    fd = os.open(mount, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        name = "restore-" + secrets.token_hex(16)
        os.mkdir(name, 0o700, dir_fd=fd)
        os.chown(name, 999, 999, dir_fd=fd, follow_symlinks=False)
        child = mount / name
        meta = child.lstat()
        require(stat.S_ISDIR(meta.st_mode) and meta.st_uid == meta.st_gid == 999 and
                stat.S_IMODE(meta.st_mode) == 0o700 and
                meta.st_dev == mount.stat().st_dev,
                "RESTORE_CHILD_IDENTITY_INVALID")
        return child
    finally:
        os.close(fd)


def cleanup_restore_scratch(path):
    """Only remove a verified owned child while the same bounded mount lives."""
    mount, _, _ = _bounded_restore_mount()
    path = Path(path)
    require(path.parent == mount and
            re.fullmatch(r"restore-[0-9a-f]{32}", path.name) is not None and
            path.is_dir() and not path.is_symlink() and
            path.lstat().st_dev == mount.stat().st_dev and
            shutil.rmtree.avoids_symlink_attacks,
            "RESTORE_CLEANUP_IDENTITY_UNVERIFIED")
    shutil.rmtree(path)


def restore_isolated(receipt_path, output, *, runner=None):
    """Real pg_restore in an existing pinned, network-none disposable container.

    No host PG socket, environment, keyring or production volume is mounted.
    Archives are piped through stdin. One exact private OS-root PGDATA bind mount
    replaces memory-backed PGDATA; there are no production/volume mounts.
    No image pull occurs. Root scratch must be preprovisioned and budgeted.
    """
    runner = runner or run
    cleanup_runner = runner
    observed = verify_current_fence(receipt_path, scope_digest(), runner=runner)
    permit = observed["permit"]
    runner = bounded_runner(runner, permit)
    output = Path(output)
    require(output.parent == BACKUPS and output.is_dir() and not output.is_symlink(), "BACKUP_PATH_INVALID")
    manifest, _ = private_json(output / "backup.json")
    require(manifest.get("scope_sha256") == scope_digest() and
            manifest.get("fence_receipt_sha256") == file_sha(receipt_path) and
            manifest.get("isolated_restore_verified") is False and
            (output / "INCOMPLETE").is_file(), "BACKUP_AUTHORITY_INVALID")
    for lane in ("hd", "de"):
        require(file_sha(output / (lane + ".dump")) == manifest["databases"][lane]["sha256"],
                "DATABASE_DUMP_CHECKSUM_MISMATCH")
    name = "wolo-financial-restore-" + secrets.token_hex(12)
    require(runner(DOCKER + ["image", "inspect", "--format", "{{.Id}}", permit["restore_image"]]).strip(),
            "EXISTING_PINNED_IMAGE_UNAVAILABLE")
    scratch = make_restore_scratch(permit["max_total_bytes"])
    container = None
    owned = False
    mount = "type=bind,src=" + str(scratch) + ",dst=/var/lib/postgresql/data,bind-propagation=rprivate"
    cmd = DOCKER + ["run", "--detach", "--pull=never", "--name", name,
           "--network=none", "--read-only", "--cap-drop=ALL", "--security-opt=no-new-privileges",
           "--user=999:999", "--pids-limit=128", "--memory=2g", "--cpus=2",
           "--mount", mount,
           "--tmpfs", "/var/run/postgresql:rw,noexec,nosuid,size=16777216,mode=1777",
           "--env=PGDATA=/var/lib/postgresql/data/isolated",
           "--env=POSTGRES_HOST_AUTH_METHOD=trust",
           "--label=wolo.financial-maintenance=" + scope_digest(), permit["restore_image"]]
    # Never fall back to memory-backed PGDATA or Docker's Wolo-volume storage.
    try:
        container = runner(cmd).strip()
        require(re.fullmatch(r"[0-9a-f]{64}", container), "NEW_CONTAINER_ID_UNVERIFIED")
    except BaseException:
        # No trusted container ID: leave private scratch for operator evidence.
        # The next admission fails closed on this interrupted restore.
        raise
    prefix = DOCKER + ["exec", "--interactive", "--user=999:999", container]
    try:
        details = json.loads(runner(DOCKER + ["inspect", container]))
        require(type(details) is list and len(details) == 1, "CONTAINER_IDENTITY_UNVERIFIED")
        detail = details[0]
        require(detail["Id"] == container and detail["Config"]["Image"] == permit["restore_image"]
            and detail["Config"]["User"] == "999:999"
            and detail["Config"]["Labels"].get("wolo.financial-maintenance") == scope_digest()
            and detail["HostConfig"]["NetworkMode"] == "none"
            and detail["HostConfig"]["ReadonlyRootfs"] is True
            and detail["HostConfig"]["Privileged"] is False
            and type(detail.get("Mounts")) is list and len(detail["Mounts"]) == 1
            and detail["Mounts"][0].get("Type") == "bind"
            and detail["Mounts"][0].get("Source") == str(scratch)
            and detail["Mounts"][0].get("Destination") == "/var/lib/postgresql/data"
            and detail["Mounts"][0].get("RW") is True,
            "DISPOSABLE_NETWORK_ISOLATION_UNVERIFIED")
        _bounded_restore_mount()  # Guard the bind source again before any database restore.
        owned = True
        deadline = time.monotonic() + 30
        while True:
            try:
                require(runner(prefix + ["cat", "/proc/1/comm"], timeout=3).strip() == "postgres",
                        "ISOLATED_POSTGRES_STILL_BOOTSTRAPPING")
                runner(prefix + ["pg_isready", "--host=/var/run/postgresql", "--username=postgres"], timeout=3)
                break
            except MaintenanceError:
                require(time.monotonic() < deadline, "ISOLATED_POSTGRES_START_TIMEOUT")
                time.sleep(0.25)
        for lane in ("hd", "de"):
            verify_current_fence(receipt_path, scope_digest(), runner=runner)
            db = "wolo_restore_" + lane
            runner(prefix + ["createdb", "--host=/var/run/postgresql", "--username=postgres", db])
            runner(prefix + ["pg_restore", "--host=/var/run/postgresql", "--username=postgres",
                             "--no-owner", "--no-privileges", "--exit-on-error", "--single-transaction",
                             "--dbname=" + db], stdin_file=output / (lane + ".dump"), timeout=300)
            contract = dict(permit["databases"][lane], database_sha256=digest(db.encode()))
            # Same native SQL comparisons inside the isolated container. Never
            # pass host credentials/env to docker exec or the restored database.
            env = {"PGDATABASE": db}
            def isolated_run(argv, **kwargs):
                require(argv[0] == "psql", "ISOLATED_COMMAND_NOT_ALLOWED")
                return runner(prefix + ["psql", "--quiet", "--host=/var/run/postgresql", "--username=postgres",
                    "--dbname=" + db, "--no-psqlrc", "--tuples-only", "--no-align", "--set=ON_ERROR_STOP=1",
                    "--set=VERBOSITY=terse"], input="SET default_transaction_read_only=on; SET timezone='UTC';\n" +
                    kwargs["input"], timeout=70).strip()
            require(financial_census(contract, env, isolated_run) == manifest["financial_censuses"][lane],
                    "RESTORED_FINANCIAL_INTEGRITY_MISMATCH")
        verify_current_fence(receipt_path, scope_digest(), runner=runner)
        for lane in ("hd", "de"):
            require(file_sha(output / (lane + ".dump")) == manifest["databases"][lane]["sha256"],
                    "DATABASE_DUMP_CHANGED_DURING_RESTORE")
        _bounded_restore_mount()  # Fail closed if mount/loop identity drifted during restoration.
        settlement_states_unchanged(Path(manifest["settlement_snapshot"]), permit["max_total_bytes"])
        receipt = {"schema": "wolo.isolated-financial-restore.v1",
                   "scope_sha256": scope_digest(), "fence_receipt_sha256": file_sha(receipt_path),
                   "isolated_restore_verified": True,
                   "settlement_snapshot_receipt_sha256": manifest["settlement_snapshot_receipt_sha256"],
                   "backup_manifest_sha256":
                   file_sha(output / "backup.json"), "restore_image": permit["restore_image"],
                   "both_financial_censuses_match": True, "network": "none",
                   "production_state_restored": False, "off_host_copy_verified": False,
                   "independent_witness_attested": False, "owner_and_privilege_recovery_proven": False,
                   "financial_release_authorized": False}
    finally:
        # Cleanup must complete BEFORE publishing verified restore authority.
        # If Docker removal or scratch cleanup fails, INCOMPLETE remains and
        # no restore.json exists for a later rehearsal to admit.
        if owned:
            # Never delete a mounted PGDATA directory while its container lives.
            cleanup_runner(DOCKER + ["rm", "--force", container], timeout=15)
            cleanup_restore_scratch(scratch)
        # If container identity verification failed, preserve scratch and HOLD.
        # Its path is root-private and the next operation rejects orphan state.

    mount, _, _ = _bounded_restore_mount()
    require(not any(p.name.startswith("restore-") for p in mount.iterdir()),
            "RESTORE_SCRATCH_NOT_CLEAN_AFTER_RUN")
    verify_current_fence(receipt_path, scope_digest(), runner=runner)

    # No successful receipt may outlive a failed cleanup. A failed write/unlink
    # keeps INCOMPLETE until a separately reviewed recovery can continue.
    write_new(output / "restore.json", canonical(receipt))
    (output / "INCOMPLETE").unlink()
    return receipt


def verify_current_backup(restore_receipt_path, expected_scope_sha256,
                          expected_fence_receipt_sha256):
    """Read-only small-receipt admission; no multi-GB rehash or inferred witness.

    Actual restore already compared archive bytes/financial census. Current file
    identity and full-copy survival remain independently witnessed requirements.
    """
    path = Path(restore_receipt_path)
    require(path.name == "restore.json" and path.parent.parent == BACKUPS,
            "FINAL_ISOLATED_RESTORE_RECEIPT_REQUIRED")
    restore, restore_sha = private_json(path)
    manifest, manifest_sha = private_json(path.with_name("backup.json"))
    require(restore.get("schema") == "wolo.isolated-financial-restore.v1" and
            restore.get("isolated_restore_verified") is True and
            restore.get("both_financial_censuses_match") is True and restore.get("network") == "none" and
            restore.get("production_state_restored") is False and
            restore.get("financial_release_authorized") is False and
            restore.get("scope_sha256") == manifest.get("scope_sha256") == expected_scope_sha256 == scope_digest() and
            restore.get("fence_receipt_sha256") == manifest.get("fence_receipt_sha256") == expected_fence_receipt_sha256 and
            restore.get("backup_manifest_sha256") == manifest_sha and
            not path.with_name("INCOMPLETE").exists(), "ISOLATED_BACKUP_AUTHORITY_UNVERIFIED")
    snapshot = Path(manifest.get("settlement_snapshot", ""))
    require(snapshot.parent == SNAPSHOT_ROOT and not (snapshot / "INCOMPLETE").exists(),
            "PROTECTED_SNAPSHOT_UNAVAILABLE")
    raw = private_read(snapshot / "proof/RECEIPT.txt")
    require(digest(raw) == manifest.get("settlement_snapshot_receipt_sha256") ==
            restore.get("settlement_snapshot_receipt_sha256"), "SNAPSHOT_RECEIPT_CHANGED")
    return {"scope_sha256": expected_scope_sha256,
            "fence_receipt_sha256": expected_fence_receipt_sha256,
            "restore_receipt_sha256": restore_sha, "backup_manifest_sha256": manifest_sha,
            "settlement_snapshot_receipt_sha256": digest(raw),
            "isolated_restore_verified": True, "independent_witness_attested": False,
            "financial_release_authorized": False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("scope", "inspect-storage", "verify-fence", "fence", "backup", "restore-isolated"),
                        default="scope")
    parser.add_argument("--permit", type=Path)
    parser.add_argument("--fence-receipt", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.mode == "scope":
            print(json.dumps({"units": UNITS, "scope_sha256": scope_digest(), "hold_path": str(HOLD),
                              "activation_or_resume_authorized": False}, sort_keys=True))
            return 3
        require(os.geteuid() == 0, "ROOT_REQUIRED")
        if args.mode == "inspect-storage":
            # Read only: invoke the EXACT production mount/backing identity
            # guard without a finance permit, lock, backup or service change.
            mount, backing, fs = _bounded_restore_mount()
            require(not any(p.name.startswith("restore-") for p in mount.iterdir()),
                    "INTERRUPTED_RESTORE_SCRATCH_REQUIRES_SEPARATE_REVIEW")
            rootfs = os.statvfs(RESTORE_SCRATCH)
            root_free = rootfs.f_bavail * rootfs.f_frsize
            require(root_free >= RESTORE_OS_RESERVE,
                    "RESTORE_OS_ROOT_CAPACITY_INSUFFICIENT")
            print(json.dumps({
                "schema": "wolo.bounded-restore-storage-inspection.v1",
                "status": "STORAGE_OBSERVED_ONLY",
                "backing_logical_bytes": backing.st_size,
                "backing_allocated_bytes": backing.st_blocks * 512,
                "bounded_total_bytes": fs.f_blocks * fs.f_frsize,
                "bounded_available_bytes": fs.f_bavail * fs.f_frsize,
                "root_available_bytes": root_free,
                "storage_mount_identity_verified": True,
                "financial_writers_quiesced": False,
                "backup_or_restore_authorized": False,
                "financial_release_authorized": False
            }, sort_keys=True))
            return 3
        require(args.fence_receipt is not None, "FENCE_RECEIPT_REQUIRED")
        if args.mode == "verify-fence":
            verify_current_fence(args.fence_receipt, scope_digest())
            print(json.dumps({"status": "CURRENT_FENCE_OBSERVED", "resume_authorized": False,
                              "financial_release_authorized": False}))
            return 3
        fd = os.open(LOCK, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "a") as lock:
            meta = os.fstat(fd)
            require(stat.S_ISREG(meta.st_mode) and meta.st_uid == 0 and meta.st_nlink == 1 and
                    stat.S_IMODE(meta.st_mode) == 0o600, "UNSAFE_MAINTENANCE_LOCK")
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            if args.mode == "fence":
                require(args.permit is not None, "EXACT_PERMIT_REQUIRED")
                fence(args.permit, args.fence_receipt)
            else:
                require(args.output is not None, "BACKUP_OUTPUT_REQUIRED")
                (backup if args.mode == "backup" else restore_isolated)(args.fence_receipt, args.output)
        print(json.dumps({"status": "SCOPED_OPERATION_COMPLETE", "resume_authorized": False,
                          "financial_release_authorized": False}))
        return 0
    except (MaintenanceError, OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as exc:
        reason = str(exc) if isinstance(exc, MaintenanceError) else "SAFE_OPERATION_UNAVAILABLE"
        print(json.dumps({"status": "BLOCKED", "reason": reason, "hold_must_remain": True,
                          "financial_release_authorized": False}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

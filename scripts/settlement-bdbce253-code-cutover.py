#!/usr/bin/env python3
"""Exact-version, two-settlement SERVICE-CODE switch / recovery. No bank-state restore.

Root-only, explicit short-lived external finance permit required before mutation.
Default --inspect is nonmutating. NEVER touches Wolo consensus or resumes HD/DE
signers. A permit is a human-approved release artifact, NOT proof that its claims
are true. It must only be issued after separately witnessed financial controls.

The only mutable financial-service paths are two dedicated systemd override files. The
original executable is never overwritten; original request/run state is never
copied, truncated, changed or rewound. A partial application is fail-closed and
offers code-only recovery after the same verified maintenance authority.
First rehearsal additionally retains a private, nonfinancial control journal
and an independent systemd watchdog; neither grants production or resume authority.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import re
import selectors
import signal
import stat
import subprocess
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

OLD = "/usr/local/bin/wolochaind-mainnet"
NODE = "/usr/local/bin/wolochaind-mainnet-node-prewartrophy"
NEW = ("/mnt/HC_Volume_105319120/wolochain-mainnet/"
       "settlement-candidates/bdbce253-UNDEPLOYED/"
       "wolochaind-settlement-only-linux-amd64")
OLD_SHA = "040126a2884946caf1651a50b7d8115c5a6fb2d5aa94fcbbe150694602d451a5"
NODE_SHA = "4b77f622191db7550cb87cafb8f1886a0aadebee3eb6565f9f90036f809e61d3"
NEW_SHA = "44d8aed5550d1b33635c734c1a359d0cb69e854093ef8c9a8a3da4f99d416ede"
REV = "bdbce253c524d6faac14f61cd129ac5072287c3f"
OLD_REV = "78c25985420ee41a6678c42fab8ea8d6c3b1b519"
CHECKOUT = "/var/www/WoloChain-wolo-1"
READ_ONLY_MODES = {"inspect", "source-authority"}
MAX_COMMAND_BYTES = 1 << 20
PRIMARY = "wolochain-mainnet-settlement.service"
FOUNDER = "wolochain-founder-rewards-settlement.service"
CONSENSUS = "wolochaind-mainnet.service"
SERVICES = (PRIMARY, FOUNDER)
OVERRIDE = "50-aoe2war-bdbce253-settlement-only.conf"
EXACT_APPROVAL = "I approve an isolated two-settlement code-only cutover; payouts remain fenced"
# systemd Type=simple may report active before the HTTP listener binds.
# Transient transport failures alone may be retried for this bounded interval.
STARTUP_HEALTH_GRACE_SECONDS = 15.0
STARTUP_HEALTH_POLL_SECONDS = 0.25
ATTESTED = {
    "hd_de_producers_isolated",
    "inflight_requests_and_accepted_tx_reconciled",
    "claim_889_liability_preserved_and_release_reviewed",
    "fresh_quiesced_backup_hash_verified",
    "reviewed_code_only_rollback_rehearsed",
    "bank_solvent_and_independently_checked",
}
REHEARSAL_CONTROLS = ATTESTED - {"reviewed_code_only_rollback_rehearsed"}
REHEARSAL_SCHEMA = "aoe2war.wolochain.first-settlement-rehearsal.v1"
RECOVERY_SCHEMA = "aoe2war.wolochain.fresh-rehearsal-recovery.v1"
REHEARSAL_APPROVAL = (
    "I approve a witnessed first two-settlement old-to-candidate-to-old rehearsal; payouts remain fenced"
)
RECOVERY_APPROVAL = (
    "I approve fresh recovery of both settlement lanes to original code; payouts remain fenced"
)
REHEARSAL_ROOT = Path("/var/lib/aoe2war-wolo-first-rehearsal")
FENCE_TOOL = Path(__file__).resolve().with_name("settlement_financial_maintenance.py")
HEX64 = re.compile(r"[a-f0-9]{64}")
EXECUTION_ID = re.compile(r"[a-f0-9]{32}")


class Blocked(RuntimeError):
    pass


def require(ok: bool, message: str) -> None:
    if not ok:
        raise Blocked(message)


def sha_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            h.update(block)
    return h.hexdigest()


def expected_override() -> bytes:
    return (
        "# AOE2WAR bdbce253 two-settlement code-only; leave request/run state untouched\n"
        "[Service]\n"
        "ExecStart=\n"
        f"ExecStart={NEW} settlement serve\n"
    ).encode()


def _read_release_permit(path: Path) -> bytes:
    require(path.is_absolute(), "release permit must be an absolute protected file")
    require(hasattr(os, "O_NOFOLLOW"), "no-follow permit reads unavailable")
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except OSError as exc:
        raise Blocked("release permit must be a regular non-symlink protected file") from exc
    try:
        before = os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and before.st_uid == 0 and before.st_gid == 0 and
                stat.S_IMODE(before.st_mode) == 0o600 and 0 <= before.st_size < 8192,
                "release permit requires root:root mode 0600 regular file and size below 8KiB")
        data = os.read(fd, 8192)
        require(len(data) == before.st_size and len(data) < 8192,
                "release permit changed or exceeded read limit")
        after = os.fstat(fd)
        fields = ("st_dev", "st_ino", "st_uid", "st_gid", "st_mode", "st_size",
                  "st_mtime_ns", "st_ctime_ns", "st_nlink")
        require(all(getattr(before, key) == getattr(after, key) for key in fields),
                "release permit changed during read")
        current = os.stat(path, follow_symlinks=False)
        require(stat.S_ISREG(current.st_mode) and
                (current.st_dev, current.st_ino) == (before.st_dev, before.st_ino),
                "release permit path changed during read")
        return data
    finally:
        os.close(fd)


def _unique_permit_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "duplicate release permit JSON field")
        result[key] = value
    return result


def load_release_permit(path: Path, *, now: datetime | None = None) -> dict:
    """Operator-issued receipt; NEVER inferred from CI/test booleans."""
    try:
        permit = json.loads(_read_release_permit(path), object_pairs_hook=_unique_permit_object)
    except (ValueError, OSError, RecursionError) as exc:
        raise Blocked("invalid release permit JSON") from exc
    require(isinstance(permit, dict), "invalid permit document")
    require(set(permit) == {"schema", "candidateRevision", "candidateSha256",
                             "operator", "issuedAtUtc", "expiresAtUtc",
                             "approval", "witnessedControls"},
            "permit fields missing or unexpected")
    require(permit["schema"] == "aoe2war.wolochain.two-settlement-code-only.v1"
            and permit["candidateRevision"] == REV
            and permit["candidateSha256"] == NEW_SHA,
            "permit target is not the exact reviewed implementation")
    require(permit["approval"] == EXACT_APPROVAL, "explicit approval text absent")
    require(isinstance(permit["operator"], str)
            and re.fullmatch(r"[A-Za-z0-9_.@-]{3,80}", permit["operator"]) is not None,
            "operator identity missing")
    require(isinstance(permit["witnessedControls"], list) and
            len(permit["witnessedControls"]) == len(ATTESTED) and
            all(isinstance(control, str) for control in permit["witnessedControls"]) and
            set(permit["witnessedControls"]) == ATTESTED,
            "release permit lacks independent finance/control reviews")
    try:
        created = datetime.fromisoformat(permit["issuedAtUtc"].replace("Z", "+00:00"))
        expiry = datetime.fromisoformat(permit["expiresAtUtc"].replace("Z", "+00:00"))
    except (TypeError, ValueError, AttributeError) as exc:
        raise Blocked("permit timestamps not valid UTC ISO format") from exc
    require(created.tzinfo is not None and expiry.tzinfo is not None and
            created.utcoffset() == timedelta(0) and expiry.utcoffset() == timedelta(0),
            "permit timestamps must be UTC")
    # Acquisition and parsing may have consumed the entire authorization
    # window. Production time is sampled only after those operations finish.
    now = now if now is not None else datetime.now(timezone.utc)
    require(now - timedelta(minutes=5) <= created <= now and
            now < expiry <= created + timedelta(minutes=10),
            "expired, future, or overlong release permit")
    return permit


class ReleaseAuthority:
    """Revalidate the original operator approval; never adopt a renewal mid-run.

    The existing public permit shape is unchanged. The binding covers every
    validated field (including operator, times and witnessed controls). File
    removal, invalid ownership, expiry or any changed field fails closed.
    """
    def __init__(self, path: Path):
        self.path = path
        self.original = self._binding(load_release_permit(path))

    @staticmethod
    def _binding(permit: dict) -> str:
        return json.dumps(permit, sort_keys=True, separators=(",", ":"))

    def check(self) -> None:
        current = load_release_permit(self.path)
        require(self._binding(current) == self.original,
                "release permit changed since original approval")


def utc(value) -> datetime:
    require(isinstance(value, str) and re.fullmatch(
        r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{1,6})?Z", value
    ) is not None, "explicit UTC timestamp required")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise Blocked("invalid UTC timestamp") from exc


def validate_rehearsal_permit(doc: dict, *, recovery=False, now=None) -> dict:
    """Human evidence references, NOT verification or an all-six release permit."""
    fields = {"schema", "executionId", "candidateRevision", "candidateSha256",
              "originalSha256", "consensusSha256", "owner", "operator", "recoveryWitness",
              "approvalRefs", "packetSha256", "procedureSha256", "backupReceiptSha256", "backupReceiptPath",
              "fenceScopeSha256", "fenceReceiptSha256", "fenceReceiptPath",
              "toolSha256", "fenceToolSha256", "windowStartUtc", "windowEndUtc",
              "issuedAtUtc", "expiresAtUtc", "approval", "witnessedControls"}
    if recovery:
        fields.add("sessionSha256")
    require(isinstance(doc, dict) and set(doc) == fields,
            "rehearsal authority fields missing or unexpected")
    require(doc["schema"] == (RECOVERY_SCHEMA if recovery else REHEARSAL_SCHEMA),
            "distinct rehearsal/recovery authority required")
    require(doc["approval"] == (RECOVERY_APPROVAL if recovery else REHEARSAL_APPROVAL),
            "explicit rehearsal/recovery approval absent")
    require(doc["candidateRevision"] == REV and doc["candidateSha256"] == NEW_SHA and
            doc["originalSha256"] == OLD_SHA and doc["consensusSha256"] == NODE_SHA,
            "rehearsal binary/source pins differ")
    require(isinstance(doc["executionId"], str) and EXECUTION_ID.fullmatch(doc["executionId"]),
            "invalid rehearsal execution identity")
    for key in ("owner", "operator", "recoveryWitness"):
        require(isinstance(doc[key], str) and re.fullmatch(r"[A-Za-z0-9_.@-]{3,80}", doc[key]),
                "named owner/operator/witness authority required")
    require(doc["recoveryWitness"] not in (doc["owner"], doc["operator"]),
            "separate recovery witness required")
    refs = doc["approvalRefs"]
    require(isinstance(refs, dict) and set(refs) == {
        "owner", "operator", "chainReviewer", "financeReviewer", "recoveryWitness"
    } and all(isinstance(value, str) and HEX64.fullmatch(value) and value != "0" * 64
              for value in refs.values()),
            "scoped human approval references required")
    for key in ("packetSha256", "procedureSha256", "backupReceiptSha256", "fenceScopeSha256",
                "fenceReceiptSha256", "toolSha256", "fenceToolSha256") + (
                    ("sessionSha256",) if recovery else ()
                ):
        require(isinstance(doc[key], str) and HEX64.fullmatch(doc[key]) and doc[key] != "0" * 64,
                "exact rehearsal evidence/source fingerprint required")
    require(all(isinstance(doc[key], str) and Path(doc[key]).is_absolute()
                for key in ("fenceReceiptPath", "backupReceiptPath")),
            "absolute protected fence/isolated-restore receipts required")
    controls = doc["witnessedControls"]
    require(isinstance(controls, list) and len(controls) == len(REHEARSAL_CONTROLS) and
            all(isinstance(value, str) for value in controls) and set(controls) == REHEARSAL_CONTROLS,
            "other five independently witnessed controls required; no invented prior rehearsal")
    start, end = utc(doc["windowStartUtc"]), utc(doc["windowEndUtc"])
    created, expiry = utc(doc["issuedAtUtc"]), utc(doc["expiresAtUtc"])
    now = now or datetime.now(timezone.utc)
    require(timedelta(0) < end - start <= timedelta(minutes=30) and start <= now < end,
            "rehearsal outside exact bounded maintenance window")
    require(start <= created <= now and now - timedelta(minutes=5) <= created and
            now < expiry <= min(end, created + timedelta(minutes=10)),
            "expired, future or overlong rehearsal authority")
    return doc


def load_rehearsal_permit(path: Path, *, recovery=False, now=None) -> dict:
    try:
        doc = json.loads(_read_release_permit(path), object_pairs_hook=_unique_permit_object)
    except (ValueError, OSError, RecursionError, UnicodeError) as exc:
        raise Blocked("invalid rehearsal authority JSON") from exc
    return validate_rehearsal_permit(doc, recovery=recovery, now=now)


def protected_bytes(path: Path, *, maximum=65536, private=True) -> bytes:
    """Stable root-owned source/receipt read; reject writable/symlink ancestors."""
    require(path.is_absolute() and hasattr(os, "O_NOFOLLOW"), "protected absolute path required")
    for parent in (path.parent, *path.parent.parents):
        info = parent.lstat()
        require(stat.S_ISDIR(info.st_mode) and info.st_uid == 0 and not info.st_mode & 0o022,
                "protected parent ownership/type/permissions differ")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        before = os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and before.st_uid == 0 and before.st_gid == 0 and
                before.st_nlink == 1 and 0 <= before.st_size <= maximum and
                (stat.S_IMODE(before.st_mode) == 0o600 if private else not before.st_mode & 0o022),
                "protected file ownership/type/permissions/size differ")
        data = os.read(fd, maximum + 1)
        after = os.fstat(fd)
        fields = ("st_dev", "st_ino", "st_mode", "st_uid", "st_gid", "st_size",
                  "st_mtime_ns", "st_ctime_ns", "st_nlink")
        current = path.lstat()
        require(len(data) == before.st_size and len(data) <= maximum and
                all(getattr(before, key) == getattr(after, key) == getattr(current, key) for key in fields),
                "protected file changed during read")
        return data
    finally:
        os.close(fd)


def private_json(path: Path) -> dict:
    try:
        doc = json.loads(protected_bytes(path), object_pairs_hook=_unique_permit_object)
    except (ValueError, OSError, RecursionError, UnicodeError) as exc:
        raise Blocked("invalid private rehearsal record") from exc
    require(isinstance(doc, dict), "private rehearsal record must be object")
    return doc


def record_once(path: Path, doc: dict) -> None:
    """Immutable new operational record, NEVER a financial journal/checklist."""
    protected_bytes(Path(__file__).resolve(), maximum=1 << 20, private=False)
    require(path.parent.is_dir() and not path.parent.is_symlink(), "private record parent absent")
    parent = path.parent.stat()
    require(parent.st_uid == 0 and parent.st_gid == 0 and stat.S_IMODE(parent.st_mode) == 0o700,
            "private rehearsal directory must be root:root 0700")
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as output:
        output.write((json.dumps(doc, sort_keys=True, separators=(",", ":")) + "\n").encode())
        output.flush()
        os.fsync(output.fileno())
    directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def sync_directory(path: Path) -> None:
    """Persist new control-journal directory entries before service mutations."""
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        info = os.fstat(fd)
        require(stat.S_ISDIR(info.st_mode) and info.st_uid == 0 and info.st_gid == 0 and
                not info.st_mode & 0o022, "unsafe control-journal ancestor")
        os.fsync(fd)
    finally:
        os.close(fd)


def check_rehearsal_sources(doc: dict) -> None:
    require(hashlib.sha256(protected_bytes(Path(__file__).resolve(), maximum=1 << 20,
                                         private=False)).hexdigest() == doc["toolSha256"],
            "rehearsal controller source drift")
    require(hashlib.sha256(protected_bytes(FENCE_TOOL, maximum=1 << 20,
                                         private=False)).hexdigest() == doc["fenceToolSha256"],
            "producer fence verifier source drift")


def fence_check(doc: dict) -> None:
    """The existing maintenance module owns actual persistent producer gates."""
    check_rehearsal_sources(doc)
    raw = protected_bytes(Path(doc["fenceReceiptPath"]))
    require(hashlib.sha256(raw).hexdigest() == doc["fenceReceiptSha256"], "fence receipt drift")
    spec = importlib.util.spec_from_file_location("settlement_financial_maintenance", FENCE_TOOL)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    recovery = doc["schema"] == RECOVERY_SCHEMA
    try:
        verifier = module.verify_retained_fence if recovery else module.verify_current_fence
        evidence = verifier(Path(doc["fenceReceiptPath"]), doc["fenceScopeSha256"])
        backup = protected_bytes(Path(doc["backupReceiptPath"]))
        require(hashlib.sha256(backup).hexdigest() == doc["backupReceiptSha256"],
                "isolated restore receipt drift")
        module.verify_current_backup(Path(doc["backupReceiptPath"]),
                                     doc["fenceScopeSha256"], doc["fenceReceiptSha256"])
    except module.MaintenanceError as exc:
        raise Blocked("current producer fence not verified") from exc
    # A scope hash alone is not approval of a different packet/procedure.
    require(isinstance(evidence, dict) and evidence.get("resume_authorized") is False,
            "producer fence returned no nonresuming evidence")
    permit = evidence.get("permit", {})
    require(permit.get("packet_sha256") == doc["packetSha256"] and
            permit.get("procedure_sha256") == doc["procedureSha256"],
            "fence belongs to different evidence/procedure")
    roles = {"owner": "owner", "operator": "operator", "chainReviewer": "chain_reviewer",
             "financeReviewer": "finance_reviewer", "recoveryWitness": "recovery_witness"}
    refs = permit.get("approval_refs", {})
    if recovery:
        # Expired OLD fence authority is NOT renewed. Its persistent gates are
        # observed only; the fresh recovery document separately authorizes the
        # new bounded recovery window and newly referenced human approvals.
        require(evidence.get("admission_authorized") is False and
                refs.get("owner", {}).get("identity") == doc["owner"],
                "retained fence ownership/observation differs")
        return
    require(utc(permit.get("not_before")) <= utc(doc["windowStartUtc"]) and
            utc(doc["windowEndUtc"]) <= utc(permit.get("expires_at")),
            "first rehearsal exceeds original approved fence window")
    require(all(isinstance(refs.get(role), dict) and
                refs[role].get("approval_sha256") == doc["approvalRefs"][key]
                for key, role in roles.items()) and
            all(refs[roles[key]].get("identity") == doc[key]
                for key in ("owner", "operator", "recoveryWitness")),
            "fence human approvals differ from rehearsal authority")


class RehearsalAuthority:
    def __init__(self, path: Path, *, recovery=False, session=None, lost_after=None):
        self.path, self.recovery, self.session, self.lost_after = path, recovery, session, lost_after
        require(not recovery or (session is not None and lost_after is not None),
                "recovery requires an independently observed controller-loss bound")
        self.doc = load_rehearsal_permit(path, recovery=recovery)
        self.binding = ReleaseAuthority._binding(self.doc)

    def refresh(self) -> dict:
        doc = load_rehearsal_permit(self.path, recovery=self.recovery)
        require(ReleaseAuthority._binding(doc) == self.binding, "rehearsal authority changed")
        return doc

    def check(self) -> None:
        doc = self.refresh()
        if self.session is not None:
            old = self.session["permit"]
            require(doc["sessionSha256"] == self.session["_sha256"] and
                    doc["executionId"] == old["executionId"] and
                    all(doc[key] == old[key] for key in ("packetSha256", "procedureSha256",
                        "fenceScopeSha256", "toolSha256", "fenceToolSha256")),
                    "recovery belongs to a different approved rehearsal")
            require(utc(doc["issuedAtUtc"]) > utc(self.session["createdAtUtc"]),
                    "later recovery requires newly issued authority")
            require(self.lost_after is not None and
                    utc(doc["issuedAtUtc"]) >= utc(self.lost_after),
                    "recovery authority predates detected controller loss")
        fence_check(doc)
        self.refresh()  # slow fence/source I/O must not consume expired authority


class Live:
    """All live external operations (mocked in offline CI)."""

    def command(self, *argv: str) -> str:
        # Bound combined command output as well as runtime. Git index/status
        # output is untrusted and must not allocate unbounded capture buffers.
        env = os.environ.copy()
        if argv and Path(argv[0]).name == "git":
            # Inspection is of CHECKOUT, never an inherited alternate index,
            # repository, namespace or command-line configuration overlay.
            for key in tuple(env):
                if key.startswith("GIT_"):
                    del env[key]
        env.update({"GIT_OPTIONAL_LOCKS": "0", "GIT_NO_REPLACE_OBJECTS": "1"})
        process = subprocess.Popen(argv, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, env=env,
                                   start_new_session=True)
        selector = selectors.DefaultSelector()
        output = bytearray()
        total = 0
        deadline = time.monotonic() + 30
        try:
            for stream in (process.stdout, process.stderr):
                selector.register(stream, selectors.EVENT_READ)
            while selector.get_map():
                require(time.monotonic() < deadline, "inspection command timed out")
                for key, _ in selector.select(min(.2, max(0, deadline-time.monotonic()))):
                    data = os.read(key.fileobj.fileno(), 65536)
                    if not data:
                        selector.unregister(key.fileobj)
                        continue
                    total += len(data)
                    require(total <= MAX_COMMAND_BYTES, "inspection output exceeds limit")
                    if key.fileobj is process.stdout:
                        output.extend(data)
            require(process.wait(timeout=max(.001, deadline-time.monotonic())) == 0,
                    "inspection command failed")
            return output.decode("utf-8", errors="strict").strip()
        except subprocess.TimeoutExpired as exc:
            raise Blocked("inspection command timed out") from exc
        finally:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()
            selector.close()
            process.stdout.close()
            process.stderr.close()

    def source_checkout(self) -> dict:
        def git(*args):
            return self.command("git", "--no-optional-locks", "--no-replace-objects",
                                "-c", "core.fsmonitor=false", "-C", CHECKOUT, *args)
        top = git("rev-parse", "--show-toplevel")
        require(Path(top).resolve() == Path(CHECKOUT).resolve(),
                "source checkout top-level differs from reviewed path")
        revision = git("rev-parse", "HEAD")
        require(re.fullmatch(r"[a-f0-9]{40}", revision) is not None,
                "source checkout revision unverifiable")
        index = git("ls-files", "-v").splitlines()
        visible = bool(index) and all(line.startswith("H ") for line in index)
        status = git("status", "--porcelain=v1", "--untracked-files=all",
                     "--ignored=matching")
        lines = status.splitlines()
        return {"revision": revision, "clean": not status and visible,
                "tracked_index_visible": visible,
                "ignored_entries": sum(line.startswith("!!") for line in lines),
                "untracked_entries": sum(line.startswith("??") for line in lines),
                "tracked_change_entries": sum(not line.startswith(("!!", "??")) for line in lines)}

    def systemctl(self, action: str, unit: str | None = None) -> str:
        require(action in {"show", "stop", "start", "daemon-reload"},
                "unreviewed systemd action")
        if action == "daemon-reload":
            require(unit is None, "reload cannot name a service")
            return self.command("systemctl", "daemon-reload")
        require(unit in (*SERVICES, CONSENSUS), "unreviewed service name")
        if action == "show":
            return self.command("systemctl", "show", "-P", "MainPID", unit)
        require(unit in SERVICES, "consensus service mutation is forbidden")
        return self.command("systemctl", action, unit)

    def show(self, unit: str, field: str) -> str:
        require(unit in (*SERVICES, CONSENSUS), "unreviewed service")
        require(field in {"MainPID", "DropInPaths", "FragmentPath", "ActiveState"},
                "unreviewed systemd property")
        return self.command("systemctl", "show", "-P", field, unit)

    def exe(self, pid: int) -> str:
        return os.readlink(f"/proc/{pid}/exe")

    def file_sha(self, path: str) -> str:
        return sha_file(Path(path))

    def check_binary(self, path: str, expected: str) -> None:
        p = Path(path)
        require(p.is_file() and not p.is_symlink()
                and self.file_sha(path) == expected,
                "candidate/original/consensus executable identity drift")

    def dropin(self, service: str) -> Path:
        require(service in SERVICES, "invalid dropin owner")
        return Path("/etc/systemd/system") / f"{service}.d" / OVERRIDE

    def check_unit_fragment(self, service: str) -> None:
        require(service in SERVICES, "unreviewed fragment")
        p = Path("/etc/systemd/system") / service
        require(p.is_file() and not p.is_symlink(), "original service unit is missing")
        info = p.stat()
        require(info.st_uid == 0 and info.st_gid == 0 and
                not (stat.S_IMODE(info.st_mode) & 0o022),
                "original unit must be root-owned and not writable by group/others")
        raw = p.read_text(encoding="utf-8")
        pattern = re.compile(
            r"^ExecStart=/usr/local/bin/wolochaind-mainnet[ \t]+settlement[ \t]+serve[ \t]*$",
            re.MULTILINE,
        )
        require(len(pattern.findall(raw)) == 1,
                "original unit has unreviewed ExecStart")

    def read_dropin(self, service: str) -> str:
        p = self.dropin(service)
        if p.is_symlink():
            raise Blocked("unsafe symlinked override")
        if not p.exists():
            return "old"
        require(p.is_file() and p.read_bytes() == expected_override(),
                "foreign or modified override - manual review")
        return "new"

    def add_dropin(self, service: str) -> None:
        p = self.dropin(service)
        require(not p.exists() and not p.is_symlink(), "override already exists")
        parent = p.parent
        require(not parent.is_symlink(), "override directory symlink")
        if not parent.exists():
            parent.mkdir(mode=0o755)
        require(parent.is_dir() and not parent.is_symlink(),
                "invalid systemd override directory")
        # Exclusive no-follow create, then sync to limit crash window.
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(p, flags, 0o644)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(expected_override())
                stream.flush()
                os.fsync(stream.fileno())
        except BaseException:
            if p.is_file() and not p.is_symlink():
                p.unlink()
            raise

    def remove_dropin(self, service: str) -> None:
        require(self.read_dropin(service) == "new", "refuse to remove foreign override")
        self.dropin(service).unlink()

    def health(self, port: int) -> None:
        require(port in (8092, 8093), "unreviewed health endpoint")
        with urlopen(f"http://127.0.0.1:{port}/settlement/v1/health", timeout=8) as resp:
            data = resp.read(65537)
        require(len(data) <= 65536, "health response too large")
        body = json.loads(data)
        require(body.get("ok") is True and body.get("chain_id") == "wolo-1",
                "settlement lane chain/health mismatch")


class Cutover:
    def __init__(self, live: Live, authorize=None):
        self.live = live
        self.authorize = authorize

    def require_authority(self) -> None:
        require(callable(self.authorize), "fresh bound release authority required")
        self.authorize()

    def pin_node(self) -> int:
        self.live.check_binary(NODE, NODE_SHA)
        pid = self.pid(CONSENSUS)
        require(self.live.exe(pid) == NODE and
                self.live.file_sha(f"/proc/{pid}/exe") == NODE_SHA,
                "consensus running identity changed")
        return pid

    def pid(self, service: str) -> int:
        raw = self.live.show(service, "MainPID")
        require(re.fullmatch(r"[1-9][0-9]*", raw) is not None,
                f"{service} has no active PID")
        return int(raw)

    def running(self, unit: str, exe: str, sha: str) -> None:
        require(self.live.show(unit, "ActiveState") == "active",
                f"{unit} inactive")
        pid = self.pid(unit)
        require(self.live.exe(pid) == exe and
                self.live.file_sha(f"/proc/{pid}/exe") == sha,
                f"{unit} running wrong executable")

    def state(self, *, allow_partial: bool = False) -> str:
        self.live.check_binary(OLD, OLD_SHA)
        self.live.check_binary(NEW, NEW_SHA)
        self.pin_node()
        modes = []
        for unit in SERVICES:
            require(self.live.show(unit, "FragmentPath") ==
                    f"/etc/systemd/system/{unit}",
                    "original unit is not the pinned systemd fragment")
            self.live.check_unit_fragment(unit)
            mode = self.live.read_dropin(unit)
            actual = self.live.show(unit, "DropInPaths")
            expected = str(self.live.dropin(unit)) if mode == "new" else ""
            if allow_partial:
                # Crash before daemon-reload can leave systemd's cached
                # DropInPaths one step behind exact on-disk owned overrides.
                require(actual in ("", str(self.live.dropin(unit))),
                        "foreign systemd drop-in while recovering")
            else:
                require(actual == expected,
                        "unexpected foreign/unsynchronized systemd override")
            modes.append(mode)
        if modes[0] != modes[1]:
            require(allow_partial, "mixed service code generations; recovery only")
            return "partial"
        return modes[0]

    def wait_settlement_health(self, port: int, pinned_pid: int) -> None:
        """Wait for a starting HTTP listener, never for wrong-chain or malformed health.

        A process may be systemd-active before it has bound its localhost port.
        Only temporary network transport faults receive a short retry window.
        Semantic health mismatches, HTTP responses indicating failure, and
        any change to the dedicated consensus process fail immediately.
        """
        deadline = time.monotonic() + STARTUP_HEALTH_GRACE_SECONDS
        while True:
            require(self.pin_node() == pinned_pid,
                    "consensus changed during settlement startup wait")
            try:
                self.live.health(port)
                return
            except HTTPError:
                raise
            except (URLError, ConnectionRefusedError, ConnectionResetError,
                    TimeoutError) as exc:
                if isinstance(exc, URLError) and not isinstance(
                    exc.reason, (ConnectionRefusedError, ConnectionResetError,
                                 TimeoutError)
                ):
                    raise
                if time.monotonic() >= deadline:
                    raise Blocked(
                        f"settlement localhost port {port} did not become "
                        "ready before the bounded health deadline"
                    ) from exc
                time.sleep(min(STARTUP_HEALTH_POLL_SECONDS,
                               max(0.0, deadline - time.monotonic())))

    def assert_services(self, generation: str, pinned_pid: int) -> None:
        program, sha = (OLD, OLD_SHA) if generation == "old" else (NEW, NEW_SHA)
        for unit in SERVICES:
            self.running(unit, program, sha)
        require(self.pin_node() == pinned_pid,
                "consensus PID changed during settlement operation")
        for port in (8092, 8093):
            self.wait_settlement_health(port, pinned_pid)
        # A lane might exit while the other is becoming ready: recheck both
        # executable identities and health at the end of the bounded wait.
        for unit in SERVICES:
            self.running(unit, program, sha)
        require(self.pin_node() == pinned_pid,
                "consensus changed after settlement startup")
        for port in (8092, 8093):
            self.wait_settlement_health(port, pinned_pid)

    def inspect(self) -> str:
        generation = self.state()
        pinned = self.pin_node()
        self.assert_services(generation, pinned)
        return generation

    def source_authority(self) -> dict:
        # A checkout update alone cannot turn the old executable into the new
        # implementation. Require exact two-lane runtime proof independently.
        before = self.live.source_checkout()
        node = self.pin_node()
        settlement_pids = {unit: self.pid(unit) for unit in SERVICES}
        generation = self.inspect()
        after = self.live.source_checkout()
        require(before == after, "source changed during authority inspection")
        # The second Git observation may take time. Recheck exact generations,
        # process identities and health afterwards; a rollback/exit/restart
        # during those reads must never retain the earlier green generation.
        require(self.state() == generation, "settlement generation changed during authority inspection")
        self.assert_services(generation, node)
        require(self.state() == generation, "settlement generation changed after final health")
        program, digest = (OLD, OLD_SHA) if generation == "old" else (NEW, NEW_SHA)
        for unit in SERVICES:
            self.running(unit, program, digest)
            require(self.pid(unit) == settlement_pids[unit],
                    "settlement PID changed during authority inspection")
        require(self.pin_node() == node, "consensus changed during authority inspection")
        require(type(after.get("clean")) is bool and
                type(after.get("tracked_index_visible")) is bool and
                re.fullmatch(r"[a-f0-9]{40}", after.get("revision", "")) is not None,
                "source checkout observation unverifiable")
        code_required = generation != "new"
        source_required = after["revision"] != REV
        visible = after["tracked_index_visible"]
        known_source = after["revision"] in (OLD_REV, REV)
        aligned = not code_required and not source_required and after["clean"] and visible
        blockers = []
        if not after["clean"] or not visible:
            blockers.append("SOURCE_TREE_OR_INDEX_NOT_CLEAN")
        if not known_source:
            blockers.append("SOURCE_REVISION_NOT_APPROVED")
        if code_required:
            blockers.append("PROTECTED_TWO_SERVICE_CODE_CUTOVER_REQUIRED")
        if source_required:
            blockers.append("SOURCE_TRANSITION_REQUIRED_AFTER_VERIFIED_CODE_CUTOVER")
        return {"schema": "aoe2war.wolo.settlement-source-authority.v1",
                "mode": "READ_ONLY",
                "observed_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "settlement_pids": settlement_pids, "consensus_pid": node,
                "status": "SOURCE_RUNTIME_ALIGNED_FINANCIAL_HOLD" if aligned else "BLOCKED",
                "expected_revision": REV, "checkout_revision": after["revision"],
                "checkout_clean": after["clean"],
                "tracked_index_visible": after["tracked_index_visible"],
                "ignored_entries": after.get("ignored_entries"),
                "untracked_entries": after.get("untracked_entries"),
                "tracked_change_entries": after.get("tracked_change_entries"),
                "live_code_state": generation,
                "live_settlement_revision": REV if generation == "new" else OLD_REV,
                "live_settlement_sha256": NEW_SHA if generation == "new" else OLD_SHA,
                "code_cutover_required": code_required,
                "source_transition_required": source_required,
                "source_transition_runtime_prerequisite_met": not code_required and after["clean"] and visible and known_source,
                "source_runtime_aligned": aligned,
                "consensus_unchanged": True,
                "blockers": blockers, "release_authorized": False,
                "financial_drain_certified": False, "custody_authorized": False,
                "claim_889_resolved": False, "production_mutated": False}

    def code_only_recover(self, pinned_pid: int) -> None:
        # A newly requested rollback/recovery needs fresh original authority
        # after its slow preflight and immediately before its first mutation.
        require(self.pin_node() == pinned_pid, "consensus changed before recovery")
        self.require_authority()
        self._complete_code_recovery(pinned_pid)

    def _complete_code_recovery(self, pinned_pid: int) -> None:
        # Cleanup continuation is authorized only by an already-started,
        # freshly approved mutation. Expiry/revocation stops forward rollout,
        # but must not strand half-switched lanes: complete only this fixed
        # at-most-seven-step OLD-code recovery (two stops, <=two owned override
        # removals, one reload, two starts). No new rollout, permit renewal,
        # producer resume, consensus mutation or financial-state restore.
        # A later process must obtain fresh authority to request recovery.

        for unit in SERVICES:
            self.live.systemctl("stop", unit)
        for unit in SERVICES:
            if self.live.read_dropin(unit) == "new":
                self.live.remove_dropin(unit)
        self.live.systemctl("daemon-reload")
        for unit in SERVICES:
            self.live.systemctl("start", unit)
        require(self.state() == "old", "recovery did not restore original unit code")
        self.assert_services("old", pinned_pid)

    def promote(self) -> str:
        require(self.state() == "old", "promotion requires both original lanes")
        pinned = self.pin_node()
        self.assert_services("old", pinned)
        started = False
        def forward(call, *args):
            nonlocal started
            # Slow I/O must not spend an authorization window checked earlier.
            # Mark cleanup eligibility only after this fresh check succeeds,
            # immediately before invoking a possibly uncertain side effect.
            self.require_authority()
            started = True
            call(*args)
        try:
            for unit in SERVICES:
                forward(self.live.systemctl, "stop", unit)
            for unit in SERVICES:
                forward(self.live.add_dropin, unit)
            forward(self.live.systemctl, "daemon-reload")
            for unit in SERVICES:
                forward(self.live.systemctl, "start", unit)
            require(self.state() == "new", "two-lane promotion not complete")
            self.assert_services("new", pinned)
            self.require_authority()
            return "new"
        except BaseException:
            if started:
                try:
                    self._complete_code_recovery(pinned)
                except BaseException as recovery:
                    raise Blocked(
                        "CRITICAL: automatic code-only recovery failed; payment "
                        "producers MUST stay fenced and human must inspect"
                    ) from recovery
            raise


def process_identity(pid: int) -> dict | None:
    """Linux boot + PID/start ticks: never mistake a reused PID for our process."""
    require(type(pid) is int and pid > 0, "invalid controller process identity")
    try:
        fd = os.open(f"/proc/{pid}/stat", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            raw = os.read(fd, 8193).decode("ascii")
        finally:
            os.close(fd)
        require(len(raw) <= 8192 and raw.startswith(f"{pid} ("), "invalid process identity data")
        fields = raw.rsplit(")", 1)[1].split()
        require(len(fields) >= 20 and fields[19].isdecimal(), "missing process start ticks")
        if fields[0] in ("Z", "X"):
            return None
        boot = Path("/proc/sys/kernel/random/boot_id").read_text().strip()
        require(re.fullmatch(r"[a-f0-9-]{36}", boot), "invalid kernel boot identity")
        return {"pid": pid, "startTicks": fields[19], "bootId": boot}
    except (FileNotFoundError, ProcessLookupError):
        return None


def unit_status(live, unit: str) -> dict:
    require(re.fullmatch(r"aoe2war-wolo-first-rehearsal-[a-f0-9]{32}\.service", unit),
            "unreviewed rehearsal supervisor unit")
    fields = ("ActiveState", "MainPID", "InvocationID", "Restart", "Type", "Transient", "KillMode")
    raw = live.command("systemctl", "show", unit, "--no-pager",
                       *("--property=" + field for field in fields))
    return dict(line.split("=", 1) for line in raw.splitlines() if "=" in line)


def supervisor_identity(live, unit: str) -> dict:
    status = unit_status(live, unit)
    require(status.get("ActiveState") == "active" and status.get("Restart") == "on-failure" and
            status.get("Type") == "exec" and status.get("Transient") == "yes" and
            status.get("KillMode") == "control-group" and
            re.fullmatch(r"[a-f0-9]{32}", status.get("InvocationID", "")) and
            status.get("MainPID", "").isdecimal(), "independent systemd supervision not verified")
    identity = process_identity(int(status["MainPID"]))
    require(identity is not None, "supervisor process absent")
    return {**identity, "invocationId": status["InvocationID"]}


def load_session(path: Path) -> dict:
    raw = protected_bytes(path)
    try:
        doc = json.loads(raw, object_pairs_hook=_unique_permit_object)
    except (ValueError, RecursionError, UnicodeError) as exc:
        raise Blocked("invalid rehearsal session") from exc
    require(isinstance(doc, dict) and set(doc) == {"schema", "permit", "permitPath",
            "controllerIdentity", "consensusPid", "createdAtUtc", "watchdogUnit"} and
            doc["schema"] == "aoe2war.wolochain.rehearsal-session.v1",
            "rehearsal session shape differs")
    validate_rehearsal_permit(doc["permit"], now=utc(doc["createdAtUtc"]))
    execution = doc["permit"]["executionId"]
    require(path == REHEARSAL_ROOT / execution / "session.json" and
            doc["watchdogUnit"] == f"aoe2war-wolo-first-rehearsal-{execution}.service" and
            type(doc["consensusPid"]) is int and doc["consensusPid"] > 0 and
            isinstance(doc["controllerIdentity"], dict) and
            set(doc["controllerIdentity"]) == {"pid", "startTicks", "bootId"},
            "rehearsal session identity/path differs")
    identity = doc["controllerIdentity"]
    require(type(identity["pid"]) is int and identity["pid"] > 0 and
            isinstance(identity["startTicks"], str) and identity["startTicks"].isdecimal() and
            isinstance(identity["bootId"], str) and re.fullmatch(r"[a-f0-9-]{36}", identity["bootId"]),
            "rehearsal session process binding invalid")
    doc["_sha256"] = hashlib.sha256(raw).hexdigest()
    return doc


def check_watchdog(live, path: Path, session: dict) -> None:
    ready = private_json(path.parent / "watchdog-ready.json")
    require(set(ready) == {"sessionSha256", "identity"} and
            ready["sessionSha256"] == session["_sha256"] and
            ready["identity"] == supervisor_identity(live, session["watchdogUnit"]),
            "watchdog absent, restarted or identity changed")


def start_watchdog(live, path: Path, session: dict) -> None:
    # systemd is the parent/supervisor, not the invoking SSH/controller session.
    live.command("systemd-run", "--unit=" + session["watchdogUnit"],
                 "--property=Type=exec", "--property=Restart=on-failure", "--property=RestartSec=1s",
                 "--property=KillMode=control-group", "--property=User=root", "--property=UMask=0077",
                 "/usr/bin/python3", str(Path(__file__).resolve()),
                 "--mode", "rehearsal-watchdog", "--session", str(path))
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        try:
            check_watchdog(live, path, session)
            return
        except (Blocked, OSError):
            time.sleep(.1)
    raise Blocked("independent watchdog readiness deadline exceeded; zero rehearsal mutations allowed")


def completion(path: Path, session: dict, *, round_trip=False, recovered=False) -> dict:
    result = {"schema": "aoe2war.wolochain.rehearsal-result.v1",
              "sessionSha256": session["_sha256"], "originalCodeRestored": True,
              "codeRoundTripObserved": round_trip, "freshRecoveryObserved": recovered,
              "production_authorized": False, "financial_resume_authorized": False,
              "canonical_control_updated": False, "independent_witness_attested": False}
    record_once(path.parent / "completed.json", result)
    return result


def first_rehearsal(authority: RehearsalAuthority, live) -> dict:
    authority.check()
    ctl = Cutover(live)
    pinned = ctl.pin_node()
    require(ctl.inspect() == "old", "first rehearsal requires both original lanes")
    identity = process_identity(os.getpid())
    require(identity is not None, "controller identity unavailable")
    REHEARSAL_ROOT.mkdir(mode=0o700, exist_ok=True)
    info = REHEARSAL_ROOT.lstat()
    require(stat.S_ISDIR(info.st_mode) and info.st_uid == 0 and info.st_gid == 0 and
            stat.S_IMODE(info.st_mode) == 0o700, "unsafe rehearsal record root")
    sync_directory(REHEARSAL_ROOT.parent)  # make a newly created journal root durable
    directory = REHEARSAL_ROOT / authority.doc["executionId"]
    directory.mkdir(mode=0o700)  # no duplicate/replayed execution identity
    sync_directory(REHEARSAL_ROOT)  # persist execution directory before its session
    path = directory / "session.json"
    record_once(path, {"schema": "aoe2war.wolochain.rehearsal-session.v1",
        "permit": authority.doc, "permitPath": str(authority.path),
        "controllerIdentity": identity, "consensusPid": pinned,
        "createdAtUtc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "watchdogUnit": f"aoe2war-wolo-first-rehearsal-{authority.doc['executionId']}.service"})
    session = load_session(path)
    start_watchdog(live, path, session)
    def guarded():
        authority.check()
        check_watchdog(live, path, session)
        authority.refresh()
    ctl.authorize = guarded
    # promote owns its own bounded OLD cleanup if forward rollout fails.
    try:
        ctl.promote()
    except BaseException:
        # Record only independently re-observed OLD code after caught abort;
        # no rehearsal/finance attestation follows from an aborted rollout.
        try:
            require(ctl.pin_node() == pinned and ctl.inspect() == "old", "abort not recovered")
            completion(path, session)
        except BaseException:
            pass  # the independently supervised loss/recovery path stays armed
        raise
    # Mandatory return is part of the SAME started round-trip authority. Even
    # expiry/revocation cannot authorize leaving candidate code installed.
    # Exactly one bounded OLD cleanup; failure is CRITICAL, never auto-retried.
    try:
        require(ctl.pin_node() == pinned, "consensus changed before mandatory return")
        ctl._complete_code_recovery(pinned)
    except BaseException as exc:
        raise Blocked("CRITICAL: first rehearsal return failed; fence retained, fresh recovery required") from exc
    try:
        guarded()
    except BaseException:
        completion(path, session)  # OLD returned, but rehearsal not certified
        raise
    return completion(path, session, round_trip=True)


def controller_loss(path: Path, session: dict) -> dict:
    """Immutable actual loss observation shared by manual and watchdog recovery."""
    require(process_identity(session["controllerIdentity"]["pid"]) != session["controllerIdentity"],
            "original controller still alive; recovery denied")
    loss_path = path.parent / "controller-lost.json"
    if not loss_path.exists():
        try:
            record_once(loss_path, {"sessionSha256": session["_sha256"],
                "observedAtUtc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "status": "CONTROLLER_LOST_FRESH_RECOVERY_REQUIRED"})
        except FileExistsError:
            pass  # the other observer won; validate the immutable record below
    loss = private_json(loss_path)
    require(set(loss) == {"sessionSha256", "observedAtUtc", "status"} and
            loss["sessionSha256"] == session["_sha256"] and
            loss["status"] == "CONTROLLER_LOST_FRESH_RECOVERY_REQUIRED" and
            utc(session["createdAtUtc"]) <= utc(loss["observedAtUtc"]) <= datetime.now(timezone.utc),
            "controller loss identity/time binding differs")
    return loss


def recover_rehearsal(path: Path, permit: Path, live) -> dict:
    session = load_session(path)
    own = process_identity(os.getpid())
    require(own is not None and own["bootId"] == session["controllerIdentity"]["bootId"],
            "host boot identity changed; fresh incident procedure required")
    loss = controller_loss(path, session)
    authority = RehearsalAuthority(permit, recovery=True, session=session,
                                  lost_after=loss["observedAtUtc"])
    authority.check()
    attempt = hashlib.sha256(authority.binding.encode()).hexdigest()
    record_once(path.parent / f"recovery-attempt-{attempt}.json", {
        "sessionSha256": session["_sha256"], "authoritySha256": attempt,
        "status": "ATTEMPT_CONSUMED_FRESH_AUTHORITY_REQUIRED_FOR_ANY_RETRY"})
    ctl = Cutover(live, authorize=authority.check)
    require(ctl.pin_node() == session["consensusPid"], "consensus changed since rehearsal")
    # Inspect owned partial overrides/inactive lanes. Never overwrite foreign code.
    generation = ctl.state(allow_partial=True)
    inactive = any(live.show(unit, "ActiveState") != "active" for unit in SERVICES)
    if generation != "old" or inactive:
        ctl.code_only_recover(session["consensusPid"])
    require(ctl.inspect() == "old", "fresh recovery did not restore both original lanes")
    authority.refresh()
    return completion(path, session, recovered=True)


def watchdog_step(path: Path, session: dict, live) -> str:
    """Never mutate on controller loss alone. Recovery is separately authorized."""
    done = path.parent / "completed.json"
    if done.exists():
        result = private_json(done)
        require(result.get("sessionSha256") == session["_sha256"] and
                result.get("originalCodeRestored") is True and
                result.get("production_authorized") is False,
                "completion marker does not bind this nonauthorizing rehearsal")
        ctl = Cutover(live)
        require(ctl.pin_node() == session["consensusPid"] and ctl.inspect() == "old",
                "completion marker differs from actual paired OLD runtime")
        return "COMPLETE_OLD_CODE_NO_RESUME_AUTHORITY"
    if process_identity(session["controllerIdentity"]["pid"]) == session["controllerIdentity"]:
        try:
            fence_check(session["permit"])
            return "MONITORING_BOUND_CONTROLLER"
        except (Blocked, OSError, ValueError):
            return "HOLD_PRODUCER_FENCE_UNVERIFIED_NO_RESUME"
    controller_loss(path, session)
    permit = path.parent / "recovery-permit.json"
    if not permit.exists():
        return "HOLD_AWAITING_FRESH_HUMAN_RECOVERY_AUTHORITY"
    try:
        with acquire_mutation_lock():
            recover_rehearsal(path, permit, live)
        return "COMPLETE_OLD_CODE_NO_RESUME_AUTHORITY"
    except (Blocked, OSError, ValueError, subprocess.SubprocessError):
        # No old permit adoption, repeated financial broadcast or producer resume.
        return "HOLD_RECOVERY_REFUSED_OR_FAILED_HUMAN_INSPECTION_REQUIRED"


def run_watchdog(path: Path, live) -> None:
    session = load_session(path)
    own = supervisor_identity(live, session["watchdogUnit"])
    require(own["pid"] == os.getpid() and
            own["bootId"] == session["controllerIdentity"]["bootId"],
            "watchdog must run as its exact independent systemd MainPID")
    check_rehearsal_sources(session["permit"])
    ready = path.parent / "watchdog-ready.json"
    if not ready.exists():
        record_once(ready, {"sessionSha256": session["_sha256"],
                           "identity": supervisor_identity(live, session["watchdogUnit"])})
    previous = None
    while True:
        state = watchdog_step(path, session, live)
        if state != previous:
            print(state, flush=True)  # fixed statuses, no private records or identities
            previous = state
        if state == "COMPLETE_OLD_CODE_NO_RESUME_AUTHORITY":
            return
        time.sleep(1)


def acquire_mutation_lock():
    """Serialize exact financial code switches, never create file for inspect."""
    import contextlib
    import errno
    @contextlib.contextmanager
    def locked():
        root = Path("/run/lock")
        require(root.is_dir() and not root.is_symlink(), "lock directory invalid")
        dest = root / "aoe2war-wolo-two-settlement-code-only.lock"
        fd = os.open(dest, os.O_RDWR | os.O_CREAT |
                     getattr(os, "O_NOFOLLOW", 0), 0o600)
        try:
            mode = os.fstat(fd)
            require(stat.S_ISREG(mode.st_mode) and mode.st_uid == 0 and
                    stat.S_IMODE(mode.st_mode) == 0o600,
                    "shared financial operator lock is unsafe")
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise Blocked("another code switch has financial operator lock") from exc
            yield
        finally:
            os.close(fd)
    return locked()


def run_mode(args, controller: Cutover) -> None:
    if args.mode == "inspect":
        print("LIVE_CODE_STATE=" + controller.inspect())
        print("FINANCIAL_DRAIN_CERTIFIED=false")
        print("RELEASE_AUTHORIZED=false")
    elif args.mode == "source-authority":
        receipt = controller.source_authority()
        print(json.dumps(receipt, sort_keys=True))
        if not receipt["source_runtime_aligned"]:
            raise Blocked("source/runtime authority remains mismatched; no checkout-only bypass")
    elif args.mode == "promote":
        print("NEW_CODE_STATE=" + controller.promote())
        print("PAYOUT_PRODUCERS_STILL_FENCED_REQUIRED=true")
    elif args.mode == "rollback":
        require(controller.state() == "new",
                "rollback requires both exact reviewed candidate services")
        pinned = controller.pin_node()
        controller.code_only_recover(pinned)
        print("RESTORED_ORIGINAL_CODE=true")
        print("PAYOUT_PRODUCERS_STILL_FENCED_REQUIRED=true")
    else:
        mode = controller.state(allow_partial=True)
        has_inactive = any(
            controller.live.show(u, "ActiveState") != "active" for u in SERVICES
        )
        require(mode == "partial" or has_inactive,
                "interrupted recovery requires a partial or inactive lane")
        controller.code_only_recover(controller.pin_node())
        print("RECOVERED_INTERRUPTED_CODE_SWITCH=true")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", default="inspect",
                        choices=["inspect", "source-authority", "promote", "rollback", "recover-interrupted",
                                 "first-rehearsal", "rehearsal-recover", "rehearsal-watchdog"])
    parser.add_argument("--permit", help="absolute root-owned finance approval JSON")
    parser.add_argument("--session", help="exact root-private first-rehearsal session record")
    args = parser.parse_args()
    try:
        require(os.geteuid() == 0, "root needed to inspect/operate exact systemd units")
        if args.mode in {"first-rehearsal", "rehearsal-recover", "rehearsal-watchdog"}:
            if args.mode == "rehearsal-watchdog":
                require(args.session and not args.permit, "supervisor requires only a bound session")
                run_watchdog(Path(args.session), Live())
            elif args.mode == "first-rehearsal":
                require(args.permit and not args.session, "first rehearsal requires its distinct permit")
                authority = RehearsalAuthority(Path(args.permit))
                with acquire_mutation_lock():
                    print(json.dumps(first_rehearsal(authority, Live()), sort_keys=True))
            else:
                require(args.permit and args.session, "later recovery requires fresh permit and session")
                with acquire_mutation_lock():
                    print(json.dumps(recover_rehearsal(Path(args.session), Path(args.permit), Live()), sort_keys=True))
            return 0
        require(not args.session, "production/read-only modes cannot adopt rehearsal sessions")
        authority = None
        if args.mode not in READ_ONLY_MODES:
            require(bool(args.permit), "mutations require explicit finance permit")
            authority = ReleaseAuthority(Path(args.permit))
        elif args.permit:
            raise Blocked("read-only mode must not be presented as financial authorization")
        controller = Cutover(Live(), authorize=authority.check if authority else None)
        if args.mode in READ_ONLY_MODES:
            run_mode(args, controller)
        else:
            with acquire_mutation_lock():
                run_mode(args, controller)
        return 0
    except (Blocked, OSError, ValueError, subprocess.SubprocessError) as exc:
        print("BLOCKED: " + str(exc), file=sys.stderr)
        print("NO_PAYOUT_PRODUCER_RESUME=true", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Exact-version, two-settlement SERVICE-CODE switch / recovery. No bank-state restore.

Root-only, explicit short-lived external finance permit required before mutation.
Default --inspect is nonmutating. NEVER touches Wolo consensus or resumes HD/DE
signers. A permit is a human-approved release artifact, NOT proof that its claims
are true. It must only be issued after separately witnessed financial controls.

The only mutable live paths are two dedicated systemd override files. The
original executable is never overwritten; original request/run state is never
copied, truncated, changed or rewound. A partial application is fail-closed and
offers code-only recovery after the same verified maintenance authority.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import fcntl
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


def load_release_permit(path: Path, *, now: datetime | None = None) -> dict:
    """Operator-issued receipt; NEVER inferred from CI/test booleans."""
    now = now or datetime.now(timezone.utc)
    require(path.is_absolute() and path.is_file() and not path.is_symlink(),
            "release permit must be regular absolute file, not symlink")
    meta = path.stat()
    require(meta.st_uid == 0 and meta.st_gid == 0 and
            stat.S_IMODE(meta.st_mode) == 0o600 and meta.st_size < 8192,
            "release permit requires root:root mode 0600 and size below 8KiB")
    try:
        permit = json.loads(path.read_bytes())
    except (ValueError, OSError) as exc:
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
    require(now - timedelta(minutes=5) <= created <= now and
            now < expiry <= created + timedelta(minutes=10),
            "expired, future, or overlong release permit")
    return permit


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
    def __init__(self, live: Live):
        self.live = live

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
        # Requires human operator's still-valid external finance permit.
        # Never rewinds request/run trees and never resumes app payment producers.
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
        try:
            started = True
            for unit in SERVICES:
                self.live.systemctl("stop", unit)
            for unit in SERVICES:
                self.live.add_dropin(unit)
            self.live.systemctl("daemon-reload")
            for unit in SERVICES:
                self.live.systemctl("start", unit)
            require(self.state() == "new", "two-lane promotion not complete")
            self.assert_services("new", pinned)
            return "new"
        except BaseException:
            if started:
                try:
                    self.code_only_recover(pinned)
                except BaseException as recovery:
                    raise Blocked(
                        "CRITICAL: automatic code-only recovery failed; payment "
                        "producers MUST stay fenced and human must inspect"
                    ) from recovery
            raise


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
                        choices=["inspect", "source-authority", "promote", "rollback", "recover-interrupted"])
    parser.add_argument("--permit", help="absolute root-owned finance approval JSON")
    args = parser.parse_args()
    try:
        require(os.geteuid() == 0, "root needed to inspect/operate exact systemd units")
        if args.mode not in READ_ONLY_MODES:
            require(bool(args.permit), "mutations require explicit finance permit")
            load_release_permit(Path(args.permit))
        elif args.permit:
            raise Blocked("read-only mode must not be presented as financial authorization")
        controller = Cutover(Live())
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

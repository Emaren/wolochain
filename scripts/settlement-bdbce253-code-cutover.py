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
import stat
import subprocess
import sys
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
PRIMARY = "wolochain-mainnet-settlement.service"
FOUNDER = "wolochain-founder-rewards-settlement.service"
CONSENSUS = "wolochaind-mainnet.service"
SERVICES = (PRIMARY, FOUNDER)
OVERRIDE = "50-aoe2war-bdbce253-settlement-only.conf"
EXACT_APPROVAL = "I approve an isolated two-settlement code-only cutover; payouts remain fenced"
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
        result = subprocess.run(argv, check=True, timeout=30,
                                capture_output=True, text=True)
        return result.stdout.strip()

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

    def assert_services(self, generation: str, pinned_pid: int) -> None:
        program, sha = (OLD, OLD_SHA) if generation == "old" else (NEW, NEW_SHA)
        for unit in SERVICES:
            self.running(unit, program, sha)
        require(self.pin_node() == pinned_pid,
                "consensus PID changed during settlement operation")
        self.live.health(8092)
        self.live.health(8093)

    def inspect(self) -> str:
        generation = self.state()
        pinned = self.pin_node()
        self.assert_services(generation, pinned)
        return generation

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
                        choices=["inspect", "promote", "rollback", "recover-interrupted"])
    parser.add_argument("--permit", help="absolute root-owned finance approval JSON")
    args = parser.parse_args()
    try:
        require(os.geteuid() == 0, "root needed to inspect/operate exact systemd units")
        if args.mode != "inspect":
            require(bool(args.permit), "mutations require explicit finance permit")
            load_release_permit(Path(args.permit))
        elif args.permit:
            raise Blocked("inspect must not be presented as financial authorization")
        controller = Cutover(Live())
        if args.mode == "inspect":
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

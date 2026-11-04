#!/usr/bin/env python3
"""Durable nonce reservation primitive for a future independently enrolled controller.

No CLI, permit issuance or production side effects. A recorded nonce can never
authorize an operation. Local disk integrity and atomicity cannot prove resistance
to rollback by a root operator: independent witness anchoring is still required.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat

NONCE = re.compile(r"[0-9a-f]{32}\Z")
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
PHASES = {"live_capture", "offline_verify", "resume", "resume_existing", "contain_partial"}
SCHEMA = "wolo.financial-maintenance-nonce-record.v1"
RECORD_KEYS = {"schema", "nonce", "signed_packet_sha256", "phase"}
RECORD_NAME = re.compile(r"nonce-[0-9a-f]{64}\.json\Z")


class ReservationRefused(ValueError):
    pass


def require(ok, reason):
    if not ok:
        raise ReservationRefused(reason)


def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=True).encode("ascii")


def _open_private_dir(path):
    path = Path(path)
    require(path.is_absolute(), "ABSOLUTE_NONCE_ROOT_REQUIRED")
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    st = os.fstat(fd)
    try:
        require(stat.S_ISDIR(st.st_mode) and st.st_uid == os.geteuid() and
                stat.S_IMODE(st.st_mode) == 0o700,
                "NONCE_DIRECTORY_OWNERSHIP_UNSAFE")
        # Reject a renamed/repointed path; continue using the open directory FD.
        current = path.lstat()
        require((st.st_dev, st.st_ino) == (current.st_dev, current.st_ino),
                "NONCE_DIRECTORY_PATH_CHANGED")
        return fd
    except BaseException:
        os.close(fd)
        raise


def _read_exact(dirfd, name):
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=dirfd)
    try:
        before = os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and before.st_uid == os.geteuid()
                and stat.S_IMODE(before.st_mode) == 0o600 and
                before.st_nlink == 1 and 0 < before.st_size <= 1024,
                "NONCE_RECORD_INTEGRITY_INVALID")
        data = os.read(fd, 1025)
        after = os.fstat(fd)
        require(len(data) == before.st_size and
                (before.st_ino, before.st_dev, before.st_mtime_ns, before.st_ctime_ns) ==
                (after.st_ino, after.st_dev, after.st_mtime_ns, after.st_ctime_ns),
                "NONCE_RECORD_CHANGED")
        return data
    finally:
        os.close(fd)


def _read_record(dirfd,name):
    raw = _read_exact(dirfd,name)
    try:
        value = json.loads(raw)
    except (ValueError, UnicodeError):
        raise ReservationRefused("NONCE_RECORD_CORRUPT") from None
    require(type(value) is dict and set(value) == RECORD_KEYS
            and value["schema"] == SCHEMA and canonical(value) == raw
            and type(value["nonce"]) is str and NONCE.fullmatch(value["nonce"])
            and type(value["signed_packet_sha256"]) is str
            and SHA256.fullmatch(value["signed_packet_sha256"])
            and type(value["phase"]) is str and value["phase"] in PHASES
            and name == "nonce-" + hashlib.sha256(value["nonce"].encode()).hexdigest() + ".json",
            "NONCE_RECORD_CORRUPT")
    return value


def reserve_once(root, nonce, signed_packet_sha256, phase):
    """Atomically record once, under a private directory lock, fail closed.

    A crash after O_EXCL still consumes the nonce; partial records block further
    reservations and must be manually investigated, never overwritten.
    This receipt does not attest enrollment, signing rights or production GO.
    """
    require(type(nonce) is str and NONCE.fullmatch(nonce) and nonce != "0"*32,
            "NONCE_INVALID")
    require(type(signed_packet_sha256) is str and SHA256.fullmatch(signed_packet_sha256),
            "PACKET_DIGEST_INVALID")
    require(type(phase) is str and phase in PHASES, "PHASE_INVALID")
    dirfd = _open_private_dir(root)
    try:
        try:
            lockfd = os.open(".nonce.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW,
                             0o600, dir_fd=dirfd)
        except OSError as exc:
            # Some filesystems can refuse one concurrent O_CREAT/openat. Never
            # retry admission or infer that a missing ACK means an unused nonce.
            raise ReservationRefused("NONCE_LOCK_STORAGE_UNAVAILABLE") from exc
        try:
            st = os.fstat(lockfd)
            require(stat.S_ISREG(st.st_mode) and st.st_uid == os.geteuid() and
                    stat.S_IMODE(st.st_mode) == 0o600 and st.st_nlink == 1,
                    "NONCE_LOCK_UNTRUSTED")
            fcntl.flock(lockfd, fcntl.LOCK_EX)
            for name in os.listdir(dirfd):
                if name == ".nonce.lock":
                    continue
                require(RECORD_NAME.fullmatch(name), "FOREIGN_NONCE_DIRECTORY_ENTRY")
                _read_record(dirfd, name)  # Corruption anywhere blocks admission.
            name = "nonce-" + hashlib.sha256(nonce.encode()).hexdigest() + ".json"
            require(name not in os.listdir(dirfd), "NONCE_ALREADY_RESERVED")
            record = {"schema": SCHEMA, "nonce": nonce,
                      "signed_packet_sha256": signed_packet_sha256, "phase": phase}
            fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                         0o600, dir_fd=dirfd)
            with os.fdopen(fd, "wb") as output:
                output.write(canonical(record))
                output.flush()
                os.fsync(output.fileno())
            os.fsync(dirfd)
            require(_read_record(dirfd, name) == record,
                    "NONCE_RESERVATION_VERIFY_FAILED")
            return {"record_sha256":hashlib.sha256(canonical(record)).hexdigest(),
                    "nonce_reserved": True, "human_enrollment_proven": False,
                    "production_operation_authorized": False,
                    "independent_rollback_witness_verified": False}
        finally:
            os.close(lockfd)
    finally:
        os.close(dirfd)

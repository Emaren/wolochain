"""C06 offline checkpoint building blocks. NO production adapter or signing path.

This module does not authenticate authority receipts, fence any service, or
certify a financial gate. It processes a disposable, already-frozen fixture
only. A separately reviewed native adapter must supply and authenticate the
observations and exclusively own the maintenance lease and restart actions.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import tarfile
import tempfile
import threading
import time

ROOTS = frozenset({"pgdata", "pgconfig", "chain-data", "primary-journal",
                   "founder-journal", "nonce-state"})
DOMAINS = frozenset({"website_hd", "website_de", "rollback_runtime",
                     "emergency_runtime", "database_clients", "external_ingress",
                     "systemd_and_cron", "manual_and_deployment",
                     "chain_and_signers", "auxiliary_writers"})
QUARANTINE = frozenset({"bet-stake-timer", "bet-stake-service",
                       "staking-timer", "staking-service",
                       "primary-settlement", "founder-settlement"})
HEX = re.compile(r"[0-9a-f]{64}\Z")
GIB = 1 << 30
BLOCK = 512
MAX_ENTRIES = 1_000_000
MAX_MANIFEST = 64 << 20


class Hold(ValueError):
    pass


def require(ok, reason):
    if not ok:
        raise Hold(reason)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(value).hexdigest()


def sha_file(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        while block := f.read(1 << 20):
            h.update(block)
    return h.hexdigest()


def hash64(value):
    return isinstance(value, str) and HEX.fullmatch(value) is not None


def validate_observation(observed, *, expected_databases):
    """Structural consistency only; no authenticity is asserted by this API."""
    require(set(observed) == {"domains", "pg", "chain", "quarantine",
                             "shared_databases", "lease", "checkpoint"},
            "OBSERVATION_SCHEMA")
    require(type(observed["domains"]) is dict and
            set(observed["domains"]) == DOMAINS and
            all(v == "FENCED_AND_RECONNECT_DENIED"
                for v in observed["domains"].values()), "WRITER_COVERAGE")
    require(set(observed["quarantine"]) == QUARANTINE and
            len(observed["quarantine"]) == len(QUARANTINE), "QUARANTINE_DRIFT")
    db = observed["shared_databases"]
    require(isinstance(db, list) and len(db) == len(set(db)) and
            set(db) == set(expected_databases) and
            {"aoe2hd_db", "aoe2de_db"} <= set(db), "SHARED_DATABASE_SCOPE")
    pg = observed["pg"]
    require(set(pg) == {"major", "system_id", "state", "prepared",
                        "client_processes", "restart_inhibited",
                        "external_tablespaces", "wal_present"} and
            type(pg["major"]) is int and pg["major"] == 16 and
            isinstance(pg["system_id"], str) and pg["system_id"].isdigit() and
            pg["state"] == "shut down" and
            type(pg["prepared"]) is int and pg["prepared"] == 0 and
            type(pg["client_processes"]) is int and pg["client_processes"] == 0 and
            pg["restart_inhibited"] is True and
            pg["external_tablespaces"] == [] and pg["wal_present"] is True,
            "PG_NOT_CLEAN_OFFLINE")
    chain = observed["chain"]
    require(set(chain) == {"chain_id", "block_height", "state_height",
                            "app_height", "state_app_hash", "app_commit_hash",
                            "closed", "restart_inhibited", "anchor_sha256"} and
            chain["chain_id"] == "wolo-1" and
            all(type(chain[k]) is int and chain[k] > 0 for k in
                ("block_height", "state_height", "app_height")) and
            chain["block_height"] == chain["state_height"] == chain["app_height"] and
            hash64(chain["state_app_hash"]) and
            chain["state_app_hash"] == chain["app_commit_hash"] and
            hash64(chain["anchor_sha256"]) and chain["closed"] is True and
            chain["restart_inhibited"] is True, "CHAIN_CHECKPOINT_INCONSISTENT")
    require(hash64(observed["lease"]) and hash64(observed["checkpoint"]),
            "CHECKPOINT_BINDING")
    return digest(canonical(observed))


def archive_budget(plain_tar_bytes, *, cipher_max, data_free, data_reserve,
                   receiver_free, receiver_reserve, restore_bytes):
    """No compression credit. Separate destination and recovery allocations."""
    values = (plain_tar_bytes, cipher_max, data_free, data_reserve,
              receiver_free, receiver_reserve, restore_bytes)
    require(all(type(v) is int and 0 < v < 1 << 50 for v in values), "BUDGET_TYPE")
    # Conservative allowance for age framing, header, recipients and tar end.
    bound = plain_tar_bytes + (plain_tar_bytes + 1023) // 1024 + (1 << 20)
    require(bound <= cipher_max, "CIPHERTEXT_LIMIT")
    require(cipher_max + data_reserve <= data_free, "DATA_CAPACITY")
    require(cipher_max + restore_bytes + receiver_reserve <= receiver_free,
            "RECEIVER_CAPACITY")
    return bound


def _fixture(path):
    path = Path(path)
    require(path.is_absolute() and path.resolve() == path and
            path.is_dir() and not path.is_symlink(), "FIXTURE_PATH")
    require((path / ".c06-disposable-fixture").is_file(), "FIXTURE_MARKER_REQUIRED")
    require(os.geteuid() != 0, "UNPRIVILEGED_REHEARSAL_ONLY")
    require(path.stat().st_uid == os.geteuid() and
            stat.S_IMODE(path.stat().st_mode) == 0o700, "FIXTURE_PRIVATE")
    return path


def inventory(fixture):
    fixture = _fixture(fixture)
    require({p.name for p in fixture.iterdir()} ==
            ROOTS | {".c06-disposable-fixture"}, "COMPONENT_SCOPE")
    entries = []
    for root in sorted(ROOTS):
        start = fixture / root
        require(start.is_dir() and not start.is_symlink(), "COMPONENT_MISSING")
        for current, dirs, files in os.walk(start, followlinks=False):
            dirs.sort()
            files.sort()
            for p in [Path(current)] + [Path(current) / x for x in files]:
                s = p.lstat()
                name = p.relative_to(fixture).as_posix()
                require(len(name.encode("utf-8")) <= 100 and
                        all(32 <= ord(c) < 127 for c in name), "USTAR_NAME")
                require(s.st_uid == os.geteuid() and not s.st_mode & 0o022,
                        "UNSAFE_SOURCE_OWNER_MODE")
                if stat.S_ISDIR(s.st_mode):
                    entries.append({"path": name, "type": "dir", "bytes": 0,
                                    "mode": stat.S_IMODE(s.st_mode)})
                else:
                    require(stat.S_ISREG(s.st_mode) and s.st_nlink == 1,
                            "SPECIAL_OR_LINKED_SOURCE")
                    # No chain validator/node keys or signing material in a restore.
                    require(not any(x in p.name.lower() for x in
                                    ("priv_validator_key", "node_key", "keyring",
                                     "mnemonic", "private-key", ".pem")),
                            "SIGNING_MATERIAL_FORBIDDEN")
                    entries.append({"path": name, "type": "file", "bytes": s.st_size,
                                    "mode": stat.S_IMODE(s.st_mode),
                                    "sha256": sha_file(p)})
                require(len(entries) <= MAX_ENTRIES, "ENTRY_LIMIT")
            for n in dirs:
                require(not (Path(current) / n).is_symlink(), "DIRECTORY_LINK")
    return sorted(entries, key=lambda x: x["path"])


def manifest(fixture, checkpoint_sha):
    require(hash64(checkpoint_sha), "CHECKPOINT_HASH")
    entries = inventory(fixture)
    return {"schema": "wolo.c06.offline-fixture-manifest.v1",
            "checkpoint_sha256": checkpoint_sha, "entries": entries}


def _round(n, b):
    return ((n + b - 1) // b) * b


def tar_size(m):
    raw = canonical(m)
    require(len(raw) <= MAX_MANIFEST, "MANIFEST_LIMIT")
    return _round(sum(BLOCK + _round(e["bytes"], BLOCK) for e in m["entries"])
                  + BLOCK + _round(len(raw), BLOCK) + 2 * BLOCK, 10240)


def write_tar(fixture, m, stream):
    fixture = _fixture(fixture)
    require(inventory(fixture) == m["entries"], "FROZEN_INVENTORY_DRIFT")
    raw = canonical(m)
    require(len(raw) <= MAX_MANIFEST, "MANIFEST_LIMIT")
    with tarfile.open(fileobj=stream, mode="w|", format=tarfile.USTAR_FORMAT) as tar:
        for e in m["entries"]:
            p = fixture / e["path"]
            s = p.lstat()
            require(stat.S_IMODE(s.st_mode) == e["mode"], "MODE_DRIFT")
            member = tarfile.TarInfo(e["path"])
            member.mode = e["mode"]
            member.uid = member.gid = member.mtime = 0
            if e["type"] == "dir":
                require(stat.S_ISDIR(s.st_mode), "TYPE_DRIFT")
                member.type = tarfile.DIRTYPE
                tar.addfile(member)
            else:
                require(stat.S_ISREG(s.st_mode) and s.st_nlink == 1 and
                        s.st_size == e["bytes"], "TYPE_OR_SIZE_DRIFT")
                member.size = e["bytes"]
                fd = os.open(p, os.O_RDONLY | os.O_NOFOLLOW)
                with os.fdopen(fd, "rb") as f:
                    a = os.fstat(f.fileno())
                    require((a.st_dev, a.st_ino, a.st_size) ==
                            (s.st_dev, s.st_ino, s.st_size), "OPEN_RACE")
                    tar.addfile(member, f)
                    b = os.fstat(f.fileno())
                    require((a.st_size, a.st_mtime_ns, a.st_ctime_ns) ==
                            (b.st_size, b.st_mtime_ns, b.st_ctime_ns), "READ_RACE")
        member = tarfile.TarInfo("manifest.json")
        member.size = len(raw)
        member.mode = 0o600
        tar.addfile(member, io.BytesIO(raw))
    require(inventory(fixture) == m["entries"], "POST_ARCHIVE_DRIFT")


def verify_tar(stream, expected_manifest, destination):
    """Extract only exact expected regular files/directories into a new fixture.

    A failed extraction leaves an unaccepted private directory for inspection.
    Never extracts into an existing database/chain home.
    """
    require(os.geteuid() != 0, "UNPRIVILEGED_REHEARSAL_ONLY")
    dest = Path(destination)
    require(dest.is_absolute() and dest.parent.resolve() == dest.parent and
            not os.path.lexists(dest), "FRESH_DESTINATION_REQUIRED")
    expected = {e["path"]: e for e in expected_manifest["entries"]}
    require(len(expected) == len(expected_manifest["entries"]) <= MAX_ENTRIES,
            "DUPLICATE_MANIFEST")
    dest.mkdir(mode=0o700)
    seen = set()
    manifest_seen = False
    with tarfile.open(fileobj=stream, mode="r|") as tar:
        for member in tar:
            name = member.name
            require(not manifest_seen and name not in seen, "DUPLICATE_OR_TRAILING_MEMBER")
            if name == "manifest.json":
                require(member.isfile() and member.size <= MAX_MANIFEST and
                        tar.extractfile(member).read() == canonical(expected_manifest),
                        "MANIFEST_MISMATCH")
                manifest_seen = True
                continue
            require(name in expected and not PurePosixPath(name).is_absolute() and
                    ".." not in PurePosixPath(name).parts and
                    PurePosixPath(name).parts[0] in ROOTS, "UNEXPECTED_MEMBER")
            e = expected[name]
            require(member.mode == e["mode"] and member.size == e["bytes"],
                    "MEMBER_METADATA_DRIFT")
            p = dest / name
            if e["type"] == "dir":
                require(member.isdir(), "DIRECTORY_TYPE")
                p.mkdir(mode=0o700)
            else:
                require(member.isfile() and member.type == tarfile.REGTYPE,
                        "FILE_TYPE")
                fd = os.open(p, os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_WRONLY, 0o600)
                h = hashlib.sha256()
                total = 0
                with os.fdopen(fd, "wb") as f:
                    reader = tar.extractfile(member)
                    while block := reader.read(1 << 20):
                        total += len(block)
                        require(total <= e["bytes"], "MEMBER_SIZE_OVERFLOW")
                        h.update(block)
                        f.write(block)
                require(total == e["bytes"] and h.hexdigest() == e["sha256"],
                        "MEMBER_HASH_MISMATCH")
                p.chmod(e["mode"])
            seen.add(name)
    require(manifest_seen and seen == set(expected), "INCOMPLETE_ARCHIVE")
    for e in reversed(expected_manifest["entries"]):
        if e["type"] == "dir":
            (dest / e["path"]).chmod(e["mode"])
    (dest / ".c06-disposable-fixture").touch(mode=0o600)
    require(inventory(dest) == expected_manifest["entries"], "RESTORE_INVENTORY_DRIFT")
    return digest(canonical(expected_manifest))


def run_phases(adapter, journal):
    """Isolated orchestration rehearsal; never calls host commands directly.

    The journal adapter must durably record each step before the next one.
    Failure never automatically restarts a writer or retries a mutation.
    """
    require(adapter.is_disposable_fixture is True, "REHEARSAL_ADAPTER_ONLY")
    journal("PREPARE")
    try:
        adapter.admit_fixture()
        journal("FENCE_INTENT")
        adapter.fence()
        journal("FROZEN")
        first = adapter.observe()
        checkpoint = validate_observation(first, expected_databases=adapter.databases)
        journal("CAPTURE_INTENT")
        cipher = adapter.capture(checkpoint)
        require(hash64(cipher), "CIPHERTEXT_HASH")
        require(adapter.observe() == first, "QUIESCENCE_LOST")
        adapter.verify_receiver(cipher)
        journal("CAPTURE_VERIFIED")
        # Restore is explicitly bound to the identical ciphertext.
        require(adapter.restore(cipher) == cipher, "RESTORE_CIPHERTEXT_DRIFT")
        journal("RECOVERY_VERIFIED")
        require(adapter.observe() == first, "QUIESCENCE_LOST")
        journal("RESTART_INTENT")
        adapter.restart_nonfinancial_only()
        adapter.verify_quarantine()
        journal("REHEARSAL_COMPLETE")
        return cipher
    except Exception:
        journal("HOLD_NO_AUTOMATIC_RETRY_OR_RESTART")
        raise


class _ExactPlainWriter:
    """No staging file; enforce exact plaintext length on the age pipe."""
    def __init__(self, stream, length):
        self.stream, self.limit, self.count = stream, length, 0
        self.hash = hashlib.sha256()

    def write(self, block):
        require(self.count + len(block) <= self.limit, "PLAINTEXT_LIMIT")
        n = self.stream.write(block)
        require(n == len(block), "PLAINTEXT_SHORT_WRITE")
        self.hash.update(block)
        self.count += n
        return n

def stream_age_ciphertext(write_plain, destination, *, plain_bytes,
                          cipher_max, reserve_bytes, age_path, age_sha256,
                          recipients, recipient_pin, timeout_seconds):
    """Bounded encryption stream to a private ciphertext-only destination.

    This is an I/O primitive, not admission, a production snapshot driver,
    or a producer fence. The protected caller must independently establish
    the complete immutable source scope, approved dual recipient pin, actual
    destination device and shared capacity/IO lease, and keep them valid.
    An incomplete stream never becomes an accepted ciphertext. On failure
    preserve the exclusive .incomplete evidence; do not retry or overwrite.
    Timeout bounds the encryption subprocess/pipe; it cannot interrupt
    arbitrary producer code blocked in kernel I/O.
    """
    require(all(type(v) is int and 0 < v < (1 << 50)
                for v in (plain_bytes,cipher_max,reserve_bytes)) and
            type(timeout_seconds) is int and 0 < timeout_seconds <= 14400,
            "STREAM_BUDGET_TYPE")
    require(plain_bytes + (plain_bytes+1023)//1024 + (1<<20) <= cipher_max,
            "STREAM_CIPHER_BOUND")
    binary=Path(age_path)
    require(binary.is_absolute() and binary.resolve(strict=True)==binary and
            hash64(age_sha256) and sha_file(binary)==age_sha256,
            "AGE_BINARY_PIN")
    bs=binary.stat()
    require(stat.S_ISREG(bs.st_mode) and bs.st_uid in (0,os.geteuid()) and
            not bs.st_mode&0o022 and bs.st_mode&0o111,"AGE_BINARY_UNSAFE")
    require(type(recipients) is tuple and len(recipients)==2 and
            len(set(recipients))==2 and all(type(x) is str and
            (re.fullmatch(r"age1[0-9a-z]{58}",x) or
             re.fullmatch(r"ssh-ed25519 [A-Za-z0-9+/=]{40,120}",x))
             for x in recipients) and
            digest(canonical(list(recipients)))==recipient_pin,
            "EXACT_DUAL_RECIPIENT_PIN")
    dest=Path(destination)
    require(dest.is_absolute() and dest.parent.resolve(strict=True)==dest.parent
            and re.fullmatch(r"[A-Za-z0-9_-]{1,120}\.age",dest.name),
            "CIPHERTEXT_DESTINATION")
    dfd=os.open(dest.parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    partial=dest.name+".incomplete"
    output=None
    process=None
    reader=None
    timer=None
    worker_errors=[]
    result={}
    expired=threading.Event()
    try:
        ds=os.fstat(dfd)
        require(stat.S_ISDIR(ds.st_mode) and ds.st_uid==os.geteuid() and
                stat.S_IMODE(ds.st_mode)==0o700,"CIPHERTEXT_DIRECTORY_PRIVATE")
        require(dest.name not in os.listdir(dfd) and partial not in os.listdir(dfd),
                "CIPHERTEXT_EXISTS_HOLD")
        def capacity(extra):
            fs=os.fstatvfs(dfd)
            require(fs.f_bavail*fs.f_frsize >= reserve_bytes+extra,
                    "STREAM_RESERVE_VIOLATION")
        capacity(cipher_max)
        fd=os.open(partial,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,
                   0o600,dir_fd=dfd)
        output=os.fdopen(fd,"wb",buffering=0)
        os.fsync(dfd)
        argv=[str(binary)]
        for recipient in recipients:argv+=["-r",recipient]
        # Only ciphertext reaches the disk; age reads from stdin.
        process=subprocess.Popen(argv,stdin=subprocess.PIPE,stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,env={"PATH":"/usr/bin:/bin","LANG":"C"})
        def kill():
            if process.poll() is None:
                try:process.kill()
                except ProcessLookupError:pass
        def timeout():
            expired.set()
            kill()
        def pump():
            h=hashlib.sha256();total=0
            try:
                while block:=process.stdout.read(1<<20):
                    require(not expired.is_set(),"STREAM_TIMEOUT")
                    require(total+len(block)<=cipher_max,"CIPHERTEXT_LIMIT")
                    capacity(len(block))
                    require(output.write(block)==len(block),"CIPHERTEXT_SHORT_WRITE")
                    h.update(block);total+=len(block)
                output.flush();os.fsync(output.fileno())
                result.update(bytes=total,sha256=h.hexdigest())
            except BaseException as exc:
                worker_errors.append(exc)
                kill()
        reader=threading.Thread(target=pump,daemon=True)
        timer=threading.Timer(timeout_seconds,timeout)
        timer.daemon=True
        reader.start();timer.start()
        plain=_ExactPlainWriter(process.stdin,plain_bytes)
        write_plain(plain)
        require(plain.count==plain_bytes,"PLAINTEXT_LENGTH_DRIFT")
        process.stdin.close()
        rc=process.wait(timeout=timeout_seconds)
        reader.join(timeout=5)
        require(not reader.is_alive(),"CIPHERTEXT_READER_HOLD")
        if worker_errors:raise worker_errors[0]
        require(rc==0 and not expired.is_set() and result.get("bytes",0)>0,
                "AGE_STREAM_FAILED_OR_TIMED_OUT")
        capacity(0)
        output.close();output=None
        readfd=os.open(partial,os.O_RDONLY|os.O_NOFOLLOW,dir_fd=dfd)
        h=hashlib.sha256()
        with os.fdopen(readfd,"rb") as check:
            s=os.fstat(check.fileno())
            require(stat.S_ISREG(s.st_mode) and s.st_uid==os.geteuid() and
                    stat.S_IMODE(s.st_mode)==0o600 and s.st_nlink==1 and
                    s.st_size==result["bytes"],"CIPHERTEXT_POSTIMAGE")
            while block:=check.read(1<<20):h.update(block)
            require(h.hexdigest()==result["sha256"],"CIPHERTEXT_READBACK")
        current=dest.parent.stat()
        require((current.st_dev,current.st_ino)==(ds.st_dev,ds.st_ino) and
                not expired.is_set(),"DESTINATION_IDENTITY_OR_TIME_DRIFT")
        # linkat is no-overwrite publication. Crash between link/unlink leaves
        # ambiguous evidence; the native caller must reconcile, never replay.
        os.link(partial,dest.name,src_dir_fd=dfd,dst_dir_fd=dfd,
                follow_symlinks=False)
        os.fsync(dfd)
        os.unlink(partial,dir_fd=dfd)
        os.fsync(dfd)
        final=os.stat(dest.name,dir_fd=dfd,follow_symlinks=False)
        require(final.st_nlink==1 and (final.st_dev,final.st_ino)==
                (s.st_dev,s.st_ino) and final.st_size==result["bytes"],
                "CIPHERTEXT_FINAL_IDENTITY")
        return {"schema":"wolo.c06.bounded-age-stream.v1",
                "ciphertext_bytes":result["bytes"],
                "ciphertext_sha256":result["sha256"],
                "plaintext_bytes":plain.count,
                "plaintext_sha256":plain.hash.hexdigest(),
                "recipient_pin":recipient_pin,
                "production_authorized":False,"c06_closed":False}
    finally:
        if timer is not None:timer.cancel()
        if process is not None:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=5)
            if reader is not None:reader.join(timeout=5)
            for pipe in (process.stdin,process.stdout):
                if pipe is not None and not pipe.closed:
                    try:pipe.close()
                    except BrokenPipeError:pass
        if output is not None:output.close()
        os.close(dfd)

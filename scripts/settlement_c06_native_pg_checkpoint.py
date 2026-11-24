"""Native offline PG16 checkpoint observation for the existing C06 driver.

No stop/start, no SQL, no CLI, no authority issuance. The caller must already
hold the authenticated maintenance lease and complete reconnect fence. The
result is an input to the checkpoint receipt, not proof of that fence.
"""
from __future__ import annotations
import hashlib
import os
from pathlib import Path
import re
import stat
import subprocess

from settlement_c06_checkpoint_rehearsal import canonical, digest, hash64, require

PGDATA = Path("/var/lib/postgresql/16/main")
PGCONTROL = Path("/usr/lib/postgresql/16/bin/pg_controldata")
FIELDS = ("Database system identifier", "Database cluster state",
          "Latest checkpoint location", "Latest checkpoint's REDO location",
          "Latest checkpoint's REDO WAL file", "Latest checkpoint's TimeLineID",
          "Bytes per WAL segment")
LSN = re.compile(r"[0-9A-F]+/[0-9A-F]+\Z")
WAL = re.compile(r"[0-9A-F]{24}\Z")


def parse_control(raw, expected_system_id):
    require(type(raw) is bytes and 0 < len(raw) <= 65536,
            "PG_CONTROL_OUTPUT_BOUND")
    fields = {}
    for line in raw.decode("ascii", errors="strict").splitlines():
        key, sep, value = line.partition(":")
        if key in FIELDS:
            require(sep and key not in fields, "PG_CONTROL_DUPLICATE")
            fields[key] = value.strip()
    require(set(fields) == set(FIELDS), "PG_CONTROL_FIELDS_MISSING")
    require(type(expected_system_id) is str and expected_system_id.isdecimal()
            and fields[FIELDS[0]] == expected_system_id,
            "PG_SYSTEM_ID_DRIFT")
    require(fields[FIELDS[1]] == "shut down", "PG_NOT_CLEAN_OFFLINE")
    require(all(LSN.fullmatch(fields[k]) for k in FIELDS[2:4])
            and WAL.fullmatch(fields[FIELDS[4]]), "PG_CHECKPOINT_WAL_ID")
    require(fields[FIELDS[5]].isdecimal() and fields[FIELDS[6]].isdecimal(),
            "PG_WAL_NUMERIC_FIELDS")
    timeline = int(fields[FIELDS[5]])
    seg = int(fields[FIELDS[6]])
    require(1 <= timeline <= 0xffffffff and 1 << 20 <= seg <= 1 << 30
            and seg & (seg - 1) == 0, "PG_WAL_SEGMENT_GEOMETRY")
    redo_high, redo_low = (int(v, 16) for v in fields[FIELDS[3]].split("/"))
    require(redo_high <= 0xffffffff and redo_low <= 0xffffffff,
            "PG_REDO_LSN_RANGE")
    expected_wal = f"{timeline:08X}{redo_high:08X}{redo_low // seg:08X}"
    require(fields[FIELDS[4]] == expected_wal, "PG_REDO_WAL_NAME_MISMATCH")
    return {"system_id": expected_system_id, "state": fields[FIELDS[1]],
            "checkpoint_lsn": fields[FIELDS[2]], "redo_lsn": fields[FIELDS[3]],
            "redo_wal": expected_wal, "timeline": timeline, "wal_segment_bytes": seg}


def _read_at(fd, name, limit):
    child = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
    with os.fdopen(child, "rb") as f:
        st = os.fstat(f.fileno())
        require(stat.S_ISREG(st.st_mode) and st.st_nlink == 1
                and 0 < st.st_size <= limit, "PG_FILE_IDENTITY")
        raw = f.read(limit + 1)
        end = os.fstat(f.fileno())
        require(len(raw) == st.st_size and
                (st.st_dev,st.st_ino,st.st_size,st.st_mtime_ns,st.st_ctime_ns) ==
                (end.st_dev,end.st_ino,end.st_size,end.st_mtime_ns,end.st_ctime_ns),
                "PG_FILE_CHANGED")
        return raw


def _child_dir(fd, name, dev):
    child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
    try:
        require(os.fstat(child).st_dev == dev, "PG_EXTERNAL_MOUNT")
        return child
    except BaseException:
        os.close(child)
        raise


def inspect_tree(fd, control):
    """Descriptor-relative physical checks; no recursive scan or writer claim."""
    dev = os.fstat(fd).st_dev
    require(_read_at(fd,"PG_VERSION",16).strip() == b"16", "PG_MAJOR_DRIFT")
    require("postmaster.pid" not in os.listdir(fd), "PG_POSTMASTER_PID_PRESENT")
    for name in ("pg_tblspc", "pg_twophase"):
        child = _child_dir(fd,name,dev)
        try:
            require(not os.listdir(child), "PG_TABLESPACE_OR_PREPARED_XACT")
        finally:
            os.close(child)
    child = _child_dir(fd,"global",dev)
    try:
        pg_control_sha = digest(_read_at(child,"pg_control",65536))
    finally:
        os.close(child)
    wal = _child_dir(fd,"pg_wal",dev)
    try:
        # Verify the exact REDO segment is physically present. Its full content
        # is hashed later by the admitted encrypted checkpoint archive.
        s = os.stat(control["redo_wal"],dir_fd=wal,follow_symlinks=False)
        require(stat.S_ISREG(s.st_mode) and s.st_nlink == 1 and
                s.st_dev == dev and s.st_size == control["wal_segment_bytes"],
                "PG_REDO_SEGMENT_MISSING_OR_INVALID")
    finally:
        os.close(wal)
    return pg_control_sha


def observe(expected_system_id, tool_sha):
    require(os.geteuid()==0 and hash64(tool_sha), "PG_NATIVE_ROOT_AND_TOOL_PIN")
    require(PGDATA.resolve(strict=True)==PGDATA and
            PGCONTROL.resolve(strict=True)==PGCONTROL, "PG_NATIVE_PATH_DRIFT")
    with PGCONTROL.open("rb") as f:
        s=os.fstat(f.fileno())
        require(stat.S_ISREG(s.st_mode) and s.st_uid==0 and not s.st_mode & 0o022
                and hashlib.file_digest(f,"sha256").hexdigest()==tool_sha,
                "PG_CONTROL_TOOL_PIN_DRIFT")
    fd=os.open(PGDATA,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:
        def read_control():
            p=subprocess.run([str(PGCONTROL),str(PGDATA)],capture_output=True,
                             timeout=15,env={"LANG":"C","LC_ALL":"C","PATH":"/usr/bin:/bin"})
            require(p.returncode==0 and not p.stderr,"PG_CONTROL_FAILED")
            return parse_control(p.stdout,expected_system_id)
        first=read_control()
        sha=inspect_tree(fd,first)
        second=read_control()
        end=PGDATA.stat()
        require(first==second and sha==inspect_tree(fd,second) and
                (end.st_dev,end.st_ino)==(os.fstat(fd).st_dev,os.fstat(fd).st_ino),
                "PG_CHECKPOINT_DRIFT")
        return {"schema":"wolo.c06.native-pg16-checkpoint.v1", **first,
                "pg_control_sha256":sha,"producer_fence_proven":False,
                "c06_closed":False}
    finally:
        os.close(fd)

"""Exact raw image stream and verification primitives; no host/transport CLI.

Caller must establish exclusive authorized IO, no mount/open writers, protected
source descriptor, approved recipient/transport and independently authenticated
recovery. No paths are opened here, no filesystem or authority is mutated.
"""
from __future__ import annotations

import hashlib
import os
import stat
import time

from settlement_c06_checkpoint_rehearsal import require, hash64

BLOCK=1<<20
MAX_BYTES=64<<30


def identity(fd):
    s=os.fstat(fd)
    require(stat.S_ISREG(s.st_mode) and s.st_nlink==1
            and 0<s.st_size<=MAX_BYTES and not s.st_mode&0o077,
            "IMAGE_DESCRIPTOR_UNSAFE")
    return {"device":s.st_dev,"inode":s.st_ino,"uid":s.st_uid,"gid":s.st_gid,
            "mode":stat.S_IMODE(s.st_mode),"bytes":s.st_size,
            "allocated_bytes":s.st_blocks*512,"mtime_ns":s.st_mtime_ns,
            "ctime_ns":s.st_ctime_ns}


def stream_exact(fd, expected, out, *, expected_sha=None):
    """Read exact pinned descriptor once, in bounded blocks, into admitted sink.

    Source SHA is over all logical bytes, including free blocks. Source read
    timings include blocking read syscalls, not sink wait or encryption CPU.
    Caller owns durable preimage/receipt authentication. No standalone permit.
    """
    require(identity(fd)==expected,"IMAGE_PREIMAGE_DRIFT")
    require(expected_sha is None or hash64(expected_sha),"IMAGE_SHA_PIN")
    size=expected["bytes"]
    h=hashlib.sha256();offset=read_ns=sink_ns=0
    start=time.monotonic_ns()
    while offset<size:
        tick=time.monotonic_ns()
        data=os.pread(fd,min(BLOCK,size-offset),offset)
        read_ns+=time.monotonic_ns()-tick
        require(0<len(data)<=size-offset,"IMAGE_SHORT_READ")
        h.update(data)
        tick=time.monotonic_ns()
        require(out.write(data)==len(data),"IMAGE_SINK_SHORT_WRITE")
        sink_ns+=time.monotonic_ns()-tick
        offset+=len(data)
    require(identity(fd)==expected,"IMAGE_POSTIMAGE_DRIFT")
    sha=h.hexdigest()
    require(expected_sha is None or sha==expected_sha,"IMAGE_SHA_MISMATCH")
    return {"schema":"wolo.financial.image-read.v1","bytes":offset,
            "sha256":sha,"source_read_ns":read_ns,"sink_write_ns":sink_ns,
            "wall_ns":time.monotonic_ns()-start,
            "retirement_authorized":False}


def verify_reconstruction(fd, expected_sha, expected_bytes):
    """Independent descriptor readback; no repair or mount operation."""
    require(hash64(expected_sha) and type(expected_bytes) is int
            and 0<expected_bytes<=MAX_BYTES,"IMAGE_RESTORE_EXPECTATION")
    pre=identity(fd)
    require(pre["bytes"]==expected_bytes,"IMAGE_RESTORE_SIZE")
    h=hashlib.sha256();offset=0
    start=time.monotonic_ns()
    while offset<expected_bytes:
        block=os.pread(fd,min(BLOCK,expected_bytes-offset),offset)
        require(0<len(block)<=expected_bytes-offset,"IMAGE_RESTORE_SHORT_READ")
        h.update(block);offset+=len(block)
    require(identity(fd)==pre and h.hexdigest()==expected_sha,
            "IMAGE_RESTORE_MISMATCH")
    return {"schema":"wolo.financial.image-readback.v1","sha256":expected_sha,
            "bytes":offset,"verification_ns":time.monotonic_ns()-start,
            "retirement_authorized":False}

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

# Financial source-side binding to the existing Transfer OS contiguous
# encrypted chunk shape. No transport, grant, signature issuer or executor.
PURPOSE="FINANCIAL_RECOVERY_IMAGE_COPY_ONLY"
IDENTITY_FIELDS=frozenset(("device","inode","uid","gid","mode","bytes",
                          "allocated_bytes","mtime_ns","ctime_ns"))
MAX_CHUNKS=4096


def financial_manifest(manifest, *, expected_plan, expected_source,
                       expected_manifest_sha, max_chunk_bytes):
    """Exact source identity/ordered chunk binding; not transport admission.

    The expected values MUST originate in separately authenticated native
    policy. This routine intentionally cannot authorize resume or retirement.
    The chunk keys match the Transfer OS #192 source contract.
    """
    from settlement_c06_checkpoint_rehearsal import canonical,digest
    require(type(manifest) is dict and set(manifest)=={
        "schema","purpose","plan_sha256","source","source_sha256","chunks"},
        "IMAGE_MANIFEST_FIELDS")
    require(manifest["schema"]=="wolo.financial.image-continuation.v1"
        and manifest["purpose"]==PURPOSE and hash64(expected_plan)
        and manifest["plan_sha256"]==expected_plan
        and hash64(manifest["source_sha256"])
        and hash64(expected_manifest_sha)
        and digest(canonical(manifest))==expected_manifest_sha,
        "IMAGE_MANIFEST_BINDING")
    source=manifest["source"]
    require(type(source) is dict and set(source)==IDENTITY_FIELDS
        and all(type(v) is int and v>=0 for v in source.values())
        and source==expected_source and 0<source["bytes"]<=MAX_BYTES
        and source["mode"]==0o600 and source["uid"]==0
        and source["gid"]==0 and source["allocated_bytes"]>=source["bytes"],
        "IMAGE_MANIFEST_SOURCE_IDENTITY")
    chunks=manifest["chunks"]
    require(type(max_chunk_bytes) is int and 0<max_chunk_bytes<=1<<32
        and type(chunks) is list and 0<len(chunks)<=MAX_CHUNKS,
        "IMAGE_MANIFEST_CHUNK_BOUND")
    offset=cipher_total=0
    for i,c in enumerate(chunks):
        require(type(c) is dict and set(c)=={
            "index","offset","plain_bytes","cipher_bytes","plain_sha256","cipher_sha256"}
            and type(c["index"]) is int and c["index"]==i
            and type(c["offset"]) is int and c["offset"]==offset
            and type(c["plain_bytes"]) is int and 0<c["plain_bytes"]<=max_chunk_bytes
            and type(c["cipher_bytes"]) is int
            and 0<c["cipher_bytes"]<=max_chunk_bytes+(1<<20)
            and hash64(c["plain_sha256"]) and hash64(c["cipher_sha256"]),
            "IMAGE_MANIFEST_CHUNK_DRIFT")
        offset+=c["plain_bytes"];cipher_total+=c["cipher_bytes"]
        require(offset<=source["bytes"],"IMAGE_MANIFEST_OVERRUN")
    require(offset==source["bytes"],"IMAGE_MANIFEST_INCOMPLETE")
    return {"schema":"wolo.financial.image-manifest-binding.v1",
            "manifest_sha256":expected_manifest_sha,"plan_sha256":expected_plan,
            "source_sha256":manifest["source_sha256"],"source_bytes":offset,
            "ciphertext_bytes":cipher_total,"chunks":len(chunks),
            "resume_authorized":False,"retirement_authorized":False}


def verify_financial_reconstruction(fd, manifest, *, expected_plan,
        expected_source, expected_manifest_sha, max_chunk_bytes):
    """Read back every original logical byte AND every ordered chunk digest.

    Native independent recovery must supply a privately reconstructed raw
    descriptor. This is a local measurement, NOT an authenticated Intel
    receipt, a filesystem mount check or permission to retire the original.
    """
    bound=financial_manifest(manifest,expected_plan=expected_plan,
        expected_source=expected_source,expected_manifest_sha=expected_manifest_sha,
        max_chunk_bytes=max_chunk_bytes)
    pre=identity(fd)
    require(pre["bytes"]==bound["source_bytes"],"IMAGE_RESTORE_SIZE")
    total=hashlib.sha256();offset=0;start=time.monotonic_ns()
    for c in manifest["chunks"]:
        chunk=hashlib.sha256()
        remaining=c["plain_bytes"]
        while remaining:
            data=os.pread(fd,min(BLOCK,remaining),offset)
            require(0<len(data)<=remaining,"IMAGE_RESTORE_SHORT_READ")
            total.update(data);chunk.update(data)
            offset+=len(data);remaining-=len(data)
        require(chunk.hexdigest()==c["plain_sha256"],"IMAGE_RESTORE_CHUNK_MISMATCH")
    require(identity(fd)==pre and total.hexdigest()==bound["source_sha256"],
            "IMAGE_RESTORE_MISMATCH")
    return {"schema":"wolo.financial.image-continuation-readback.v1",
            "manifest_sha256":expected_manifest_sha,"plan_sha256":expected_plan,
            "sha256":total.hexdigest(),"bytes":offset,
            "chunks":bound["chunks"],"verification_ns":time.monotonic_ns()-start,
            "independent_host_authenticated":False,"retirement_authorized":False}

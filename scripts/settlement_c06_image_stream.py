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
    require(manifest["schema"]=="wolo.financial.image-source-manifest.v1"
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


def financial_chunk_receipt(raw, manifest, *, expected_plan, expected_source,
        expected_manifest_sha, max_chunk_bytes, expected_index,
        expected_receipt_sha, expected_receiver, verify_native_receipt):
    """Correlate a verified #192 financial-class chunk ACK to the exact manifest.

    A separately enrolled native verifier must authenticate the raw receipt.
    This adapter does not implement that verifier, grant continuation,
    remember spent nonces or attest independent recovery.
    """
    import json
    from settlement_c06_checkpoint_rehearsal import canonical,digest
    bound=financial_manifest(manifest,expected_plan=expected_plan,
        expected_source=expected_source,expected_manifest_sha=expected_manifest_sha,
        max_chunk_bytes=max_chunk_bytes)
    require(type(expected_index) is int and 0<=expected_index<bound["chunks"]
        and hash64(expected_receiver) and hash64(expected_receipt_sha)
        and type(raw) is bytes and 0<len(raw)<=32768
        and digest(raw)==expected_receipt_sha and callable(verify_native_receipt),
        "IMAGE_RECEIPT_BINDING")
    def pairs(items):
        result={}
        for k,v in items:
            require(k not in result,"IMAGE_RECEIPT_DUPLICATE")
            result[k]=v
        return result
    try:
        parsed=json.loads(raw,object_pairs_hook=pairs)
    except (UnicodeError,ValueError):
        raise ValueError("IMAGE_RECEIPT_JSON") from None
    verified=verify_native_receipt(raw)
    require(type(verified) is dict and canonical(verified)==canonical(parsed),
            "IMAGE_RECEIPT_NATIVE_VERIFIER")
    chunk=manifest["chunks"][expected_index]
    expected={
        "schema":"wolo.financial.image-chunk-ack.v1","purpose":PURPOSE,
        "plan_sha256":expected_plan,"manifest_sha256":expected_manifest_sha,
        "source_sha256":bound["source_sha256"],"receiver_identity_sha256":expected_receiver,
        "index":expected_index,"offset":chunk["offset"],
        "ciphertext_sha256":chunk["cipher_sha256"],
        "ciphertext_bytes":chunk["cipher_bytes"],
        "status":"CIPHERTEXT_DURABLE_READBACK_VERIFIED_NOT_RESTORED",
        "retirement_authorized":False}
    require(canonical(verified)==canonical(expected),"IMAGE_RECEIPT_SCOPE_OR_CHUNK_DRIFT")
    return {"schema":"wolo.financial.image-chunk-correlation.v1",
        "manifest_sha256":expected_manifest_sha,"index":expected_index,
        "receipt_sha256":expected_receipt_sha,
        "ciphertext_bytes":chunk["cipher_bytes"],"ciphertext_sha256":chunk["cipher_sha256"],
        "independent_restore":False,"resume_authorized":False,
        "retirement_authorized":False}


def financial_prefix(initial, receipts, *, expected_initial_sha, verify_initial,
                     verify_receipt):
    """Read-only authenticated-prefix projection, not a sender or grant issuer.

    Native policy pins the initial identity before the first encryption.
    Each receipt must be authenticated by the existing class-specific
    verifier and linked to the preceding receipt. No final image hash is
    assumed at campaign start. The controller owns durability/replay
    exclusion; this function cannot persist or authorize anything.
    """
    import re
    from settlement_c06_checkpoint_rehearsal import canonical,digest
    require(type(initial) is dict and set(initial)=={
        "schema","purpose","campaign","plan_sha256","source","max_chunk_bytes",
        "recipient_sha256","receiver_identity_sha256"},"PREFIX_INITIAL_FIELDS")
    require(initial["schema"]=="wolo.financial.image-prefix-identity.v1"
        and initial["purpose"]==PURPOSE
        and type(initial["campaign"]) is str
        and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}",initial["campaign"])
        and all(hash64(initial[k]) for k in ("plan_sha256","recipient_sha256",
                                               "receiver_identity_sha256"))
        and hash64(expected_initial_sha)
        and digest(canonical(initial))==expected_initial_sha
        and callable(verify_initial) and verify_initial(canonical(initial)) is True,
        "PREFIX_INITIAL_BINDING")
    source=initial["source"];limit=initial["max_chunk_bytes"]
    require(type(source) is dict and set(source)==IDENTITY_FIELDS
        and all(type(v) is int and v>=0 for v in source.values())
        and 0<source["bytes"]<=MAX_BYTES and source["mode"]==0o600
        and source["uid"]==source["gid"]==0
        and source["allocated_bytes"]>=source["bytes"]
        and type(limit) is int and 0<limit<=1<<32,
        "PREFIX_SOURCE_IDENTITY")
    require(type(receipts) is list and len(receipts)<=MAX_CHUNKS
        and callable(verify_receipt),"PREFIX_RECEIPT_BOUND")
    previous=expected_initial_sha;offset=0;cipher_total=0;chunks=[]
    for i,r in enumerate(receipts):
        require(type(r) is dict and set(r)=={"schema","initial_sha256","previous",
            "receiver_identity_sha256","chunk","status","retirement_authorized"},
            "PREFIX_RECEIPT_FIELDS")
        require(r["schema"]=="wolo.financial.image-prefix-readback.v1"
            and r["initial_sha256"]==expected_initial_sha and r["previous"]==previous
            and r["receiver_identity_sha256"]==initial["receiver_identity_sha256"]
            and r["status"]=="CIPHERTEXT_DURABLE_READBACK_VERIFIED_NOT_RESTORED"
            and r["retirement_authorized"] is False,"PREFIX_RECEIPT_LINEAGE")
        c=r["chunk"]
        require(type(c) is dict and set(c)=={"index","offset","plain_bytes",
            "cipher_bytes","plain_sha256","cipher_sha256"}
            and type(c["index"]) is int and c["index"]==i
            and type(c["offset"]) is int and c["offset"]==offset
            and type(c["plain_bytes"]) is int and 0<c["plain_bytes"]<=limit
            and type(c["cipher_bytes"]) is int and 0<c["cipher_bytes"]<=limit+(1<<20)
            and hash64(c["plain_sha256"]) and hash64(c["cipher_sha256"]),
            "PREFIX_CHUNK_DRIFT")
        raw=canonical(r)
        require(verify_receipt(raw) is True,"PREFIX_RECEIPT_NOT_AUTHENTICATED")
        previous=digest(raw)
        offset+=c["plain_bytes"];cipher_total+=c["cipher_bytes"]
        require(offset<=source["bytes"],"PREFIX_OVERRUN")
        chunks.append(dict(c))
    return {"schema":"wolo.financial.image-prefix-projection.v1",
            "initial_sha256":expected_initial_sha,"tip_sha256":previous,
            "verified_plain_bytes":offset,"verified_cipher_bytes":cipher_total,
            "chunks":chunks,"coverage_complete":offset==source["bytes"],
            "resume_authorized":False,"retirement_authorized":False}


def seal_transfer_manifest(initial, receipts, *, expected_initial_sha,
        verify_initial, verify_receipt, source_sha256, expected_seal_sha,
        verify_seal):
    """Map complete authenticated prefix to exact #192 whole-image schema.

    The authenticated final seal binds the original source digest and prefix
    tip. A shape-only prefix or a caller's hash cannot establish that seal.
    The result is a candidate for #192's own native verification, never a
    recovery or retirement receipt.
    """
    from settlement_c06_checkpoint_rehearsal import canonical,digest
    p=financial_prefix(initial,receipts,expected_initial_sha=expected_initial_sha,
                       verify_initial=verify_initial,verify_receipt=verify_receipt)
    require(p["coverage_complete"] and hash64(source_sha256)
            and hash64(expected_seal_sha) and callable(verify_seal),"PREFIX_SEAL_INCOMPLETE")
    manifest={"schema":"wolo.financial.image-continuation.v1",
              "identity":{"purpose":"FULL_IMAGE_EXACT","campaign":initial["campaign"],
                "plan_sha256":initial["plan_sha256"],
                "source_identity_sha256":digest(canonical(initial["source"])),
                "source_sha256":source_sha256,"source_bytes":initial["source"]["bytes"],
                "max_chunk_bytes":initial["max_chunk_bytes"],
                "recipient_sha256":initial["recipient_sha256"]},"chunks":p["chunks"]}
    seal={"schema":"wolo.financial.image-prefix-seal.v1",
          "initial_sha256":expected_initial_sha,"tip_sha256":p["tip_sha256"],
          "manifest_sha256":digest(canonical(manifest)),"source_sha256":source_sha256}
    raw=canonical(seal)
    require(digest(raw)==expected_seal_sha and verify_seal(raw) is True,
            "PREFIX_SEAL_NOT_AUTHENTICATED")
    return {"manifest":manifest,"seal":seal,"seal_sha256":expected_seal_sha,
            "independent_restore":False,"resume_authorized":False,
            "retirement_authorized":False}


def reconstruct_financial_image(fd, manifest, *, expected_plan, expected_source,
        expected_manifest_sha, max_chunk_bytes, open_verified_plaintext):
    """Single destination, bounded plaintext reconstruction and full readback.

    The native Intel Linux driver owns isolated target admission, immutable
    encrypted receipt verification, decryptor authentication/exit status,
    reserve and mount exclusion. open_verified_plaintext(chunk) must be a
    context manager which raises on failed authentication or decryption.
    No source path or temp file is opened here. Partial output is retained
    on failure and cannot be automatically replayed into this descriptor.
    """
    bound=financial_manifest(manifest,expected_plan=expected_plan,
        expected_source=expected_source,expected_manifest_sha=expected_manifest_sha,
        max_chunk_bytes=max_chunk_bytes)
    st=os.fstat(fd)
    require(stat.S_ISREG(st.st_mode) and st.st_nlink==1 and st.st_size==0
            and st.st_uid==os.geteuid() and stat.S_IMODE(st.st_mode)==0o600
            and (st.st_dev,st.st_ino)!=(expected_source["device"],expected_source["inode"])
            and callable(open_verified_plaintext),"IMAGE_NEW_TARGET_REQUIRED")
    total=hashlib.sha256();offset=0
    start=time.monotonic_ns()
    for c in manifest["chunks"]:
        require(offset==c["offset"],"IMAGE_RECONSTRUCTION_OFFSET")
        h=hashlib.sha256();remaining=c["plain_bytes"]
        # Context exit must verify native decryptor success, even if the
        # expected bytes were already delivered. Never accept a truncated tag.
        with open_verified_plaintext(dict(c)) as stream:
            while remaining:
                data=stream.read(min(BLOCK,remaining))
                require(type(data) is bytes and 0<len(data)<=min(BLOCK,remaining),
                        "IMAGE_RECONSTRUCTION_SHORT_OR_OVERSIZE")
                h.update(data);total.update(data)
                n=os.pwrite(fd,data,offset)
                require(n==len(data),"IMAGE_RECONSTRUCTION_SHORT_WRITE")
                offset+=n;remaining-=n
            require(stream.read(1)==b"","IMAGE_RECONSTRUCTION_TRAILING_PLAINTEXT")
        require(h.hexdigest()==c["plain_sha256"],"IMAGE_RECONSTRUCTION_CHUNK_HASH")
    require(offset==bound["source_bytes"] and total.hexdigest()==bound["source_sha256"],
            "IMAGE_RECONSTRUCTION_WHOLE_HASH")
    os.fsync(fd)
    end=os.fstat(fd)
    require((end.st_dev,end.st_ino,end.st_uid,end.st_mode,end.st_nlink)==
            (st.st_dev,st.st_ino,st.st_uid,st.st_mode,st.st_nlink)
            and end.st_size==offset,"IMAGE_RECONSTRUCTION_TARGET_DRIFT")
    proof=verify_financial_reconstruction(fd,manifest,expected_plan=expected_plan,
        expected_source=expected_source,expected_manifest_sha=expected_manifest_sha,
        max_chunk_bytes=max_chunk_bytes)
    return {**proof,"schema":"wolo.financial.image-single-target-reconstruction.v1",
            "single_target":True,"reconstruction_wall_ns":time.monotonic_ns()-start,
            "independent_host_authenticated":False,"retirement_authorized":False}

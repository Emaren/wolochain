#!/usr/bin/env python3
"""Versioned real SINGLE owner financial intent signature review (OFFLINE HOLD).

A verified owner signature is not a bank/finality/solvency proof, a producer
fence, an off-host monotonic nonce witness or a production permit. The existing
five-person production controller remains unchanged and refuses production.
This read-only verifier demonstrates a genuine one-human alternative signature
domain without inventing four other people or consuming release authority.
"""
from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile

DOMAIN = b"AOE2WAR-WOLO-SOLO-OWNER-INTENT-V1\x00"
SCHEMA = "wolo.solo-owner-financial-intent.v1"
PACKET_SCHEMA = "wolo.solo-owner-signed-intent.v1"
ENROLL_SCHEMA = "wolo.solo-owner-public-enrollment.v1"
HEX32 = re.compile(r"[a-f0-9]{32}\Z")
HEX40 = re.compile(r"[a-f0-9]{40}\Z")
HEX64 = re.compile(r"[a-f0-9]{64}\Z")
IDENTITY = re.compile(r"[a-z][a-z0-9_-]{2,63}\Z")
WINDOW = 20 * 60
OPS = {
    "live_capture": "fence-drain-capture-hd-de",
    "offline_verify": "isolated-restore-verify-sealed-archives",
    "resume": "reviewed-resume-existing-hd-de-units",
    "funded_activate": "owner-authorized-bounded-canary",
}
REQUEST_KEYS = {
    "schema", "chain_id", "phase", "operation", "source_commit",
    "consensus_binary_sha256", "settlement_binary_sha256",
    "scope_sha256", "global_fence_sha256", "bank_proof_sha256",
    "liability_proof_sha256", "rollback_receipt_sha256",
    "previous_phase_receipt_sha256", "nonce",
    "not_before", "expires_at",
}
PACKET_KEYS = {"schema", "owner_key_id", "request", "signature_b64"}
ENROLL_KEYS = {
    "schema", "owner_key_id", "public_key_pem",
    "valid_from", "valid_until", "revoked",
}


class AuthorityHold(ValueError):
    pass


def require(ok, reason):
    if not ok:
        raise AuthorityHold(reason)


def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True).encode("ascii")


def unique(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "DUPLICATE_JSON_FIELD")
        result[key] = value
    return result


def hex64(x):
    return type(x) is str and HEX64.fullmatch(x) is not None and x != "0" * 64


def read_private(path):
    p = Path(path)
    require(p.is_absolute(), "ABSOLUTE_PRIVATE_PATH_REQUIRED")
    root = p.parent
    before_dir = root.lstat()
    require(stat.S_ISDIR(before_dir.st_mode) and not root.is_symlink()
            and stat.S_IMODE(before_dir.st_mode) == 0o700
            and before_dir.st_uid == os.geteuid(), "PRIVATE_DIRECTORY_UNSAFE")
    fd = None
    try:
        fd = os.open(p, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        before = os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1
                and before.st_uid == os.geteuid()
                and stat.S_IMODE(before.st_mode) == 0o600
                and 0 < before.st_size < 131072, "PRIVATE_FILE_UNSAFE")
        data = os.read(fd, 131072)
        after = os.fstat(fd)
        require(len(data) == before.st_size and all(
            getattr(before, k) == getattr(after, k)
            for k in ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
        ), "PRIVATE_FILE_CHANGED")
        return data
    except AuthorityHold:
        raise
    except OSError as exc:
        raise AuthorityHold("PRIVATE_FILE_UNAVAILABLE") from exc
    finally:
        if fd is not None:
            os.close(fd)


def parse(raw):
    try:
        o = json.loads(raw, object_pairs_hook=unique,
                       parse_float=lambda _: require(False, "FLOAT_FORBIDDEN"),
                       parse_constant=lambda _: require(False, "NONFINITE_FORBIDDEN"))
    except AuthorityHold:
        raise
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise AuthorityHold("INVALID_JSON") from exc
    require(type(o) is dict, "JSON_OBJECT_REQUIRED")
    return o


def utc(s):
    require(type(s) is str and re.fullmatch(
        r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", s) is not None,
        "UTC_SECONDS_REQUIRED")
    try:
        return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise AuthorityHold("UTC_INVALID") from exc


def openssl(*args, input_data=None):
    try:
        result = subprocess.run(["openssl", *args], input=input_data,
                                capture_output=True, timeout=8, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise AuthorityHold("OPENSSL_UNAVAILABLE") from exc
    require(result.returncode == 0, "INVALID_PUBLIC_KEY_OR_SIGNATURE")
    return result.stdout


def authenticate_owner(enrollment_raw, packet_raw, *, pinned_enrollment_sha256,
           pinned_owner_der_sha256, packet_schema, domain, validate_request, now=None):
    require(hex64(pinned_enrollment_sha256) and hex64(pinned_owner_der_sha256)
            and hashlib.sha256(enrollment_raw).hexdigest() == pinned_enrollment_sha256,
            "EXTERNAL_ENROLLMENT_PIN_MISMATCH")
    e = parse(enrollment_raw)
    require(set(e) == ENROLL_KEYS and e["schema"] == ENROLL_SCHEMA,
            "OWNER_ENROLLMENT_SCHEMA_INVALID")
    require(type(e["owner_key_id"]) is str and IDENTITY.fullmatch(e["owner_key_id"])
            and type(e["revoked"]) is bool and e["revoked"] is False
            and type(e["public_key_pem"]) is str
            and 80 < len(e["public_key_pem"]) < 2048
            and e["public_key_pem"].startswith("-----BEGIN PUBLIC KEY-----\n")
            and e["public_key_pem"].endswith("-----END PUBLIC KEY-----\n"),
            "OWNER_PUBLIC_ENROLLMENT_INVALID")
    der = openssl("pkey", "-pubin", "-inform", "PEM", "-outform", "DER",
                  input_data=e["public_key_pem"].encode("ascii"))
    require(hashlib.sha256(der).hexdigest() == pinned_owner_der_sha256,
            "PINNED_OWNER_PUBLIC_KEY_MISMATCH")
    n = datetime.now(timezone.utc) if now is None else now
    require(n.tzinfo is not None and n.utcoffset() == timedelta(),
            "UTC_RUNTIME_CLOCK_REQUIRED")
    require(utc(e["valid_from"]) <= n <= utc(e["valid_until"]),
            "OWNER_ENROLLMENT_EXPIRED")

    packet = parse(packet_raw)
    require(set(packet) == PACKET_KEYS and packet["schema"] == packet_schema
            and packet["owner_key_id"] == e["owner_key_id"],
            "OWNER_PACKET_SCHEMA_OR_KEY_MISMATCH")
    q = packet["request"]
    require(type(q) is dict, "SIGNED_REQUEST_OBJECT_REQUIRED")
    validate_request(q, n)
    try:
        sig = base64.b64decode(packet["signature_b64"], validate=True)
    except (ValueError, TypeError, binascii.Error) as exc:
        raise AuthorityHold("SIGNATURE_ENCODING_INVALID") from exc
    require(len(sig) == 64, "ED25519_SIGNATURE_LENGTH_INVALID")
    message = domain + canonical({"owner_key_id": e["owner_key_id"], "request": q})
    with tempfile.TemporaryDirectory(prefix="wolo-solo-intent-") as directory:
        folder = Path(directory)
        key, payload, signature = [folder / x for x in ("key.pem", "msg", "sig")]
        for file, data in (
            (key, e["public_key_pem"].encode("ascii")),
            (payload, message), (signature, sig)
        ):
            file.write_bytes(data)
            file.chmod(0o600)
        openssl("pkeyutl", "-verify", "-pubin", "-rawin", "-inkey",
                str(key), "-in", str(payload), "-sigfile", str(signature))
    return e, q, n


def _validate_request(q, n):
    require(type(q) is dict and set(q) == REQUEST_KEYS and q["schema"] == SCHEMA
            and q["chain_id"] == "wolo-1" and type(q["phase"]) is str
            and q["phase"] in OPS
            and q["operation"] == OPS[q["phase"]], "SIGNED_OPERATION_UNAPPROVED")
    require(type(q["source_commit"]) is str and HEX40.fullmatch(q["source_commit"])
            and all(hex64(q[k]) for k in (
                "consensus_binary_sha256", "settlement_binary_sha256",
                "scope_sha256", "global_fence_sha256",
                "bank_proof_sha256", "liability_proof_sha256",
                "rollback_receipt_sha256")),
            "SOURCE_AND_ARTIFACT_BINDINGS_INCOMPLETE")
    old = q["previous_phase_receipt_sha256"]
    require((old is None if q["phase"] == "live_capture" else hex64(old)),
            "PRIOR_SIGNED_PHASE_LINEAGE_MISSING")
    require(type(q["nonce"]) is str and HEX32.fullmatch(q["nonce"])
            and q["nonce"] != "0" * 32, "FRESH_NONCE_INVALID")
    begin, expires = utc(q["not_before"]), utc(q["expires_at"])
    require(begin <= n < expires and timedelta() < expires - begin
            <= timedelta(seconds=WINDOW), "OWNER_PHASE_WINDOW_INVALID")


def review(enrollment_raw, packet_raw, *, pinned_enrollment_sha256,
           pinned_owner_der_sha256, now=None):
    _, q, _ = authenticate_owner(
        enrollment_raw, packet_raw,
        pinned_enrollment_sha256=pinned_enrollment_sha256,
        pinned_owner_der_sha256=pinned_owner_der_sha256,
        packet_schema=PACKET_SCHEMA, domain=DOMAIN,
        validate_request=_validate_request, now=now)
    # Source-review truth only. No consumption, off-host monotonicity, P1 source
    # provenance, asset proof, signer census, or production permissions.
    return {
        "schema": "wolo.solo-owner-offline-review.v1",
        "status": "CRYPTO_VALID_NONAUTHORIZING",
        "phase": q["phase"],
        "request_sha256": hashlib.sha256(canonical(q)).hexdigest(),
        "owner_der_sha256": pinned_owner_der_sha256,
        "nonce_commitment_sha256": hashlib.sha256(q["nonce"].encode()).hexdigest(),
        "real_single_owner_signature_verified": True,
        "independent_chain_finality_authenticated": False,
        "same_height_solvency_authenticated": False,
        "offhost_monotonic_nonce_consumed": False,
        "all_financial_writers_fenced": False,
        "owner_financial_operation_authorized": False,
        "production_mutated": False,
        "next": "Enroll independent witness and prove custody/finality/solvency/fence; separately authorize each live financial phase.",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--enrollment", type=Path, required=True)
    parser.add_argument("--packet", type=Path, required=True)
    parser.add_argument("--pinned-enrollment-sha256", required=True)
    parser.add_argument("--pinned-owner-der-sha256", required=True)
    args = parser.parse_args(argv)
    try:
        result = review(
            read_private(args.enrollment), read_private(args.packet),
            pinned_enrollment_sha256=args.pinned_enrollment_sha256,
            pinned_owner_der_sha256=args.pinned_owner_der_sha256,
        )
    except (AuthorityHold, UnicodeError, OSError, ValueError) as exc:
        print(json.dumps({"status": "HOLD", "reason": str(exc),
                          "owner_financial_operation_authorized": False}, sort_keys=True))
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 3


if __name__ == "__main__":
    sys.exit(main())

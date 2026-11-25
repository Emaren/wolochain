#!/usr/bin/env python3
"""C06 read-only HEL1 -> Intel SSH host-identity witness, NOT backup acceptance.

An SSH banner or reverse listener is never equivalent to a successfully
authenticated encrypted backup or C07 restore. Compare the live ED25519 host
key to the exact previously root-enrolled identity and return only HOLD/STOP.
Never initiate an SSH login, stage credentials, transfer archive, change a
service, or grant financial authority.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import stat
import subprocess
import sys
from datetime import datetime, timezone

SCHEMA="wolo.c06.intel-offhost-hostidentity-observed-finance-hold.v1"
HOST="ubuntu-4gb-hel1-11"
PORT=22996
ENROLLMENT=Path("/root/aoe2war-c06-transport-enrollment-20261107/c06-intel-physical-accepted.json")
ENROLLMENT_SHA256="3371c79a3728ebbadc9f186e9492313c2a5039aae9eee337b9c83dc816210562"
MAX_BYTES=8192

class Hold(ValueError):
    pass

def need(ok,reason):
    if not ok:
        raise Hold(reason)

def hex_digest(data:bytes)->str:
    return hashlib.sha256(data).hexdigest()

def parse_enrollment(raw:bytes):
    need(0<len(raw)<MAX_BYTES and hex_digest(raw)==ENROLLMENT_SHA256,
         "C06_ROOT_ENROLLMENT_SHA_CHANGED")
    try:
        d=json.loads(raw)
    except (ValueError,UnicodeError):
        raise Hold("C06_ENROLLMENT_INVALID_JSON") from None
    need(type(d) is dict,"C06_ENROLLMENT_NOT_OBJECT")
    # Explicitly pin status and scope, not merely fingerprint.
    need(d.get("schema")=="aoe2war.c06.intel-transport-live.v1"
         and d.get("status")=="PASS_C06_ONLY_TRANSPORT_PHYSICALLY_VERIFIED"
         and d.get("remote_listen")=="127.0.0.1:22996"
         and d.get("scope")=="transport-only: dedicated Intel SSH reverse path",
         "C06_ENROLLMENT_STATUS_OR_SCOPE_CHANGED")
    for field in ("financial_release_authorized","formal_c06_gate_accepted",
                  "formal_c07_gate_accepted","global_c03_gate_accepted",
                  "quiesced_joint_financial_backup_captured"):
        need(d.get(field) is False,"C06_ENROLLMENT_FALSE_RELEASE_CLAIM")
    need(d.get("intel_launchd_reconnect_observed") is True,
         "C06_PRIOR_OFFHOST_LAUNCHD_ENROLLMENT_ABSENT")
    fp=d.get("intel_ssh_host_fingerprint")
    need(type(fp) is str and
         re.fullmatch(r"SHA256:[A-Za-z0-9+/]{43}",fp),
         "C06_PINNED_HOST_FINGERPRINT_FORMAT")
    return fp

def parse_live_public_key(scan:str):
    need(type(scan) is str and 0<len(scan.encode())<MAX_BYTES,
         "C06_HOST_PUBLIC_KEY_RESULT_MISSING")
    keys=[]
    for line in scan.splitlines():
        if line.startswith("#") or not line.strip():
            continue
        fields=line.split()
        need(len(fields)==3 and fields[0] in (
            "[127.0.0.1]:22996","127.0.0.1:22996"
        ) and fields[1]=="ssh-ed25519",
             "C06_UNEXPECTED_SSH_HOST_KEY_ALGORITHM_OR_ENDPOINT")
        try:
            blob=base64.b64decode(fields[2],validate=True)
        except (ValueError,base64.binascii.Error):
            raise Hold("C06_REMOTE_HOST_KEY_INVALID_B64") from None
        need(40<=len(blob)<=4096 and blob[0:4]==b"\x00\x00\x00\x0b"
             and blob[4:15]==b"ssh-ed25519",
             "C06_HOST_KEY_BLOB_MALFORMED")
        # Pinned public host fingerprint is the SHA256 of the SSH wire blob.
        fp="SHA256:"+base64.b64encode(hashlib.sha256(blob).digest()).decode().rstrip("=")
        keys.append(fp)
    need(len(keys)==1,"C06_HOST_KEY_MISSING_OR_DUPLICATE")
    return keys[0]

def verify(enrollment_raw:bytes,banner:bytes,keyscan:str):
    expected=parse_enrollment(enrollment_raw)
    need(type(banner) is bytes and len(banner)<=256 and
         banner.startswith(b"SSH-2.0-") and b"\n" in banner,
         "C06_REVERSE_PORT_NOT_AUTHENTIC_SSH_BANNER")
    got=parse_live_public_key(keyscan)
    need(got==expected,"C06_OFFHOST_SSH_IDENTITY_DRIFT")
    return {
        "schema":SCHEMA,
        "status":"HOLD_C06_TRANSPORT_HOST_IDENTITY_MATCHED_BACKUP_NOT_CAPTURED",
        "observed_utc":datetime.now(timezone.utc).isoformat(),
        "enrollment_sha256":ENROLLMENT_SHA256,
        "transport_endpoint":"127.0.0.1:22996",
        "live_server_banner_is_ssh2":True,
        "live_ed25519_host_identity_matches_previously_enrolled":True,
        "prior_receiver_launchd_reconnect_observed":True,
        "ssh_client_authenticated_to_receiver":False,
        "encrypted_financial_backup_captured":False,
        "offhost_ciphertext_receipt_verified":False,
        "same_capture_independently_restored":False,
        "global_financial_writer_quiescence_proved":False,
        "formal_c06_gate_accepted":False,
        "formal_c07_gate_accepted":False,
        "financial_release_authorized":False,
        "production_modified":False,
    }

def read_enrollment():
    need(not ENROLLMENT.is_symlink() and ENROLLMENT.is_absolute(),
         "C06_ENROLLMENT_UNSAFE_PATH")
    st=ENROLLMENT.stat()
    need(st.st_uid==0 and st.st_nlink==1 and stat.S_ISREG(st.st_mode)
         and stat.S_IMODE(st.st_mode)==0o600
         and 0<st.st_size<MAX_BYTES,
         "C06_ENROLLMENT_PRIVATE_MODE_OR_OWNER_CHANGED")
    raw=ENROLLMENT.read_bytes()
    need(len(raw)==st.st_size and hex_digest(raw)==ENROLLMENT_SHA256,
         "C06_ENROLLMENT_CHANGED_DURING_READ")
    return raw

def probe():
    need(os.geteuid()==0 and sys.platform=="linux" and
         socket.gethostname()==HOST,"C06_ROOT_ON_EXACT_HEL1_REQUIRED")
    raw=read_enrollment()
    with socket.socket() as sock:
        sock.settimeout(3)
        sock.connect(("127.0.0.1",PORT))
        banner=sock.recv(256)
    proc=subprocess.run(["/usr/bin/ssh-keyscan","-T","5","-p",str(PORT),
                         "-t","ed25519","127.0.0.1"],
                        capture_output=True,text=True,timeout=8)
    need(proc.returncode==0 and len(proc.stdout.encode())<MAX_BYTES,
         "C06_LIVE_HOST_KEY_SCAN_FAILED")
    return verify(raw,banner,proc.stdout)

def main():
    try:
        print(json.dumps(probe(),sort_keys=True))
        return 3
    except (Hold,OSError,UnicodeError,subprocess.SubprocessError,
            ConnectionError) as exc:
        why=str(exc) if isinstance(exc,Hold) else "C06_HOST_IDENTITY_OBSERVATION_UNAVAILABLE"
        print(json.dumps({"schema":SCHEMA,"status":"STOP","reason":why,
                          "formal_c06_gate_accepted":False,
                          "formal_c07_gate_accepted":False,
                          "financial_release_authorized":False,
                          "production_modified":False},sort_keys=True))
        return 2

if __name__=="__main__":
    sys.exit(main())

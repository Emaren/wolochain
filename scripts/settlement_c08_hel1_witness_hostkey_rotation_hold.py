#!/usr/bin/env python3
"""C08 HOLD: exact Intel SSH host-key pin repair, never maintenance authority.

Root-local operator-only controller. Replaces ONLY the C08 witness SSH
known_hosts file and its corresponding digest in the C08 private enrollment.
Never edits C03 fences, C06 tunnel, sshd, C01 services, signer keys, bank
records, nonce ledgers, owner enrollment, or real WOLO balances.

First independently verify current Intel Ed25519 host key against the M1
long-pinned LAN host and the separately enrolled Intel hardware identity.
A key from an unauthenticated scan alone is NOT sufficient.

--plan is read-only; --apply is explicitly gated, atomic per file with root
private preimages; --rollback recovers only an unchanged, exact postimage or
the identified partial state. An interrupted update remains FAIL CLOSED.
All successful results return exit 3/HOLD, never payment authorization.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile

SCHEMA="wolo.c08.hel1-ssh-hostkey-pin-only.v1"
ROOT=Path("/etc/wolochain-financial-maintenance/authority")
CONFIG_NAME="solo-runtime.json"
HOST_NAME="solo-witness-known-hosts"
OWNER_NAME="solo-owner.json"
BACKUP_NAME="c08-witness-hostkey-rotation-20261106"
EXPECTED_CONFIG_SHA="5fae8033a2c3d5e38e5e0a59369c9567d9c71caa09b8b92e5ad20add29b45299"
EXPECTED_OLD_KNOWN_SHA="31e23699e91c64698681631eeddc26db2c36eb24492ce861a047793a5f9e8b51"
EXPECTED_OLD_BLOB_SHA="45c6153f1a67b5585662aa072e03dde6b09ad607e030b40834262aa436687194"
EXPECTED_NEW_BLOB_SHA="d10e1e1ac631aa9584a780dc7105c3083f6b513c66d615bf09f59aca683ddea1"
EXPECTED_SOURCE="b35f294d619e6bf5d07b337cea46095f2eea9f76"
EXPECTED_KEY_PATTERN="[127.0.0.1]:22995"
KEY_PATTERN=re.compile(rb"ssh-ed25519\s+([A-Za-z0-9+/]+={0,2})(?:\s+[^\r\n]+)?\Z")
MAX_BYTES=131072
FINANCIAL_PORTS=re.compile(rb":(?:8094|8095)(?:\s|$)")


class Stop(ValueError):
    pass


def require(ok,code):
    if not ok:
        raise Stop(code)


def digest(raw: bytes)->str:
    return hashlib.sha256(raw).hexdigest()


def private_read(path:Path)->bytes:
    require(path.is_absolute() and ".." not in path.parts
            and not path.is_symlink(), "C08_PRIVATE_PIN_PATH_UNSAFE")
    try:
        fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|os.O_CLOEXEC)
        try:
            start=os.fstat(fd)
            require(stat.S_ISREG(start.st_mode) and start.st_uid==os.geteuid()
                    and stat.S_IMODE(start.st_mode)==0o600
                    and start.st_nlink==1 and 0<start.st_size<=MAX_BYTES,
                    "C08_PRIVATE_PIN_OWNER_OR_MODE_DRIFT")
            content=bytearray()
            while len(content)<=MAX_BYTES:
                piece=os.read(fd,min(65536,MAX_BYTES+1-len(content)))
                if not piece:
                    break
                content.extend(piece)
            end=os.fstat(fd)
            fields=("st_dev","st_ino","st_mode","st_uid","st_size",
                    "st_mtime_ns","st_ctime_ns","st_nlink")
            require(len(content)==start.st_size and all(
                    getattr(start,k)==getattr(end,k) for k in fields),
                    "C08_PIN_CHANGED_DURING_READ")
            return bytes(content)
        finally:
            os.close(fd)
    except OSError:
        raise Stop("C08_PROTECTED_PIN_UNAVAILABLE") from None


def dict_unique(pairs):
    d={}
    for key,value in pairs:
        require(key not in d,"C08_DUPLICATE_ENROLLMENT_JSON_KEY")
        d[key]=value
    return d


def no_constant(_):
    raise Stop("C08_NONCANONICAL_JSON_NUMBER")


def parse_config(raw:bytes):
    try:
        d=json.loads(raw.decode("utf-8","strict"),
                     object_pairs_hook=dict_unique,
                     parse_constant=no_constant)
    except (ValueError,UnicodeError,RecursionError):
        raise Stop("C08_ENROLLMENT_JSON_UNREADABLE") from None
    require(type(d) is dict and d.get("schema")==
            "wolo.solo-maintenance-runtime-enrollment.v1"
            and d.get("source_commit")==EXPECTED_SOURCE
            and type(d.get("controller_files")) is dict
            and len(d["controller_files"])==6,
            "C08_WITNESS_SOURCE_BINDING_DRIFT")
    w=d.get("witness")
    require(type(w) is dict and w.get("host")=="127.0.0.1"
            and type(w.get("port")) is int and w.get("port")==22995
            and w.get("user")=="tonyblum"
            and w.get("known_hosts_path")==str(ROOT/HOST_NAME)
            and type(w.get("known_hosts_sha256")) is str,
            "C08_WITNESS_HOST_SCOPE_DRIFT")
    return d


def key_from_pub(raw:bytes)->bytes:
    require(len(raw)<=2048 and b"\x00" not in raw and b"\r" not in raw,
            "C08_NEW_INTEL_KEY_FORMAT_INVALID")
    parts=raw.strip().split()
    require(len(parts) in (2,3) and parts[0]==b"ssh-ed25519",
            "C08_NEW_INTEL_KEY_TYPE_INVALID")
    blob=parts[1]
    require(digest(blob)==EXPECTED_NEW_BLOB_SHA,
            "C08_NEW_INTEL_KEY_NOT_TWO_WAY_VERIFIED")
    try:
        decoded=base64.b64decode(blob,validate=True)
    except ValueError:
        raise Stop("C08_NEW_INTEL_KEY_BASE64_INVALID") from None
    require(len(decoded)>36 and decoded.startswith(b"\x00\x00\x00\x0bssh-ed25519"),
            "C08_NEW_INTEL_KEY_WIRE_FORMAT_INVALID")
    return (EXPECTED_KEY_PATTERN+" ssh-ed25519 "+blob.decode("ascii")+"\n").encode("ascii")


def original_key_valid(raw:bytes):
    rows=raw.strip().splitlines()
    require(len(rows)==1 and b"\r" not in raw and b"\x00" not in raw,
            "C08_OLD_KNOWN_HOSTS_SCOPE_DRIFT")
    parts=rows[0].split()
    require(len(parts)==3 and parts[0].decode("ascii")==EXPECTED_KEY_PATTERN
            and parts[1]==b"ssh-ed25519"
            and digest(parts[2])==EXPECTED_OLD_BLOB_SHA,
            "C08_OLD_HOST_KEY_NOT_SOURCE_PINNED")


def current_state(root:Path,new_host_raw:bytes):
    require(root.is_absolute() and root.is_dir() and not root.is_symlink()
            and root.lstat().st_uid==os.geteuid()
            and stat.S_IMODE(root.lstat().st_mode)==0o700,
            "C08_ROOT_AUTHORITY_DIRECTORY_DRIFT")
    old_cfg=private_read(root/CONFIG_NAME)
    old_host=private_read(root/HOST_NAME)
    owner=private_read(root/OWNER_NAME)
    require(digest(old_cfg)==EXPECTED_CONFIG_SHA
            and digest(old_host)==EXPECTED_OLD_KNOWN_SHA,
            "C08_ORIGINAL_PROTECTED_STATE_DRIFT")
    original_key_valid(old_host)
    cfg=parse_config(old_cfg)
    require(cfg["witness"]["known_hosts_sha256"]==EXPECTED_OLD_KNOWN_SHA
            and digest(owner)==cfg.get("owner_enrollment_sha256"),
            "C08_OWNER_OR_HOST_PIN_DRIFT")
    new_key=key_from_pub(new_host_raw)
    new_cfg=json.loads(old_cfg,object_pairs_hook=dict_unique)
    new_cfg["witness"]["known_hosts_sha256"]=digest(new_key)
    new_cfg_raw=(json.dumps(new_cfg,sort_keys=True,separators=(",",":"),
                            ensure_ascii=True)+"\n").encode()
    require(parse_config(new_cfg_raw)["witness"]["known_hosts_sha256"]==digest(new_key),
            "C08_NEW_CONFIG_BINDING_INCOMPLETE")
    return old_cfg,old_host,new_cfg_raw,new_key


def financial_ports_absent():
    p=subprocess.run(["/usr/bin/ss","-ltnH"],capture_output=True,
                     check=False,timeout=5)
    require(p.returncode==0 and len(p.stdout)<131072
            and not FINANCIAL_PORTS.search(p.stdout),
            "C08_FINANCIAL_LISTENER_PRESENT_OR_UNAVAILABLE")


def fsync_dir(path:Path):
    fd=os.open(path,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:os.fsync(fd)
    finally:os.close(fd)


def create_backup(root:Path,cfg:bytes,host:bytes):
    folder=root/BACKUP_NAME
    require(not folder.exists() and not folder.is_symlink(),
            "C08_PROTECTED_BACKUP_ALREADY_EXISTS")
    folder.mkdir(mode=0o700)
    require(folder.lstat().st_uid==os.geteuid() and
            stat.S_IMODE(folder.lstat().st_mode)==0o700,
            "C08_BACKUP_DIRECTORY_MODE_DRIFT")
    for name,raw in ((CONFIG_NAME+".before",cfg),(HOST_NAME+".before",host)):
        f=folder/name
        fd=os.open(f,os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_WRONLY,0o600)
        with os.fdopen(fd,"wb") as out:
            out.write(raw)
            out.flush()
            os.fsync(out.fileno())
        require(private_read(f)==raw,"C08_PROTECTED_BACKUP_MISMATCH")
    fsync_dir(folder)
    fsync_dir(root)
    return folder


def replace_if_exact(path:Path,expected:bytes,new:bytes):
    require(private_read(path)==expected,
            "C08_PIN_FILE_CHANGED_BEFORE_REPLACE")
    fd,temp=tempfile.mkstemp(prefix=".c08-witness-pin-",dir=str(path.parent))
    try:
        with os.fdopen(fd,"wb") as f:
            os.fchmod(f.fileno(),0o600)
            f.write(new)
            f.flush()
            os.fsync(f.fileno())
        require(private_read(path)==expected,
                "C08_PIN_CHANGED_DURING_REPLACEMENT")
        os.replace(temp,path)
        fsync_dir(path.parent)
        require(private_read(path)==new,
                "C08_PIN_POSTWRITE_MISMATCH")
    finally:
        if os.path.exists(temp):os.unlink(temp)


def result(status,oldcfg,oldhost,newcfg,newhost):
    return {"schema":SCHEMA,"status":status,
            "old_host_sha256":digest(oldhost),
            "new_host_sha256":digest(newhost),
            "old_enrollment_sha256":digest(oldcfg),
            "new_enrollment_sha256":digest(newcfg),
            "only_c08_witness_hostkey_rotated":True,
            "owner_enrollment_changed":False,
            "witness_nonce_ledger_changed":False,
            "financial_release_authorized":False,
            "financial_services_started":False,
            "c08_gate_closed":False}


def operation(root, new_pub, mode):
    require(mode in ("plan","apply","rollback"),"C08_OPERATION_NOT_ALLOWED")
    financial_ports_absent()
    if mode=="rollback":
        folder=root/BACKUP_NAME
        require(folder.is_dir() and not folder.is_symlink() and
                stat.S_IMODE(folder.lstat().st_mode)==0o700,
                "C08_ROOT_ROLLBACK_BACKUP_UNAVAILABLE")
        old_cfg=private_read(folder/(CONFIG_NAME+".before"))
        old_host=private_read(folder/(HOST_NAME+".before"))
        require(digest(old_cfg)==EXPECTED_CONFIG_SHA and
                digest(old_host)==EXPECTED_OLD_KNOWN_SHA,
                "C08_ROLLBACK_PREIMAGES_NOT_EXACT")
        new_key=key_from_pub(new_pub)
        cfg=parse_config(old_cfg)
        cfg["witness"]["known_hosts_sha256"]=digest(new_key)
        new_cfg=(json.dumps(cfg,sort_keys=True,separators=(",",":"),
                            ensure_ascii=True)+"\n").encode()
        current_cfg=private_read(root/CONFIG_NAME)
        current_host=private_read(root/HOST_NAME)
        require(current_cfg in (old_cfg,new_cfg) and
                current_host in (old_host,new_key),
                "C08_CANNOT_ROLLBACK_CONCURRENT_OPERATOR_CHANGE")
        if current_cfg!=old_cfg:
            replace_if_exact(root/CONFIG_NAME,new_cfg,old_cfg)
        if current_host!=old_host:
            replace_if_exact(root/HOST_NAME,new_key,old_host)
        require(private_read(root/CONFIG_NAME)==old_cfg and
                private_read(root/HOST_NAME)==old_host,
                "C08_ROLLBACK_VERIFICATION_FAILED")
        financial_ports_absent()
        return result("HOLD_SOURCE_PIN_ROLLED_BACK",old_cfg,old_host,new_cfg,new_key)
    old_cfg,old_host,new_cfg,new_host=current_state(root,new_pub)
    if mode=="plan":
        return result("HOLD_NEW_INTEL_PIN_PLAN_ONLY",old_cfg,old_host,new_cfg,new_host)
    create_backup(root,old_cfg,old_host)
    # The first replacement is deliberately nonauthorizing until the matched
    # config is installed; any partial state refuses future source checks.
    replace_if_exact(root/HOST_NAME,old_host,new_host)
    replace_if_exact(root/CONFIG_NAME,old_cfg,new_cfg)
    require(private_read(root/HOST_NAME)==new_host and
            private_read(root/CONFIG_NAME)==new_cfg,
            "C08_NEW_WITNESS_PIN_INCOMPLETE")
    financial_ports_absent()
    return result("HOLD_HOST_KEY_ROTATED_NO_AUTHORITY",old_cfg,old_host,new_cfg,new_host)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode",choices=("plan","apply","rollback"),required=True)
    parser.add_argument("--intel-public-key-file",type=Path,required=True)
    args=parser.parse_args(argv)
    try:
        require(os.geteuid()==0,"C08_ROOT_ONLY_OPERATOR_REPAIR")
        new_pub=private_read(args.intel_public_key_file)
        report=operation(ROOT,new_pub,args.mode)
    except (Stop,KeyError,ValueError,UnicodeError,OSError,
            subprocess.SubprocessError,subprocess.TimeoutExpired):
        print(json.dumps({"schema":SCHEMA,"status":"STOP",
                          "reason":"C08_PRIVATE_HOSTKEY_ROTATION_UNAVAILABLE",
                          "financial_release_authorized":False},sort_keys=True))
        return 2
    print(json.dumps(report,sort_keys=True))
    return 3


if __name__=="__main__":
    sys.exit(main())

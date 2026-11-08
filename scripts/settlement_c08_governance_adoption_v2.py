#!/usr/bin/env python3
"""C08 one-human governance ADOPTION, never a WOLO transaction permit.

Unlike C08 intent-HOLD checkers, successful owner-authorized adoption commits
an immutable versioned policy on the owner device. No Satchel activation, owner
funding permission, SQL mutations, native RPC, or legacy 8092 fallback.

Modes:
  prepare: create a short-lived, exact-source owner adoption request (no signing)
  sign: owner-local interactive OpenSSL Ed25519 signature from encrypted PEM
  adopt: authenticate signed request + mature public notice; atomically adopt
  status: validate adopted receipt against original public signing proof

An adopted policy has funded allowance ZERO until a *separate* C09 exact permit.
"""
from __future__ import annotations

import argparse
import base64
import binascii
from datetime import datetime, timedelta, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile

import settlement_solo_owner_public_notice_hold as notice

CHAIN="wolo-1"
POLICY_PATH="docs/settlement-contracts/solo-owner-governance-adoption-v2.json"
POLICY_SHA="602f1078a2979d7f467e2ac4e055f6364bff8c4baf8d111fb1e10a227eb86e03"
OWNER_DER_SHA="00d08c27271cf484f684059e83478d9522765c374101d5c4e8ed29e266e500ed"
VERSION=2
POLICY_SCHEMA="wolo.c08.solo-owner-financial-governance-policy.v2"
REQUEST_SCHEMA="wolo.c08.governance-adoption-request.v2"
PACKET_SCHEMA="wolo.c08.governance-adoption-signed-packet.v2"
RECEIPT_SCHEMA="wolo.c08.governance-policy-adopted-owner-signed.v2"
DOMAIN=b"AOE2WAR-WOLO-C08-REAL-GOVERNANCE-ADOPTION-V2\x00"
HEX40=re.compile(r"[a-f0-9]{40}\Z")
HEX32=re.compile(r"[a-f0-9]{32}\Z")
HEX64=re.compile(r"[a-f0-9]{64}\Z")
UTC=re.compile(r"20[0-9]{2}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z\Z")
REQUEST_KEYS=frozenset({
    "schema","chain_id","policy_version","source_commit",
    "policy_sha256","owner_der_sha256","notice_body_sha256",
    "notice_url","owner_human_count","independent_human_review_claimed",
    "legacy_8092_fallback_allowed","historical_claims_waived",
    "initial_funded_allowance_uwolo","c09_transaction_signature_present",
    "adoption_is_transaction_permit","nonce","not_before","expires_at"
})
PACKET_KEYS=frozenset({"schema","request","signature_b64"})
RECEIPT_KEYS=frozenset({
    "schema","status","source_commit","policy_sha256","owner_der_sha256",
    "request_sha256","signed_packet_sha256","signed_packet",
    "nonce_sha256","public_notice_uri","adopted_utc","funded_allowance_uwolo",
    "financial_release_authorized","c09_transaction_permit_present",
    "centralized_one_human_disclosed","independent_human_review_claimed"
})

class Hold(ValueError):pass

def require(ok,reason):
    if not ok:raise Hold(reason)

def canonical(obj):
    return json.dumps(obj,sort_keys=True,separators=(",",":"),ensure_ascii=True).encode("ascii")

def unique(pairs):
    result={}
    for key,val in pairs:
        require(key not in result,"DUPLICATE_JSON_FIELD")
        result[key]=val
    return result

def strict(raw,maxlen=32768):
    require(type(raw) is bytes and 1<len(raw)<maxlen,"JSON_LENGTH_INVALID")
    try:
        return json.loads(raw,object_pairs_hook=unique,
            parse_float=lambda _:require(False,"FLOAT_FORBIDDEN"),
            parse_constant=lambda _:require(False,"NONFINITE_FORBIDDEN"))
    except (ValueError,UnicodeError,RecursionError) as exc:
        raise Hold("INVALID_JSON") from exc

def utc(s):
    require(type(s) is str and UTC.fullmatch(s) is not None,"UTC_REQUIRED")
    try:return datetime.strptime(s,"%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError as exc:raise Hold("UTC_INVALID") from exc

def stamp(t):
    return t.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def safe_owner_root(root,create=False):
    p=Path(root).expanduser().absolute()
    if create and not p.exists():
        p.mkdir(mode=0o700,parents=False)
    s=p.lstat()
    require(stat.S_ISDIR(s.st_mode) and not p.is_symlink()
       and s.st_uid==os.geteuid() and stat.S_IMODE(s.st_mode)==0o700,
       "C08_OWNER_PRIVATE_DIR_UNSAFE")
    return p

def read_private(path):
    p=Path(path).absolute()
    safe_owner_root(p.parent)
    fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        info=os.fstat(fd)
        require(stat.S_ISREG(info.st_mode) and info.st_uid==os.geteuid()
          and info.st_nlink==1 and stat.S_IMODE(info.st_mode)==0o600
          and 0<info.st_size<32768,"C08_PRIVATE_FILE_UNSAFE")
        raw=os.read(fd,32768)
        require(len(raw)==info.st_size and os.fstat(fd).st_mtime_ns==info.st_mtime_ns,
                "C08_PRIVATE_FILE_DRIFT")
        return raw
    finally:os.close(fd)

def write_private(path,raw):
    path=Path(path)
    safe_owner_root(path.parent)
    require(type(raw) is bytes and len(raw)<32768,"C08_WRITE_LENGTH_INVALID")
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,"wb") as stream:
        stream.write(raw);stream.flush();os.fsync(stream.fileno())

def checked_program(args,input_data=None,timeout=9):
    result=subprocess.run(args,input=input_data,capture_output=True,timeout=timeout)
    require(result.returncode==0,"C08_CRYPTO_OR_PROVENANCE_FAILED")
    return result.stdout

def public_der_hash(public_pem):
    require(type(public_pem) is bytes and
            public_pem.startswith(b"-----BEGIN PUBLIC KEY-----\n")
            and public_pem.rstrip().endswith(b"-----END PUBLIC KEY-----")
            and len(public_pem)<2048,"C08_OWNER_PEM_INVALID")
    der=checked_program(["openssl","pkey","-pubin","-inform","PEM","-outform","DER"],
                        input_data=public_pem)
    return sha(der)

def verify_signed(message,signature,pem):
    require(len(signature)==64,"C08_OWNER_ED25519_SIGNATURE_LENGTH")
    with tempfile.TemporaryDirectory(prefix="wolo-c08-adoption-verify-") as folder:
        f=Path(folder)
        for name,raw in (("m",message),("s",signature),("public.pem",pem)):
            p=f/name;p.write_bytes(raw);p.chmod(0o600)
        checked_program(["openssl","pkeyutl","-verify","-pubin","-rawin",
            "-inkey",str(f/"public.pem"),"-in",str(f/"m"),
            "-sigfile",str(f/"s")])

def load_policy(repo):
    raw=(Path(repo)/POLICY_PATH).read_bytes()
    require(sha(raw)==POLICY_SHA,"C08_IMPLEMENTED_POLICY_SHA_CHANGED")
    obj=strict(raw)
    require(type(obj) is dict and obj.get("schema")==POLICY_SCHEMA
            and obj.get("chain_id")==CHAIN and obj.get("policy_version")==VERSION
            and obj.get("governance_mode")=="one_human_centralized"
            and obj.get("human_operator_count")==1
            and obj.get("independent_human_review_claimed") is False
            and obj.get("legacy_8092_fallback_allowed") is False
            and obj.get("old_unknown_claims_deleted_or_waived") is False
            and obj.get("unknown_transaction_rebroadcast_allowed") is False
            and obj.get("initial_funded_allowance_uwolo")==0
            and obj.get("first_funded_canary_limit_uwolo")==0
            and obj.get("policy_adoption_is_not_permission_to_fund") is True
            and obj.get("require_fresh_exact_c09_owner_transaction_signature") is True
            and obj.get("require_offhost_one_use_transaction_nonce") is True
            and obj.get("public_notice_url")==notice.ISSUE_URL
            and obj.get("public_notice_minimum_seconds")==86400,
            "C08_GOVERNANCE_POLICY_SCOPE_INVALID")
    return raw

def source_commit(repo,ref=None):
    root=Path(repo)
    if ref is None:
        commit=checked_program(["git","-C",str(root),"rev-parse","HEAD"]).decode().strip()
        status=checked_program(["git","-C",str(root),"status","--porcelain",
            "--",POLICY_PATH,"scripts/settlement_c08_governance_adoption_v2.py"])
        require(not status.strip(),"C08_LOCAL_SOURCE_UNCOMMITTED")
    else:
        require(type(ref) is str and HEX40.fullmatch(ref) is not None,
                "C08_SOURCE_REFERENCE_INVALID")
        commit=ref
    require(HEX40.fullmatch(commit) is not None,"C08_SOURCE_UNPINNED")
    kind=checked_program(["git","-C",str(root),"cat-file","-t",commit]).decode().strip()
    require(kind=="commit","C08_SOURCE_NOT_GIT_COMMIT")
    object_bytes=checked_program(["git","-C",str(root),"show",commit+":"+POLICY_PATH])
    require(sha(object_bytes)==POLICY_SHA,"C08_SOURCE_OBJECT_NOT_AUTHENTICATED")
    # The adopted policy is pinned to the *actual implementation* as well,
    # not merely a policy JSON copied into an unrelated source tree.
    implementation="scripts/settlement_c08_governance_adoption_v2.py"
    impl=checked_program(["git","-C",str(root),"show",commit+":"+implementation])
    require(sha(impl)==sha((Path(__file__)).read_bytes()),
            "C08_POLICY_ADOPTION_EXECUTABLE_SOURCE_DRIFT")
    return commit

def validate_request(q,now,commit):
    require(type(q) is dict and set(q)==REQUEST_KEYS
        and q["schema"]==REQUEST_SCHEMA and q["chain_id"]==CHAIN
        and type(q["policy_version"]) is int and q["policy_version"]==VERSION
        and type(q["source_commit"]) is str and
        HEX40.fullmatch(q["source_commit"]) is not None
        and q["source_commit"]==commit
        and q["policy_sha256"]==POLICY_SHA
        and q["owner_der_sha256"]==OWNER_DER_SHA
        and q["notice_body_sha256"]==notice.EXACT_PUBLIC_BODY_SHA256
        and q["notice_url"]==notice.ISSUE_URL,
        "C08_SIGNED_SOURCE_OR_NOTICE_IDENTITY_DRIFT")
    exact={
        "owner_human_count":1,
        "independent_human_review_claimed":False,
        "legacy_8092_fallback_allowed":False,
        "historical_claims_waived":False,
        "initial_funded_allowance_uwolo":0,
        "c09_transaction_signature_present":False,
        "adoption_is_transaction_permit":False
    }
    for name,expected in exact.items():
        require(type(q[name]) is type(expected) and q[name]==expected,
            "C08_SIGNED_GOVERNANCE_SCOPE_INVALID")
    require(type(q["nonce"]) is str and HEX32.fullmatch(q["nonce"]) is not None
            and q["nonce"]!="0"*32,"C08_ADOPTION_NONCE_INVALID")
    begin,expires=utc(q["not_before"]),utc(q["expires_at"])
    require(begin<=now<expires and
            timedelta()<expires-begin<=timedelta(minutes=30),
            "C08_OWNER_ADOPTION_SIGNATURE_WINDOW_INVALID")

def signed_request(q):
    return DOMAIN+canonical(q)

def packet_sign_payload(q):
    return signed_request(q)

def prepare_request(*,repo,pem,now=None,nonce=None):
    t=now or datetime.now(timezone.utc)
    load_policy(repo);commit=source_commit(repo)
    require(public_der_hash(pem)==OWNER_DER_SHA,
            "C08_HISTORICAL_OWNER_DER_TRUST_ANCHOR_DIFFERENT")
    q={
        "schema":REQUEST_SCHEMA,"chain_id":CHAIN,"policy_version":VERSION,
        "source_commit":commit,"policy_sha256":POLICY_SHA,
        "owner_der_sha256":OWNER_DER_SHA,
        "notice_body_sha256":notice.EXACT_PUBLIC_BODY_SHA256,
        "notice_url":notice.ISSUE_URL,
        "owner_human_count":1,"independent_human_review_claimed":False,
        "legacy_8092_fallback_allowed":False,"historical_claims_waived":False,
        "initial_funded_allowance_uwolo":0,
        "c09_transaction_signature_present":False,
        "adoption_is_transaction_permit":False,
        "nonce":nonce or os.urandom(16).hex(),
        "not_before":stamp(t-timedelta(seconds=5)),
        "expires_at":stamp(t+timedelta(minutes=20))}
    validate_request(q,t,commit)
    return q

def sign_packet(request,owner_pem,encrypted_private_path,*,now,commit):
    validate_request(request,now,commit)
    require(public_der_hash(owner_pem)==OWNER_DER_SHA,
            "C08_OWNER_DER_WRONG")
    encrypted_private=Path(encrypted_private_path).expanduser().absolute()
    safe_owner_root(encrypted_private.parent)
    info=encrypted_private.lstat()
    require(stat.S_ISREG(info.st_mode) and info.st_uid==os.geteuid()
            and stat.S_IMODE(info.st_mode)==0o600
            and info.st_nlink==1 and info.st_size<8192,
            "C08_ENCRYPTED_PRIVATE_KEY_PATH_UNSAFE")
    with encrypted_private.open("rb") as private_stream:
        require(private_stream.readline(128)==
                b"-----BEGIN ENCRYPTED PRIVATE KEY-----\n",
                "C08_UNENCRYPTED_OWNER_PRIVATE_KEY_FORBIDDEN")
    message=signed_request(request)
    with tempfile.TemporaryDirectory(prefix="wolo-c08-owner-sign-") as tmp:
        m=Path(tmp)/"message"
        m.write_bytes(message);m.chmod(0o600)
        # No passphrase in CLI/env/logs. OpenSSL prompts owner at local TTY.
        # Input and stdout never include raw private key material.
        result=subprocess.run(["openssl","pkeyutl","-sign","-rawin",
            "-inkey",str(encrypted_private),"-in",str(m)],
            stdout=subprocess.PIPE,check=False,timeout=90)
        require(result.returncode==0 and len(result.stdout)==64,
                "C08_OWNER_INTERACTIVE_SIGNING_FAILED")
        signature=result.stdout
    verify_signed(message,signature,owner_pem)
    return {"schema":PACKET_SCHEMA,"request":request,
            "signature_b64":base64.b64encode(signature).decode("ascii")}

def verify_packet(*,packet_raw,public_pem,repo,now=None,notice_issue=None,notice_repo=None):
    t=now or datetime.now(timezone.utc)
    load_policy(repo)
    p=strict(packet_raw)
    require(type(p) is dict and set(p)==PACKET_KEYS
        and p["schema"]==PACKET_SCHEMA and type(p.get("request")) is dict,
        "C08_SIGNED_PACKET_SCHEMA_DRIFT")
    commit=source_commit(repo,ref=p["request"].get("source_commit"))
    require(public_der_hash(public_pem)==OWNER_DER_SHA,
            "C08_OWNER_KEY_ANCHOR_UNTRUSTED")
    q=p["request"]
    validate_request(q,t,commit)
    try:
        signature=base64.b64decode(p["signature_b64"],validate=True)
    except (ValueError,binascii.Error,TypeError) as exc:
        raise Hold("C08_SIGNATURE_ENCODING_INVALID") from exc
    verify_signed(signed_request(q),signature,public_pem)
    if notice_issue is None or notice_repo is None:
        notice_issue,notice_repo=notice.live_fetch()
    n=notice.inspect_notice(notice_issue,notice_repo,now=t)
    require(n["status"]=="PASS_NOTICE_TIME_ONLY_ALL_FINANCIAL_GATES_HOLD",
            "C08_PUBLIC_24H_NOTICE_NOT_MATURE")
    return p

def adopt(*,packet_raw,public_pem,repo,root,now=None,
          notice_issue=None,notice_repo=None):
    t=now or datetime.now(timezone.utc)
    p=verify_packet(packet_raw=packet_raw,public_pem=public_pem,repo=repo,
       now=t,notice_issue=notice_issue,notice_repo=notice_repo)
    q=p["request"]
    root=safe_owner_root(root)
    lock=root/"adoption-v2.lock"
    fd=os.open(lock,os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
    try:
        info=os.fstat(fd)
        require(stat.S_ISREG(info.st_mode) and info.st_uid==os.geteuid()
                and stat.S_IMODE(info.st_mode)==0o600,
                "C08_ADOPTION_LOCK_UNSAFE")
        fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        receipt_path=root/"adopted-governance-v2.json"
        require(not receipt_path.exists() and not receipt_path.is_symlink(),
                "C08_ADOPTION_ALREADY_EXISTS_NO_REPLAY")
        receipt={
            "schema":RECEIPT_SCHEMA,
            "status":"PASS_C08_OWNER_GOVERNANCE_POLICY_ADOPTED_NO_FUNDS",
            "source_commit":q["source_commit"],
            "policy_sha256":POLICY_SHA,
            "owner_der_sha256":OWNER_DER_SHA,
            "request_sha256":sha(canonical(q)),
            "signed_packet_sha256":sha(canonical(p)),
            "signed_packet":p,
            "nonce_sha256":sha(q["nonce"].encode("ascii")),
            "public_notice_uri":notice.ISSUE_URL,
            "adopted_utc":stamp(t),
            "funded_allowance_uwolo":0,
            "financial_release_authorized":False,
            "c09_transaction_permit_present":False,
            "centralized_one_human_disclosed":True,
            "independent_human_review_claimed":False
        }
        require(set(receipt)==RECEIPT_KEYS,"C08_ADOPTION_RECEIPT_SCHEMA_CHANGED")
        write_private(receipt_path,canonical(receipt)+b"\n")
        return receipt,sha((canonical(receipt)+b"\n"))
    finally:os.close(fd)

def inspect_adoption(*,root,public_pem,repo,notice_issue=None,notice_repo=None):
    folder=safe_owner_root(root)
    raw=read_private(folder/"adopted-governance-v2.json")
    receipt=strict(raw)
    require(type(receipt) is dict and set(receipt)==RECEIPT_KEYS
           and receipt["schema"]==RECEIPT_SCHEMA
           and receipt["status"]=="PASS_C08_OWNER_GOVERNANCE_POLICY_ADOPTED_NO_FUNDS"
           and receipt["financial_release_authorized"] is False
           and receipt["funded_allowance_uwolo"]==0
           and receipt["c09_transaction_permit_present"] is False
           and receipt["centralized_one_human_disclosed"] is True
           and receipt["independent_human_review_claimed"] is False,
           "C08_ADOPTED_RECEIPT_SCOPE_NOT_VALID")
    q=receipt["signed_packet"]["request"]
    # Historic adoption remains valid after its short-lived signing interval;
    # validate using exact recorded adoption time, not current time.
    at=utc(receipt["adopted_utc"])
    p=verify_packet(packet_raw=canonical(receipt["signed_packet"]),
       public_pem=public_pem,repo=repo,now=at,
       notice_issue=notice_issue,notice_repo=notice_repo)
    require(receipt["request_sha256"]==sha(canonical(q))
        and receipt["signed_packet_sha256"]==sha(canonical(p))
        and receipt["nonce_sha256"]==sha(q["nonce"].encode())
        and receipt["source_commit"]==q["source_commit"]
        and receipt["policy_sha256"]==POLICY_SHA
        and receipt["owner_der_sha256"]==OWNER_DER_SHA
        and receipt["public_notice_uri"]==notice.ISSUE_URL,
        "C08_ADOPTED_RECEIPT_SIGNATURE_OR_LINEAGE_DRIFT")
    return {"status":"PASS_C08_GOVERNANCE_ADOPTION_PROOF_VERIFIED",
       "source_commit":receipt["source_commit"],"receipt_sha256":sha(raw),
       "funded_allowance_uwolo":0,"financial_release_authorized":False}

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode",choices=("prepare","sign","adopt","status"))
    parser.add_argument("--repo",type=Path,default=Path(__file__).resolve().parents[1])
    parser.add_argument("--root",type=Path,required=True)
    parser.add_argument("--public-key",type=Path,required=True)
    parser.add_argument("--encrypted-private-key",type=Path)
    a=parser.parse_args(argv)
    try:
        root=safe_owner_root(a.root,create=True)
        public=read_private(a.public_key)
        now=datetime.now(timezone.utc)
        if a.mode=="prepare":
            q=prepare_request(repo=a.repo,pem=public,now=now)
            write_private(root/"request-v2.json",canonical(q)+b"\n")
            out={"status":"PASS_C08_REQUEST_PREPARED_OWNER_SIGNATURE_REQUIRED",
                 "request_sha256":sha(canonical(q)),"expires_at":q["expires_at"],
                 "financial_release_authorized":False}
        elif a.mode=="sign":
            require(a.encrypted_private_key is not None,
                "C08_OWNER_ENCRYPTED_KEY_ARGUMENT_REQUIRED")
            q=strict(read_private(root/"request-v2.json"))
            commit=source_commit(a.repo)
            packet=sign_packet(q,public,a.encrypted_private_key,
                               now=now,commit=commit)
            write_private(root/"signed-packet-v2.json",canonical(packet)+b"\n")
            out={"status":"PASS_C08_OWNER_SIGNED_ADOPTION_PACKET_READY",
                 "signed_packet_sha256":sha(canonical(packet)),
                 "financial_release_authorized":False}
        elif a.mode=="adopt":
            receipt,digest=adopt(packet_raw=read_private(root/"signed-packet-v2.json"),
                public_pem=public,repo=a.repo,root=root,now=now)
            out={"status":receipt["status"],"receipt_sha256":digest,
                 "governance_policy_adopted":True,
                 "financial_release_authorized":False}
        else:
            out=inspect_adoption(root=root,public_pem=public,repo=a.repo)
        print(json.dumps(out,sort_keys=True))
        return 0
    except (Hold,notice.NoticeStop,OSError,subprocess.SubprocessError,
            ValueError,KeyError,TypeError,RuntimeError) as exc:
        print(json.dumps({"status":"HOLD_C08_ADOPTION_NOT_ACCEPTED",
         "reason":str(exc)[:90] if isinstance(exc,Hold) else "C08_UNVERIFIED",
         "financial_release_authorized":False},sort_keys=True))
        return 3

if __name__=="__main__":sys.exit(main())

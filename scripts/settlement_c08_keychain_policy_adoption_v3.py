#!/usr/bin/env python3
"""Owner-authorized noninteractive C08 policy-only Keychain adoption, NO FUNDS.

This is a NEW independently enrolled macOS login-Keychain SOFTWARE P-256 key,
NOT the prior encrypted Ed25519 key and NOT Secure Enclave attestation.
C08 adoption allows zero WOLO transfers. C09 must require separately verified,
transaction-specific owner approval, financial gates and independent bank proof.
"""
from __future__ import annotations

import argparse
import base64
import binascii
from datetime import datetime,timezone,timedelta
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

import settlement_c08_governance_adoption_v2 as old
import settlement_solo_owner_public_notice_hold as notice

SCHEMA="wolo.c08.one-human-keychain-p256-governance-adoption.v3"
REQUEST_SCHEMA="wolo.c08.keychain-p256-policy-request.v3"
PACKET_SCHEMA="wolo.c08.keychain-p256-signed-adoption.v3"
RECEIPT_SCHEMA="wolo.c08.keychain-p256-adopted-policy.v3"
DOMAIN=b"AOE2WAR-WOLO-C08-KEYCHAIN-GOVERNANCE-ADOPTION-V3\x00"
POLICY_SHA=old.POLICY_SHA
OWNER_X963_SHA="f9f76deb8ba61b8f4b4f8e5b434acc11fa95630ccb19306a71e8bff0dc6fb826"
HISTORICAL_ED25519_DER_SHA=old.OWNER_DER_SHA
KEY_COMMENT_ID=6727529299
KEY_COMMENT_SHA="bde91d30f97aaf53650122d33128790187a809b3760210a9e08822ece2395b48"
KEY_COMMENT_URL="https://api.github.com/repos/Emaren/wolochain/issues/comments/6727529299"
SOURCE_PY="scripts/settlement_c08_keychain_policy_adoption_v3.py"
SOURCE_SWIFT="scripts/c08_keychain_governance_v3.swift"
SOURCE_POL="docs/settlement-contracts/solo-owner-governance-adoption-v2.json"
PUB_FILE="public-owner-key-x963.bin"
RECEIPT_FILE="adopted-governance-v3.json"
HEX40=re.compile("[0-9a-f]{40}\\Z")
HEX32=re.compile("[0-9a-f]{32}\\Z")
REQUEST_KEYS=frozenset({
    "schema","chain_id","operation","source_commit",
    "policy_sha256","owner_public_x963_sha256",
    "historical_ed25519_der_sha256","historical_owner_key_signed_this_request",
    "key_enrollment_comment_id","key_enrollment_comment_body_sha256",
    "public_notice_url","public_notice_body_sha256","owner_human_count",
    "independent_human_review_claimed","legacy_8092_fallback_allowed",
    "historical_claims_waived","financial_release_authorized",
    "standing_funded_allowance_uwolo","future_c09_canary_ceiling_uwolo",
    "c09_transaction_signature_present","nonce","not_before","expires_at"
})
PACKET_KEYS=frozenset({"schema","request","signature_der_b64"})
RECEIPT_KEYS=frozenset({
    "schema","status","source_commit","policy_sha256",
    "owner_public_x963_sha256","signed_packet","signed_packet_sha256",
    "adopted_utc","public_notice_url","key_enrollment_comment_id",
    "historic_ed25519_key_not_used","login_keychain_software_key_not_secure_enclave",
    "single_human_owner_disclosed","independent_human_review_claimed",
    "standing_funded_allowance_uwolo","future_c09_canary_ceiling_uwolo",
    "financial_release_authorized","c09_permit_issued"
})
SPKI=bytes.fromhex("3059301306072a8648ce3d020106082a8648ce3d030107034200")

class Hold(ValueError):
    pass

def need(ok,reason):
    if not ok:raise Hold(reason)

def sha(b):return hashlib.sha256(b).hexdigest()

def canonical(obj):return old.canonical(obj)

def strict(raw):return old.strict(raw)

def read_private(path):return old.read_private(path)

def write_private(path,raw):return old.write_private(path,raw)

def root_safe(root,create=False):return old.safe_owner_root(root,create=create)

def git_commit(repo,ref=None):
    repo=Path(repo)
    if ref is None:
        cp=subprocess.run(["git","-C",str(repo),"rev-parse","HEAD"],
            capture_output=True,text=True,timeout=8,check=True)
        ref=cp.stdout.strip()
        state=subprocess.run(["git","-C",str(repo),"status","--porcelain","--",
             SOURCE_PY,SOURCE_SWIFT,SOURCE_POL],
             capture_output=True,text=True,timeout=8,check=True)
        need(not state.stdout.strip(),"C08_V3_CURRENT_SOURCE_UNCOMMITTED")
    need(type(ref) is str and HEX40.fullmatch(ref) is not None,
         "C08_V3_SOURCE_REF_INVALID")
    verify=subprocess.run(["git","-C",str(repo),"cat-file","-t",ref],
         capture_output=True,text=True,timeout=8,check=True)
    need(verify.stdout.strip()=="commit","C08_V3_SOURCE_NOT_GIT_COMMIT")
    for filename in (SOURCE_PY,SOURCE_SWIFT,SOURCE_POL):
        disk=(repo/filename).read_bytes()
        source=subprocess.run(["git","-C",str(repo),"show",ref+":"+filename],
            capture_output=True,timeout=8,check=True)
        need(sha(source.stdout)==sha(disk),"C08_V3_SOURCE_OBJECT_DRIFT")
    need(sha((repo/SOURCE_POL).read_bytes())==POLICY_SHA,
         "C08_V3_POLICY_SOURCE_CHANGED")
    old.load_policy(repo)
    return ref

def key_public(raw):
    need(type(raw) is bytes and len(raw)==65 and raw[0]==4
         and sha(raw)==OWNER_X963_SHA,"C08_V3_PUBLIC_KEY_ANCHOR_CHANGED")
    return raw

def verify_ecdsa(message,signature,public):
    need(type(message) is bytes and message.startswith(DOMAIN)
          and 80<len(message)<8192,"C08_V3_SIGNED_MESSAGE_DOMAIN")
    need(type(signature) is bytes and 64<=len(signature)<=80
         and signature[:1]==bytes([0x30]),"C08_V3_ECDSA_SIGNATURE_ENCODING")
    pub=key_public(public)
    with tempfile.TemporaryDirectory(prefix="wolo-c08-p256-public-verify-") as folder:
        d=Path(folder)
        for name,raw in (("pub.der",SPKI+pub),("msg",message),
                         ("signature.der",signature)):
            file=d/name;file.write_bytes(raw);file.chmod(0o600)
        r=subprocess.run(["openssl","dgst","-sha256","-keyform","DER",
            "-verify",str(d/"pub.der"),"-signature",str(d/"signature.der"),
            str(d/"msg")],capture_output=True,timeout=8)
        need(r.returncode==0 and b"Verified OK" in r.stdout,
             "C08_V3_P256_OWNER_SIGNATURE_INVALID")

def comment_live():
    r=subprocess.run(["gh","api",
       "repos/Emaren/wolochain/issues/comments/"+str(KEY_COMMENT_ID)],
        capture_output=True,timeout=15)
    need(r.returncode==0,"C08_V3_PUBLIC_KEY_ENROLLMENT_UNAVAILABLE")
    return strict(r.stdout)

def notice_live():
    return notice.live_fetch()

def verify_public_lineage(comment,issue,repo_info,now):
    need(type(comment) is dict and type(comment.get("user")) is dict,
         "C08_V3_KEY_COMMENT_MISSING")
    need(comment.get("id")==KEY_COMMENT_ID
         and comment.get("issue_url")==
           "https://api.github.com/repos/Emaren/wolochain/issues/184"
         and comment["user"].get("login")=="Emaren"
         and isinstance(comment.get("body"),str)
         and sha(comment["body"].encode())==KEY_COMMENT_SHA
         and OWNER_X963_SHA in comment["body"],
         "C08_V3_PUBLIC_OWNER_KEY_ENROLLMENT_DRIFT")
    result=notice.inspect_notice(issue,repo_info,now=now)
    need(result["status"]=="PASS_NOTICE_TIME_ONLY_ALL_FINANCIAL_GATES_HOLD",
         "C08_V3_SINGLE_HUMAN_NOTICE_NOT_MATURE")
    return result

def request_valid(q,now,commit):
    need(type(q) is dict and set(q)==REQUEST_KEYS
         and q["schema"]==REQUEST_SCHEMA
         and q["chain_id"]=="wolo-1"
         and q["operation"]=="one-human-source-bound-policy-adoption-zero-funds"
         and q["source_commit"]==commit
         and q["policy_sha256"]==POLICY_SHA
         and q["owner_public_x963_sha256"]==OWNER_X963_SHA
         and q["historical_ed25519_der_sha256"]==HISTORICAL_ED25519_DER_SHA
         and q["historical_owner_key_signed_this_request"] is False
         and q["key_enrollment_comment_id"]==KEY_COMMENT_ID
         and q["key_enrollment_comment_body_sha256"]==KEY_COMMENT_SHA
         and q["public_notice_url"]==notice.ISSUE_URL
         and q["public_notice_body_sha256"]==notice.EXACT_PUBLIC_BODY_SHA256
         and type(q["owner_human_count"]) is int
         and q["owner_human_count"]==1
         and q["independent_human_review_claimed"] is False
         and q["legacy_8092_fallback_allowed"] is False
         and q["historical_claims_waived"] is False
         and q["financial_release_authorized"] is False
         and type(q["standing_funded_allowance_uwolo"]) is int
         and q["standing_funded_allowance_uwolo"]==0
         and type(q["future_c09_canary_ceiling_uwolo"]) is int
         and q["future_c09_canary_ceiling_uwolo"]==1000000
         and q["c09_transaction_signature_present"] is False,
         "C08_V3_SIGNED_POLICY_SCOPE_INVALID")
    need(type(q["nonce"]) is str and HEX32.fullmatch(q["nonce"]) is not None
         and q["nonce"]!="0"*32,"C08_V3_ADOPTION_NONCE_INVALID")
    begin=old.utc(q["not_before"]);end=old.utc(q["expires_at"])
    need(begin<=now<end and timedelta()<end-begin<=timedelta(minutes=30),
         "C08_V3_SIGNED_WINDOW_EXPIRED_OR_EXPANDED")

def signature_message(q):
    return DOMAIN+canonical(q)

def prepared_request(repo,now,nonce=None):
    commit=git_commit(repo)
    q={
      "schema":REQUEST_SCHEMA,"chain_id":"wolo-1",
      "operation":"one-human-source-bound-policy-adoption-zero-funds",
      "source_commit":commit,"policy_sha256":POLICY_SHA,
      "owner_public_x963_sha256":OWNER_X963_SHA,
      "historical_ed25519_der_sha256":HISTORICAL_ED25519_DER_SHA,
      "historical_owner_key_signed_this_request":False,
      "key_enrollment_comment_id":KEY_COMMENT_ID,
      "key_enrollment_comment_body_sha256":KEY_COMMENT_SHA,
      "public_notice_url":notice.ISSUE_URL,
      "public_notice_body_sha256":notice.EXACT_PUBLIC_BODY_SHA256,
      "owner_human_count":1,"independent_human_review_claimed":False,
      "legacy_8092_fallback_allowed":False,
      "historical_claims_waived":False,
      "financial_release_authorized":False,
      "standing_funded_allowance_uwolo":0,
      "future_c09_canary_ceiling_uwolo":1000000,
      "c09_transaction_signature_present":False,
      "nonce":nonce or os.urandom(16).hex(),
      "not_before":old.stamp(now-timedelta(seconds=5)),
      "expires_at":old.stamp(now+timedelta(minutes=20))
    }
    request_valid(q,now,commit)
    return q

def verify_packet(packet_raw,repo,public,now,
                  comment=None,issue=None,repo_info=None):
    p=strict(packet_raw)
    need(type(p) is dict and set(p)==PACKET_KEYS
         and p["schema"]==PACKET_SCHEMA
         and type(p.get("request")) is dict,
         "C08_V3_PACKET_SCHEMA")
    q=p["request"]
    commit=git_commit(repo,ref=q.get("source_commit"))
    request_valid(q,now,commit)
    if comment is None:comment=comment_live()
    if issue is None or repo_info is None:issue,repo_info=notice_live()
    verify_public_lineage(comment,issue,repo_info,now)
    try:sig=base64.b64decode(p["signature_der_b64"],validate=True)
    except (ValueError,binascii.Error,TypeError) as exc:
        raise Hold("C08_V3_SIGNATURE_BASE64") from exc
    verify_ecdsa(signature_message(q),sig,public)
    return p

def adopted(root,repo,public,now=None,comment=None,issue=None,repo_info=None):
    now=now or datetime.now(timezone.utc)
    folder=root_safe(root)
    raw=read_private(folder/RECEIPT_FILE)
    r=strict(raw)
    need(type(r) is dict and set(r)==RECEIPT_KEYS
         and r["schema"]==RECEIPT_SCHEMA
         and r["status"]=="PASS_C08_ONE_HUMAN_KEYCHAIN_GOVERNANCE_ADOPTED_NO_FUNDS"
         and r["standing_funded_allowance_uwolo"]==0
         and r["future_c09_canary_ceiling_uwolo"]==1000000
         and r["financial_release_authorized"] is False
         and r["c09_permit_issued"] is False
         and r["single_human_owner_disclosed"] is True
         and r["independent_human_review_claimed"] is False
         and r["historic_ed25519_key_not_used"] is True
         and r["login_keychain_software_key_not_secure_enclave"] is True,
         "C08_V3_ADOPTED_RECEIPT_SCOPE_INVALID")
    at=old.utc(r["adopted_utc"])
    # The original adoption was only valid inside its signed window.
    # Later authentication evaluates that original time, not today's time.
    p=verify_packet(canonical(r["signed_packet"]),repo,public,at,
        comment=comment,issue=issue,repo_info=repo_info)
    need(r["source_commit"]==p["request"]["source_commit"]
         and r["policy_sha256"]==POLICY_SHA
         and r["owner_public_x963_sha256"]==OWNER_X963_SHA
         and r["signed_packet_sha256"]==sha(canonical(p))
         and r["public_notice_url"]==notice.ISSUE_URL
         and r["key_enrollment_comment_id"]==KEY_COMMENT_ID,
         "C08_V3_SIGNED_RECEIPT_PROVENANCE_CHANGED")
    return {"status":"PASS_C08_KEYCHAIN_GOVERNANCE_OWNER_ADOPTION_VERIFIED",
            "receipt_sha256":sha(raw),"source_commit":r["source_commit"],
            "signed_at":r["adopted_utc"],
            "standing_funded_allowance_uwolo":0,
            "future_c09_canary_ceiling_uwolo":1000000,
            "financial_release_authorized":False}

def ceremony(repo,root,now=None,comment=None,issue=None,repo_info=None,
            signer=None,nonce=None):
    """Single atomic zero-funded C08 adoption. Caller can test with signer fixture."""
    now=now or datetime.now(timezone.utc)
    folder=root_safe(root,create=True)
    pin=key_public(read_private(folder/PUB_FILE))
    code=git_commit(repo)
    if comment is None:comment=comment_live()
    if issue is None or repo_info is None:issue,repo_info=notice_live()
    verify_public_lineage(comment,issue,repo_info,now)
    lock=os.open(folder/"keychain-adoption-v3.lock",
        os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
    try:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        need(not (folder/RECEIPT_FILE).exists(),"C08_V3_ALREADY_ADOPTED_NO_REPLAY")
        q=prepared_request(repo,now,nonce=nonce)
        need(q["source_commit"]==code,"C08_V3_SOURCE_CHANGED_DURING_ADOPTION")
        message=signature_message(q)
        with tempfile.TemporaryDirectory(prefix="c08-keychain-policy-sign-") as t:
            msg=Path(t)/"message";sig=Path(t)/"signature"
            msg.write_bytes(message);msg.chmod(0o600)
            if signer is None:
                exe=Path(repo)/SOURCE_SWIFT
                result=subprocess.run(["swift",str(exe),"sign",str(msg),str(sig)],
                    capture_output=True,text=True,timeout=35)
                need(result.returncode==0 and
                     "PASS_C08_NONINTERACTIVE_KEYCHAIN_POLICY_SIGNATURE_CREATED" in
                      result.stdout,"C08_V3_MAC_KEYCHAIN_SIGNER_UNAVAILABLE")
                signature=sig.read_bytes()
            else:signature=signer(message)
        verify_ecdsa(message,signature,pin)
        p={"schema":PACKET_SCHEMA,"request":q,
           "signature_der_b64":base64.b64encode(signature).decode("ascii")}
        checked=verify_packet(canonical(p),repo,pin,now,
            comment=comment,issue=issue,repo_info=repo_info)
        r={
          "schema":RECEIPT_SCHEMA,
          "status":"PASS_C08_ONE_HUMAN_KEYCHAIN_GOVERNANCE_ADOPTED_NO_FUNDS",
          "source_commit":code,"policy_sha256":POLICY_SHA,
          "owner_public_x963_sha256":OWNER_X963_SHA,
          "signed_packet":checked,"signed_packet_sha256":sha(canonical(checked)),
          "adopted_utc":old.stamp(now),
          "public_notice_url":notice.ISSUE_URL,
          "key_enrollment_comment_id":KEY_COMMENT_ID,
          "historic_ed25519_key_not_used":True,
          "login_keychain_software_key_not_secure_enclave":True,
          "single_human_owner_disclosed":True,
          "independent_human_review_claimed":False,
          "standing_funded_allowance_uwolo":0,
          "future_c09_canary_ceiling_uwolo":1000000,
          "financial_release_authorized":False,"c09_permit_issued":False
        }
        need(set(r)==RECEIPT_KEYS,"C08_V3_RECEIPT_SCHEMA")
        output=canonical(r)+b"\n"
        write_private(folder/RECEIPT_FILE,output)
        return {"status":r["status"],
                "receipt_sha256":sha(output),
                "standing_funded_allowance_uwolo":0,
                "financial_release_authorized":False}
    finally:os.close(lock)

def main(argv=None):
    arg=argparse.ArgumentParser(description=__doc__)
    arg.add_argument("mode",choices=("adopt","status"))
    arg.add_argument("--repo",type=Path,default=Path(__file__).resolve().parents[1])
    arg.add_argument("--owner-root",type=Path,required=True)
    opts=arg.parse_args(argv)
    try:
        if opts.mode=="adopt":
            report=ceremony(opts.repo,opts.owner_root)
        else:
            report=adopted(opts.owner_root,opts.repo,
                read_private(opts.owner_root/PUB_FILE))
        print(json.dumps(report,sort_keys=True))
        return 0
    except (Hold,old.Hold,notice.NoticeStop,OSError,
            subprocess.SubprocessError,ValueError,TypeError,
            KeyError,RuntimeError) as exc:
        why=str(exc) if isinstance(exc,(Hold,old.Hold)) else "C08_V3_UNVERIFIED"
        print(json.dumps({"status":"HOLD_C08_KEYCHAIN_GOVERNANCE_NOT_ADOPTED",
                          "reason":why[:110],"financial_release_authorized":False},
                         sort_keys=True))
        return 3

if __name__=="__main__":sys.exit(main())

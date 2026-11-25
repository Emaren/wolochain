#!/usr/bin/env python3
"""C05 one-validator bank-height/commit consistency witness.

Off-host observation of ONE authoritative node is NOT independent consensus,
reserve control, or payment proof. Emits a minimal private sealed receipt.
No wallet, transaction, SQL, key, systemd, or funded mutation paths exist.
"""
from __future__ import annotations
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys

SCHEMA = "wolo.c05.one-validator.fixed-bank-height.offhost-observer.v1"
HEX64 = re.compile(r"^[0-9A-Fa-f]{64}$")
ADDR = re.compile(r"^[0-9A-Fa-f]{40}$")
TARGET = "root@157.180.114.124"
EXPECTED_CENSUS_SHA256 = "148b9d9aa46b01eafd3804a1603d954f2bbaaffe282755e430a288dbc815159d"
REMOTE = r'''
import datetime,json,hashlib,urllib.request
p="/root/aoe2war-c05-native-registered24-bank-v3-20261109/registered24-single-height-native-bank.json"
raw=open(p,"rb").read()
c=json.loads(raw)
height=c["observed_height"]
def get(path):
    with urllib.request.urlopen("http://127.0.0.1:27657/"+path, timeout=8) as r:
        d=json.load(r)
    if "error" in d:raise RuntimeError("RPC_ERROR_"+path.split("?")[0])
    return d["result"]
b=get("block?height="+str(height))
co=get("commit?height="+str(height))
v=get("validators?height="+str(height)+"&per_page=100")
s=get("status")
print(json.dumps({"observed_at_utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),
"census_sha256":hashlib.sha256(raw).hexdigest(),
"census":{"network":c["network"],"observed_height":height,
"local_consensus_block_hash":c["local_consensus_block_hash"],
"registered_wallet_count":len(c["public_wallets"]),
"total_all_24_labels_uwolo":c["total_all_24_labels_uwolo"],
"eligible_reserves_uwolo":c["actual_eligible_spendable_reserves_proven_uwolo"],
"c05_gate_closed":c["c05_gate_closed"],
"offhost_consensus_witness_verified":c["offhost_consensus_witness_verified"]},
"block":{"block_id":b["block_id"],"header":b["block"]["header"]},
"commit":{"signed_header":co["signed_header"]},
"validators":v,"status":s}))
'''


class Hold(ValueError):
    pass


def need(ok: bool, why: str) -> None:
    if not ok:
        raise Hold("HOLD_C05_" + why)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def canonical(obj: dict) -> bytes:
    return (json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n").encode()


def hexeq(a: str, b: str) -> bool:
    return isinstance(a,str) and isinstance(b,str) and bool(HEX64.fullmatch(a)) and a.upper()==b.upper()


def classify(data: dict) -> dict:
    need(isinstance(data,dict), "INPUT_NOT_OBJECT")
    c,b,co,v,s = (data[k] for k in ("census","block","commit","validators","status"))
    need(data["census_sha256"] == EXPECTED_CENSUS_SHA256, "UNPINNED_CENSUS")
    h=c["observed_height"]
    need(type(h) is int and h>0, "BANK_HEIGHT")
    need(c["network"]=="wolo-1", "BANK_NETWORK")
    need(c["registered_wallet_count"]==24, "BANK_WALLET_COUNT")
    need(c["total_all_24_labels_uwolo"]=="87639451200705", "BANK_TOTAL_DRIFT")
    need(c["eligible_reserves_uwolo"]=="0" and c["c05_gate_closed"] is False,
         "FALSE_COLLATERAL_CLAIM")
    need(c["offhost_consensus_witness_verified"] is False,
         "CENSUS_HAS_UNEXPECTED_WITNESS_CLAIM")
    header=b["header"]
    signed=co["signed_header"]
    commit=signed["commit"]
    need(str(header["height"])==str(h) and
         str(signed["header"]["height"])==str(h) and
         str(commit["height"])==str(h), "MIXED_HEIGHT")
    need(header["chain_id"]=="wolo-1" and
         signed["header"]["chain_id"]=="wolo-1" and
         s["node_info"]["network"]=="wolo-1", "CHAIN_ID_MISMATCH")
    bh=b["block_id"]["hash"]
    need(hexeq(bh,c["local_consensus_block_hash"]) and
         hexeq(bh,commit["block_id"]["hash"]), "BLOCK_HASH_MISMATCH")
    need(hexeq(header["app_hash"],signed["header"]["app_hash"]),
         "APP_HASH_MISMATCH")
    need(hexeq(header["validators_hash"],signed["header"]["validators_hash"]),
         "VALIDATOR_HASH_MISMATCH")
    need(str(v["block_height"])==str(h) and str(v["total"])=="1"
         and str(v["count"])=="1" and len(v["validators"])==1,
         "NOT_EXACT_ONE_VALIDATOR")
    val=v["validators"][0]
    addr=val["address"]
    need(isinstance(addr,str) and ADDR.fullmatch(addr) is not None,
         "VALIDATOR_ID")
    signatures=commit["signatures"]
    need(len(signatures)==1 and signatures[0]["validator_address"]==addr
         and signatures[0]["block_id_flag"]==2
         and bool(signatures[0]["signature"]), "NO_ONE_VALIDATOR_COMMIT")
    need(int(val["voting_power"])>0 and
         int(s["validator_info"]["voting_power"])>0, "NO_VOTING_POWER")
    need(s["validator_info"]["address"]==addr, "LOCAL_VALIDATOR_CHANGED")
    need(int(s["sync_info"]["latest_block_height"])>=h and
         s["sync_info"]["catching_up"] is False, "CHAIN_NOT_CURRENT")
    return {
        "schema":SCHEMA,
        "classification":"PASS_SAME_NODE_HISTORICAL_BLOCK_COMMIT_CONSISTENCY",
        "bank_height":h,
        "bank_census_sha256":data["census_sha256"],
        "bank_local_block_hash":bh.upper(),
        "bank_app_hash":header["app_hash"].upper(),
        "bank_validator_set_hash":header["validators_hash"].upper(),
        "one_validator_address":addr,
        "one_validator_voting_power":str(val["voting_power"]),
        "commit_has_signature":True,
        "latest_observed_height":int(s["sync_info"]["latest_block_height"]),
        "observed_at_utc":data["observed_at_utc"],
        "chain_id":"wolo-1",
        "financial_gate_closed":False,
        "eligible_unencumbered_reserves_proven_uwolo":"0",
        "funding_authorized":False,
        "independent_consensus_verified":False,
        "independent_bank_balances_reverified":False,
        "reason":"SSH off-host copy of a single-validator RPC is not an independent validator or cryptographic signature verification.",
    }


def seal(result: dict, target: Path) -> dict:
    parent=target.parent
    need(parent.is_dir() and not target.exists() and not target.is_symlink(),
         "RECEIPT_TARGET_EXISTS_OR_PARENT")
    raw=canonical(result)
    fd=os.open(target, os.O_CREAT | os.O_WRONLY | os.O_EXCL | os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,"wb") as f:
        f.write(raw);f.flush();os.fsync(f.fileno())
    need(stat.S_IMODE(target.stat().st_mode)==0o600,"PRIVATE_RECEIPT_MODE")
    return {"result":result["classification"],"receipt":str(target),
            "sha256":sha(raw),"finance_authorized":False}


def main() -> None:
    ap=argparse.ArgumentParser()
    g=ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--live-ssh",action="store_true")
    g.add_argument("--fixture-json",type=Path)
    ap.add_argument("--private-receipt",type=Path)
    args=ap.parse_args()
    if args.live_ssh:
        need(args.private_receipt is not None, "LIVE_REQUIRES_PRIVATE_RECEIPT")
        p=subprocess.run(["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes",
             "-o","ConnectTimeout=8",TARGET,"python3 -I -B -"],
             input=REMOTE,text=True,capture_output=True,timeout=45,check=False)
        need(p.returncode==0 and len(p.stdout)<250_000, "REMOTE_RPC_READ")
        d=json.loads(p.stdout)
    else:
        d=json.loads(args.fixture_json.read_text())
    result=classify(d)
    if args.private_receipt:
        print(json.dumps(seal(result,args.private_receipt),sort_keys=True))
    else:
        print(json.dumps(result,sort_keys=True))


if __name__=="__main__":
    try:
        main()
    except (Hold,KeyError,TypeError,ValueError,OSError,subprocess.TimeoutExpired) as exc:
        print("HOLD_C05_FIXED_HEIGHT_WITNESS_"+type(exc).__name__,file=sys.stderr)
        sys.exit(3)

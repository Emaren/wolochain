#!/usr/bin/env python3
"""Offline C04 Comet TX inclusion observation, never independent payment finality.

Validates a private candidate against private locally obtained Comet /tx?prove
and /block responses.  This proves a cryptographic link to a SAME OPERATOR
local block, not a separate consensus checkpoint, economic claim identity,
custody signer, disjointness, or authorization to replay/refund/credit.
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
import sys

SCHEMA="wolo.c04.same-node-comet-tx-merkle-inclusion-hold.v1"
SHA=re.compile(r"[0-9a-f]{64}\Z")
HEX64=re.compile(r"[0-9a-fA-F]{64}\Z")
MAX_BYTES=1_000_000

class Hold(ValueError):
    pass

def need(ok,why):
    if not ok:raise Hold(why)

def private_json(path,expected):
    need(type(expected) is str and SHA.fullmatch(expected),"INPUT_SHA_REQUIRED")
    path=Path(path)
    need(path.is_absolute() and not path.is_symlink(),"ABSOLUTE_PRIVATE_PATH_REQUIRED")
    st=path.lstat()
    need(stat.S_ISREG(st.st_mode) and st.st_uid==os.geteuid()
         and st.st_nlink==1 and stat.S_IMODE(st.st_mode)==0o600,
         "PRIVATE_INPUT_OWNER_OR_MODE_CHANGED")
    need(0<st.st_size<MAX_BYTES,"PRIVATE_INPUT_SIZE")
    raw=path.read_bytes()
    need(hashlib.sha256(raw).hexdigest()==expected,"INPUT_DIGEST_CHANGED")
    d=json.loads(raw)
    need(type(d) is dict,"PRIVATE_JSON_NOT_OBJECT")
    return d

def b64(value,limit=MAX_BYTES):
    need(type(value) is str and 0<len(value)<MAX_BYTES*2,
         "BASE64_VALUE_INVALID")
    try:
        raw=base64.b64decode(value,validate=True)
    except (ValueError,base64.binascii.Error):
        raise Hold("BASE64_DECODE_FAILED") from None
    need(0<len(raw)<=limit,"BASE64_DECODE_SIZE")
    return raw

def merkle_from_aunts(index,total,leaf,aunts):
    need(type(index) is int and type(total) is int and
         0<=index<total<=100_000 and type(aunts) is list and len(aunts)<=40
         and type(leaf) is bytes and len(leaf)==32,"MERKLE_PROOF_SHAPE")
    need(all(type(a) is bytes and len(a)==32 for a in aunts),
         "MERKLE_AUNT_SHAPE")
    if total==1:
        need(index==0 and not aunts,"MERKLE_SINGLETON_AUNTS")
        return leaf
    need(aunts,"MERKLE_AUNT_MISSING")
    split=1 << (total.bit_length()-1)
    if split==total:split//=2
    if index<split:
        left=merkle_from_aunts(index,split,leaf,aunts[:-1])
        right=aunts[-1]
    else:
        left=aunts[-1]
        right=merkle_from_aunts(index-split,total-split,leaf,aunts[:-1])
    return hashlib.sha256(bytes([1])+left+right).digest()

def decode_attr(value):
    need(type(value) is str and len(value)<1024,"EVENT_ATTRIBUTE_SHAPE")
    try:
        raw=base64.b64decode(value,validate=True)
        decoded=raw.decode("utf-8")
        if decoded and all(32<=ord(ch)<=126 for ch in decoded):
            return decoded
    except (ValueError,UnicodeError,base64.binascii.Error):
        pass
    return value

def validate(candidate_doc,tx,block):
    need(set(candidate_doc)=={"query_sha256","candidate"} and
         type(candidate_doc["query_sha256"]) is str and
         SHA.fullmatch(candidate_doc["query_sha256"]) and
         type(candidate_doc["candidate"]) is dict,
         "CANDIDATE_SOURCE_SHAPE")
    c=candidate_doc["candidate"]
    need(set(c)=={"claim_id","kind","nominal_wolo","candidate_tx_hash",
                  "candidate_height","candidate_amount_uwolo","candidate_recipient"},
         "CANDIDATE_SCHEMA")
    need(c["kind"]=="bet_payout" and type(c["claim_id"]) is int
         and c["claim_id"]>0,"CANDIDATE_CLAIM_KIND")
    need(type(c["nominal_wolo"]) is int and
         type(c["candidate_amount_uwolo"]) is int and
         c["nominal_wolo"]>0 and
         c["nominal_wolo"]*1_000_000==c["candidate_amount_uwolo"],
         "CANDIDATE_AMOUNT_MISMATCH")
    height=c["candidate_height"]
    need(type(height) is int and height>0,"CANDIDATE_HEIGHT_INVALID")
    txhash=c["candidate_tx_hash"]
    need(type(txhash) is str and HEX64.fullmatch(txhash.removeprefix("0x")),
         "CANDIDATE_TX_HASH_INVALID")
    need(type(c["candidate_recipient"]) is str and
         re.fullmatch(r"wolo1[a-z0-9]{20,90}",c["candidate_recipient"]),
         "CANDIDATE_RECIPIENT_INVALID")

    need(type(tx) is dict and type(block) is dict,
         "COMET_RPC_DOCUMENTS_INVALID")
    need(type(tx.get("tx")) is str and
         type(tx.get("height")) is str and
         type(tx.get("hash")) is str and
         type(tx.get("tx_result")) is dict and
         type(tx.get("proof")) is dict,"COMET_TX_RESULT_MISSING")
    raw_tx=b64(tx["tx"])
    real_hash=hashlib.sha256(raw_tx).digest()
    need(tx["hash"].upper()==real_hash.hex().upper()==txhash.removeprefix("0x").upper(),
         "TRANSACTION_BYTES_HASH_MISMATCH")
    need(tx["height"]==str(height) and
         type(tx["tx_result"].get("code")) is int and
         tx["tx_result"]["code"]==0,
         "TRANSACTION_HEIGHT_OR_EXECUTION_CHANGED")
    proof=tx["proof"]
    need(set(proof)=={"data","root_hash","proof"} and
         proof["data"]==tx["tx"] and
         type(proof["proof"]) is dict and
         set(proof["proof"])=={"aunts","index","leaf_hash","total"},
         "COMET_PROOF_FORMAT_CHANGED")
    p=proof["proof"]
    need(all(type(p[k]) is str and re.fullmatch(r"[0-9]{1,10}",p[k])
             for k in ("total","index")),"MERKLE_INDEX_SHAPE")
    leaf=hashlib.sha256(bytes([0])+real_hash).digest()
    need(b64(p["leaf_hash"],limit=32)==leaf,
         "COMET_TXHASH_LEAF_MISMATCH")
    need(type(p["aunts"]) is list and len(p["aunts"])<=40,
         "COMET_AUNTS_FORMAT")
    aunts=[b64(x,limit=32) for x in p["aunts"]]
    root=merkle_from_aunts(int(p["index"]),int(p["total"]),leaf,aunts)
    need(type(proof["root_hash"]) is str and
         HEX64.fullmatch(proof["root_hash"]) and
         root.hex().upper()==proof["root_hash"].upper(),
         "COMET_MERKLE_ROOT_MISMATCH")

    bb=block.get("block")
    need(type(bb) is dict and type(bb.get("header")) is dict and
         type(bb.get("data")) is dict and type(bb["data"].get("txs")) is list,
         "COMET_BLOCK_DOCUMENT_SHAPE")
    header=bb["header"]
    need(header.get("chain_id")=="wolo-1" and
         header.get("height")==str(height) and
         type(header.get("data_hash")) is str and
         root.hex().upper()==header["data_hash"].upper(),
         "LOCAL_BLOCK_DATA_ROOT_MISMATCH")
    ts=bb["data"]["txs"]
    need(len(ts)==int(p["total"]) and
         ts[int(p["index"])]==tx["tx"],
         "BLOCK_TX_POSITION_OR_COUNT_DRIFT")
    need(type(block.get("block_id")) is dict and
         type(block["block_id"].get("hash")) is str and
         HEX64.fullmatch(block["block_id"]["hash"]),
         "BLOCK_ID_MISSING")
    events=tx["tx_result"].get("events")
    need(type(events) is list and len(events)<=200,
         "COMET_TX_EVENTS_MISSING")
    matches=0
    transfer_count=0
    for e in events:
        need(type(e) is dict and type(e.get("type")) is str and
             type(e.get("attributes")) is list and len(e["attributes"])<=80,
             "COMET_EVENT_FORMAT_CHANGED")
        if e["type"]!="transfer":continue
        transfer_count+=1
        attrs={}
        for a in e["attributes"]:
            need(type(a) is dict,"COMET_TRANSFER_ATTRIBUTE_FORMAT")
            key=decode_attr(a.get("key"))
            val=decode_attr(a.get("value"))
            need(key not in attrs,"DUPLICATED_TRANSFER_ATTRIBUTE")
            attrs[key]=val
        if (attrs.get("recipient","").lower()==c["candidate_recipient"].lower()
            and attrs.get("amount","")==str(c["candidate_amount_uwolo"])+"uwolo"):
            matches+=1
    need(matches>=1,"ACTUAL_TRANSFER_EVENT_NOT_LINKED_TO_INDEXED_CANDIDATE")

    return {"schema":SCHEMA,
            "status":"HOLD_C04_LOCAL_MERKLE_INCLUSION_NOT_INDEPENDENT_PAYMENT_FINALITY",
            "candidate_kind":"bet_payout","same_local_chain_id":"wolo-1",
            "candidate_block_height":str(height),
            "raw_transaction_sha256_matches_index":True,
            "comet_tx_hash_leaf_uses_sha256_transaction_hash":True,
            "merkle_root_equals_local_block_data_hash":True,
            "local_block_tx_position_verified":True,
            "execution_code_zero":True,
            "transfer_event_recipient_amount_match":True,
            "matching_transfer_event_records":matches,
            "all_transfer_event_records":transfer_count,
            "single_operator_rpc_source_only":True,
            "independent_checkpoint_authenticated":False,
            "claim_economic_payout_purpose_authenticated":False,
            "payer_custody_signer_authenticated":False,
            "claim_discharge_authorized":False,
            "retry_authorized":False,
            "financial_release_authorized":False,
            "production_mutated":False}

def main(argv=None):
    ap=argparse.ArgumentParser(description=__doc__)
    for key in ("candidate","tx","block"):
        ap.add_argument("--"+key,type=Path,required=True)
        ap.add_argument("--"+key+"-sha256",required=True)
    args=ap.parse_args(argv)
    try:
        c=private_json(args.candidate,args.candidate_sha256)
        t=private_json(args.tx,args.tx_sha256)
        b=private_json(args.block,args.block_sha256)
        print(json.dumps(validate(c,t,b),sort_keys=True))
        return 3
    except (Hold,ValueError,OSError,UnicodeError,TypeError,KeyError,json.JSONDecodeError) as e:
        reason=str(e) if isinstance(e,Hold) else "PRIVATE_LOCAL_PROOF_UNAVAILABLE"
        print(json.dumps({"schema":SCHEMA,"status":"STOP","reason":reason,
            "financial_release_authorized":False,"production_mutated":False},sort_keys=True))
        return 2

if __name__=="__main__":
    sys.exit(main())

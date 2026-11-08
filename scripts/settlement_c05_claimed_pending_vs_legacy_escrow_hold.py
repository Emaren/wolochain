#!/usr/bin/env python3
"""C04/C05 root-only HD claim nominal vs on-chain historic escrow HOLD.

Nonmutating physical observation only. A gross claim nominal minus one
historical wallet balance is NEVER proof of debt, solvency, signer control,
finality or a funded payout. Verify exact HD public records, live Comet
chain identity, bank at one pinned height and reserve provenance separately.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import urllib.request

SCHEMA="wolo.c05.hd-claim-nominal-single-height-legacy-escrow-comparison-hold.v1"
WALLET="wolo1zygwt232ymc4h2g52yvkntffhmd5alx2kglw7p"
NODE="http://127.0.0.1:27657/"
EXE=Path("/usr/local/bin/wolochaind-mainnet-node-prewartrophy")
EXPECTED={"claimed_hashless":(69,120443),"pending":(948,993289)}
RECEIPT=Path("/root/aoe2war-c05-hd-escrow-comparison-20261108")
SQL="""BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;
SET LOCAL statement_timeout='9000ms';
SELECT CASE WHEN c.status='claimed' AND
 NULLIF(btrim(coalesce(c.payout_tx_hash,'')),'') IS NULL
 THEN 'claimed_hashless'
 WHEN c.status='pending' THEN 'pending' ELSE 'other' END,
 count(*),coalesce(sum(c.amount_wolo::bigint),0),count(DISTINCT c.id)
FROM public.pending_wolo_claims c
WHERE c.status='pending' OR
 (c.status='claimed' AND
  NULLIF(btrim(coalesce(c.payout_tx_hash,'')),'') IS NULL)
GROUP BY 1 ORDER BY 1;
ROLLBACK;
"""
HEX64=re.compile(r"[A-Fa-f0-9]{64}\Z")

class Hold(ValueError):pass

def need(ok,why):
    if not ok:raise Hold(why)

def canonical(obj):
    return (json.dumps(obj,sort_keys=True,indent=2)+"\n").encode()

def parse_claims(raw:str)->dict:
    need(type(raw) is str and 1<len(raw)<8192,"HD_CLAIM_SQL_OUTPUT_BOUNDS")
    result={}
    for line in raw.splitlines():
        parts=line.split("|")
        need(len(parts)==4,"HD_CLAIM_ROW_FORMAT")
        kind,count,amount,distinct=parts
        need(kind in EXPECTED and kind not in result,"HD_CLAIM_KIND_OR_DUPLICATE")
        need(all(x.isdecimal() and len(x)<30 for x in (count,amount,distinct)),
             "HD_CLAIM_COUNTER_NOT_INTEGER")
        n,a,u=int(count),int(amount),int(distinct)
        need((n,a)==EXPECTED[kind] and u==n,"HD_CLAIM_POPULATION_DRIFT")
        result[kind]={"rows":n,"nominal_wolo":a,"distinct_claim_ids":u}
    need(set(result)==set(EXPECTED),"HD_CLAIM_GROUP_MISSING")
    return result

def parse_bank(obj:dict)->int:
    need(type(obj) is dict and set(obj)=={"balances","pagination"},
         "NATIVE_BANK_RESPONSE_SHAPE_DRIFT")
    entries=obj["balances"]
    need(type(entries) is list and len(entries)<=1,
         "NATIVE_BANK_UNREVIEWED_DENOM")
    amount=0
    for entry in entries:
        need(type(entry) is dict and set(entry)=={"denom","amount"}
             and entry["denom"]=="uwolo"
             and type(entry["amount"]) is str
             and entry["amount"].isdecimal()
             and 0<len(entry["amount"])<24,"NATIVE_BANK_DENOM_OR_AMOUNT")
        amount+=int(entry["amount"])
    need(0<=amount<=100_000_000*1_000_000,
         "NATIVE_BANK_SUPPLY_CAP_EXCEEDED")
    return amount

def run(args,*,timeout=16):
    r=subprocess.run(args,input=SQL if args[0]=="runuser" else None,
       capture_output=True,text=True,timeout=timeout,check=False)
    need(r.returncode==0,"SOURCE_NATIVE_OR_SQL_QUERY_FAILED")
    return r.stdout

def rpc(method:str,params:dict):
    need(method in ("status","block"),"UNREVIEWED_RPC_METHOD")
    request=urllib.request.Request(
      NODE,data=json.dumps({"jsonrpc":"2.0","id":"c05-readonly-claim-wallet",
                            "method":method,"params":params}).encode(),
      headers={"Content-Type":"application/json"})
    with urllib.request.urlopen(request,timeout=6) as f:
        answer=json.load(f)
    need(type(answer) is dict and type(answer.get("result")) is dict
         and "error" not in answer,"RPC_STATUS_UNAVAILABLE")
    return answer["result"]

def observe():
    need(os.geteuid()==0,"HEL1_ROOT_REQUIRED")
    binary=os.readlink("/proc/1009/exe")
    need(binary==str(EXE),"LIVE_WOLO_VALIDATOR_BINARY_CHANGED")
    tokens=[p.decode("utf8","replace") for p in
            Path("/proc/1009/cmdline").read_bytes().split(b"\0") if p]
    need(tokens.count("--home")==1,"VALIDATOR_HOME_PIN_MISSING")
    home=tokens[tokens.index("--home")+1]
    need(home.startswith("/") and len(home)<200,"VALIDATOR_HOME_INVALID")
    status=rpc("status",{})
    need(status["node_info"]["network"]=="wolo-1"
         and status["sync_info"]["catching_up"] is False,
         "CONSENSUS_NETWORK_OR_SYNC_INVALID")
    height=int(status["sync_info"]["latest_block_height"])
    need(2_800_000<=height<=100_000_000_000,
         "CHAIN_HEIGHT_BOUNDS_CHANGED")
    block=rpc("block",{"height":str(height)})
    block_hash=block["block_id"]["hash"]
    need(HEX64.fullmatch(block_hash) is not None
         and block["block"]["header"]["chain_id"]=="wolo-1"
         and int(block["block"]["header"]["height"])==height,
         "PINNED_LOCAL_BLOCK_INVALID")
    query=[str(EXE),"query","bank","balances",WALLET,
           "--home",home,"--node","tcp://127.0.0.1:27657",
           "--height",str(height),"--output","json"]
    bank=parse_bank(json.loads(run(query,timeout=26)))
    sql=["runuser","-u","postgres","--","psql","-X","-qAt","-F","|",
         "-v","ON_ERROR_STOP=1","-d","aoe2hd_db"]
    claims=parse_claims(run(sql))
    total=sum(x["nominal_wolo"] for x in claims.values())*1_000_000
    comparison=total-bank
    return {
       "schema":SCHEMA,
       "utc":datetime.now(timezone.utc).isoformat(),
       "status":"HOLD_C05_GROSS_CLAIM_NOMINAL_NOT_INDEPENDENT_SOLVENCY",
       "chain_id":"wolo-1",
       "local_node_height":height,
       "local_node_block_hash":block_hash,
       "wallet_source_label":"historical_mainnet_settlement_escrow",
       "source_public_wallet":WALLET,
       "native_source_wallet_uwolo":str(bank),
       "hd_claims":claims,
       "gross_hd_claims_nominal_uwolo":str(total),
       "single_labeled_wallet_minus_gross_nominal_uwolo":str(-comparison),
       "arithmetic_difference_is_not_insolvency_or_actual_unpaid_debt":True,
       "original_69_payment_fates_proven":False,
       "all_pending_claims_independently_payable_proven":False,
       "chain_and_sql_cross_system_atomic":False,
       "complete_hd_de_liabilities_inventory":False,
       "independent_reserve_holder_or_signer_control_proven":False,
       "all_other_wolo_addresses_and_surfaces_included":False,
       "claim_and_wager_principal_overlap_removed":False,
       "c04_finality_gate_closed":False,
       "c05_solvency_gate_closed":False,
       "funded_8094_8095_authorized":False,
       "production_modified":False,
    }

def persist(obj:dict):
    need(not RECEIPT.exists() and not RECEIPT.is_symlink(),
         "OWNER_PRIVATE_RECEIPT_ALREADY_EXISTS")
    RECEIPT.mkdir(mode=0o700)
    dir_stat=RECEIPT.lstat()
    need(stat.S_ISDIR(dir_stat.st_mode) and dir_stat.st_uid==os.geteuid()
         and stat.S_IMODE(dir_stat.st_mode)==0o700,
         "ROOT_PRIVATE_DIRECTORY_UNSAFE")
    target=RECEIPT/"claims-vs-historic-escrow-single-height.json"
    raw=canonical(obj)
    fd=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,"wb") as f:
        f.write(raw);f.flush();os.fsync(f.fileno())
    return hashlib.sha256(raw).hexdigest()

def main():
    try:
        report=observe()
        digest=persist(report)
        print(json.dumps({
          "status":"PASS_READONLY_C04_C05_COMPARISON_WITH_FINANCIAL_HOLD",
          "height":report["local_node_height"],
          "source_escrow_uwolo":report["native_source_wallet_uwolo"],
          "gross_nominal_uwolo":report["gross_hd_claims_nominal_uwolo"],
          "labeled_wallet_minus_gross_uwolo":
            report["single_labeled_wallet_minus_gross_nominal_uwolo"],
          "root_only_receipt_sha256":digest,
          "c04_c05_gates_closed":False,"funded_authorized":False},
          sort_keys=True))
        return 3
    except (Hold,OSError,ValueError,KeyError,TypeError,
            subprocess.TimeoutExpired,UnicodeError):
        print(json.dumps({"status":"HOLD_C04_C05_PHYSICAL_COMPARISON_UNQUALIFIED",
                          "financial_release_authorized":False,
                          "production_modified":False},sort_keys=True))
        return 2

if __name__=="__main__":sys.exit(main())

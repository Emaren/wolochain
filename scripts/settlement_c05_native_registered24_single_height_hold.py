#!/usr/bin/env python3
"""C05 exact-source 23 registered mainnet wallets + separate C01 vault bank census.

Read only: source-registered wallet set, same wolo-1 Comet height, native CLI
historical bank queries; ZERO spendability/reserve eligibility asserted.
No private keys, SQL, service changes, broadcasts or direct remote calls.
"""
from __future__ import annotations
from datetime import datetime,timezone
from pathlib import Path
import hashlib,json,os,re,stat,subprocess,sys,urllib.request

CHAIN="wolo-1"
RPC="http://127.0.0.1:27657/"
NODE=Path("/usr/local/bin/wolochaind-mainnet-node-prewartrophy")
HOME="/var/lib/wolochaind-mainnet"
ROOT=Path("/root/aoe2war-c05-native-registered24-bank-v3-20261109")
SOURCE=Path(__file__).resolve()
C01="wolo1e5rn0r6wrh5u547r2rrtu72epkn88ag2j05wl5"
# Exact set of 23 labels from docs/mainnet-wallets.md at reviewed Git HEAD.
# Categories are informational. Do not infer operator signer or free reserves.
DOCUMENT=Path("/root/aoe2war-c05-source-pinned-mainnet-wallets-20261109.md")
DOCUMENT_SHA256="a159768ee35ccdd0c02f8be0005d1ca1fbedcbfe83079e91ba86544c2e9d0280"

def parse_registered_document(doc):
 need(type(doc) is str,"SOURCE_WALLET_DOC_TYPE")
 first=doc.index("## Current Mainnet Address Labels")
 last=doc.index("## Operational Notes",first)
 section=doc[first:last]
 result=[]
 for line in section.splitlines():
  cells=[c.strip() for c in line.split("|")]
  if len(cells)<4:continue
  address=re.fullmatch(r"\x60(wolo1[023456789acdefghjklmnpqrstuvwxyz]{38})\x60",cells[2])
  if address is None:continue
  label=re.sub(r"[^a-z0-9]+","_",cells[1].lower()).strip("_")
  need(re.fullmatch(r"[a-z][a-z0-9_]{2,64}",label) is not None,
       "REGISTERED_LABEL_INVALID")
  result.append((label,address.group(1)))
 need(len(result)==23 and len({x[1] for x in result})==23
      and len({x[0] for x in result})==23,"CANONICAL_23_WALLET_DOC_INCOMPLETE")
 return tuple(result)

def load_registered_document():
 need(DOCUMENT.is_absolute() and DOCUMENT.is_file() and
      not DOCUMENT.is_symlink(),"SOURCE_WALLET_DOCUMENT_MISSING")
 stat_info=DOCUMENT.lstat()
 need(stat_info.st_uid==0 and stat_info.st_nlink==1 and
      stat.S_IMODE(stat_info.st_mode)==0o600 and
      1000<stat_info.st_size<262144,"SOURCE_WALLET_DOCUMENT_PERMISSIONS")
 fd=os.open(DOCUMENT,os.O_RDONLY|os.O_NOFOLLOW)
 try:
  data=os.read(fd,262144)
 finally:os.close(fd)
 need(hashlib.sha256(data).hexdigest()==DOCUMENT_SHA256,
      "CANONICAL_SOURCE_DOCUMENT_SHA256_DRIFT")
 return parse_registered_document(data.decode("utf-8","strict"))
class Hold(Exception):pass
def need(cond,why):
 if not cond:raise Hold(why)
def rpc(method,params=None):
 req=urllib.request.Request(RPC,
   data=json.dumps({"jsonrpc":"2.0","id":"c05-audited-readonly",
                    "method":method,"params":params or {}},separators=(',',':')).encode(),
   headers={"Content-Type":"application/json"})
 with urllib.request.urlopen(req,timeout=10) as r:
  need(r.status==200,"COMET_RPC_STATUS")
  val=json.load(r)
 need(isinstance(val,dict) and "error" not in val and
      isinstance(val.get("result"),dict),"COMET_RPC_RESPONSE")
 return val["result"]
def run(args,seconds=30):
 p=subprocess.run([str(a) for a in args],capture_output=True,timeout=seconds)
 need(p.returncode==0 and 1<=len(p.stdout)<32768,"NATIVE_BANK_QUERY_FAILED")
 return p.stdout
def main():
 need(sys.platform=="linux" and os.getuid()==0 and os.geteuid()==0,
      "HEL1_ROOT_READONLY_ONLY")
 registered=load_registered_document()
 need(len(registered)==23 and len({a for _,a in registered})==23
     and len({l for l,_ in registered})==23,"EXACT_23_REGISTERED_REQUIRED")
 for label,address in registered:
  need(re.fullmatch(r"[a-z][a-z0-9_]{2,64}",label) is not None
    and re.fullmatch(r"wolo1[023456789acdefghjklmnpqrstuvwxyz]{38}",address) is not None,
    "REGISTERED_ADDRESS_FORMAT")
 need(C01 not in {a for _,a in registered},"FRESH_VAULT_DISJOINT")
 need(NODE.is_file() and os.path.samefile(NODE,"/proc/1009/exe"),
      "RUNNING_NODE_BINARY_NOT_PINNED")
 cmd=Path("/proc/1009/cmdline").read_bytes().split(b"\0")
 need(HOME.encode() in cmd and b"start" in cmd,"LIVE_MAINNET_HOME_IDENTITY")
 need(ROOT.parent==Path("/root") and not ROOT.exists(),"ROOT_PRIVATE_RECEIPT_REPLAY")
 status=rpc("status")
 node=status["node_info"]; sync=status["sync_info"]
 need(node["network"]==CHAIN and sync["catching_up"] is False,
      "CHAIN_NETWORK_OR_SYNC_DRIFT")
 height=int(sync["latest_block_height"])
 need(1000000<height<1000000000,"HEIGHT_OUT_OF_RANGE")
 block=rpc("block",{"height":str(height)})
 header=block["block"]["header"]
 need(header["chain_id"]==CHAIN and int(header["height"])==height,
      "BLOCK_HEADER_CHAIN_DRIFT")
 block_hash=block["block_id"]["hash"]
 need(re.fullmatch(r"[A-Fa-f0-9]{64}",block_hash) is not None,
      "BLOCK_HASH_FORMAT")
 source_names="\n".join(f"{l}|{a}" for l,a in registered)
 wallet_rows=[]
 grand=0
 for index,(label,address) in enumerate(registered+(("c01_new_vault",C01),),1):
  result=run([NODE,"query","bank","balances",address,"--home",HOME,
       "--node","tcp://127.0.0.1:27657","--height",str(height),
       "--output","json"])
  val=json.loads(result)
  bal=val.get("balances")
  need(type(bal) is list,"NATIVE_BANK_BALANCE_NOT_LIST")
  seen=set(); subtotal=0
  for row in bal:
   need(type(row) is dict and set(row)=={"denom","amount"},
        "NATIVE_BANK_DENOM_SCHEMA")
   denom=row["denom"];amt=row["amount"]
   need(denom=="uwolo" and denom not in seen and
        type(amt) is str and re.fullmatch(r"(?:0|[1-9][0-9]{0,38})",amt),
        "NATIVE_BANK_DENOM_OR_AMOUNT")
   seen.add(denom);subtotal+=int(amt)
  wallet_rows.append({"role":label,"public_address":address,
     "balances":bal,"total_uwolo":str(subtotal),
     "current_custody_control_authenticated":False,
     "eligible_unencumbered_collateral_uwolo":"0"})
  grand+=subtotal
  print("C05_PINNED_BANK_QUERIED",index,"of",len(registered)+1,flush=True)
 need(wallet_rows[-1]["total_uwolo"]=="0",
      "C01_FRESH_VAULT_FUNDING_CHANGED_REVIEW")
 ROOT.mkdir(mode=0o700)
 result={
  "schema":"wolo.c05.all-public-23-plus-new-c01-single-height-bank-unfunded.v1",
  "observed_utc":datetime.now(timezone.utc).isoformat(),
  "source_sha256":hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
  "canonical_registered23_sha256":hashlib.sha256((source_names+"\n").encode()).hexdigest(),
  "network":CHAIN,"observed_height":height,
  "local_consensus_block_hash":block_hash,
  "native_executable":str(NODE),"public_wallets":wallet_rows,
  "canonical_registered_wallet_count":23,
  "canonical_source_document_sha256":DOCUMENT_SHA256,
  "new_c01_vault_additional":True,
  "total_all_24_labels_uwolo":str(grand),
  "wallets_overlap_deduped":True,
  "raw_bank_balance_is_not_custody_or_collateral_proof":True,
  "ibc_escrow_and_player_founder_retired_balances_not_eligible":True,
  "actual_eligible_spendable_reserves_proven_uwolo":"0",
  "operator_exclusive_control_verified":False,
  "offhost_consensus_witness_verified":False,
  "economic_liability_id_disjointness_verified":False,
  "global_reserve_surplus_verified":False,
  "c05_gate_closed":False,
  "c09_transaction_authorized":False,
  "production_mutated":False
 }
 blob=(json.dumps(result,sort_keys=True,indent=2)+"\n").encode()
 target=ROOT/"registered24-single-height-native-bank.json"
 fd=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
 with os.fdopen(fd,"wb") as f:f.write(blob);f.flush();os.fsync(f.fileno())
 print("PASS_C05_REGISTERED_23_PLUS_C01_REAL_SAME_HEIGHT_BANK_OBSERVATION")
 print("BANK_HEIGHT",height,"BANK_HEADER_SHA",block_hash)
 print("C01_NEW_VAULT_UNFUNDED",True)
 print("TOTAL_OBSERVED_BALANCES_UWOLO",str(grand))
 print("ROOT_PRIVATE_RECEIPT_SHA256",hashlib.sha256(blob).hexdigest())
 print("HOLD_C05_CUSTODY_LIABILITY_AND_INDEPENDENT_CONSENSUS_WITNESS")
if __name__=="__main__":
 try:main()
 except (Hold,OSError,ValueError,KeyError,TypeError,
         subprocess.SubprocessError,TimeoutError) as err:
  print("HOLD_C05_SINGLE_HEIGHT_REGISTERED_WALLET_OBSERVATION",
        str(err) if isinstance(err,Hold) else "HOST_OR_CHAIN_DATA_ERROR")
  sys.exit(3)

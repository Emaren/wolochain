#!/usr/bin/env python3
"""C03 partial legacy 3030 financial transport isolation, ROOT/HEL1 ONLY.

This confines the legacy UID1000 web/process family from TCP 127.0.0.1
ports 8092 and 8093 via an independent nftables OUTPUT chain. It preserves
the running 3030 PID, 3032, HD/DE API, both Wolo local listeners and the
original public web proxy. It does NOT claim complete finance writer isolation:
legacy direct RPC, CLI, nonlocal targets, all DB write paths and other UIDs
require separately reviewed controls.

Default command is read-only. Actual firewall mutation is deliberately only
--mode=apply and requires the exact source-preimage, process identity,
missing table, original healthy websites, and two live Wolo listeners.
Any negative after deploy deletes only our newly-added table immediately.
This deny stays fail-closed across shell exit; a separately reviewed rollback
procedure is needed to remove it after acceptance. No funded release.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import stat
import subprocess
import sys
from urllib.parse import urlparse

SCHEMA="wolo.c03.legacy-3030-two-loopback-transport-deny-partial.v1"
TABLE="aoe2war_c03_legacy_finance_deny"
ORIGIN_PID=2625090
R25_PID=1766058
OLD_UID=1000
OLD_USER="tony"
OLD_CGROUP="/system.slice/aoe2hdbets-web.service"
R25_UID=990
R25_CGROUP="/system.slice/aoe2hdbets-web-prod.service"
ROOT="/var/www/AoE2HDBets/app-prodn"
ARCHIVE="/var/lib/aoe2war-web-prod-1c4ffe0ce31e"
ACCEPTANCE=Path("/root/aoe2war-c03-legacy-3030-egress-20261107/physical-acceptance.json")
FILES={
 "app/api/admin/wolochain/scheduled-settlements/[id]/execute/route.ts":
 "e6480b742cf3a4fbe4f9d1c15d3d035b39f5636fc1d19c4aa4c718f8f6401352",
 "app/api/admin/wolochain/staking-treasury-payouts/[id]/execute/route.ts":
 "e4080644a7217225ecbc368a15c804a40055fec54a1065cbe33ce4b1da6ae907",
 "lib/woloBetSettlement.ts":
 "32e4a1c6578c6ade539a11da439478faf620ce44e1f1f18a765869fd7a3fcbad",
}
NFT=f"""table inet {TABLE} {{
 chain output {{
  type filter hook output priority -12; policy accept;
  meta skuid {OLD_UID} ip daddr 127.0.0.1 tcp dport {{ 8092, 8093 }} counter reject with tcp reset
 }}
}}
"""
class Hold(RuntimeError):pass
def need(ok,reason):
 if not ok:raise Hold(reason)
def run(argv,*,input=None,timeout=12,check=True):
 p=subprocess.run(argv,input=input,capture_output=True,text=True,timeout=timeout,
                  env={"PATH":"/usr/sbin:/usr/bin:/sbin:/bin","LANG":"C"})
 if check:need(p.returncode==0,"COMMAND_FAILED_"+argv[0].split("/")[-1])
 return p
def sha(data):return hashlib.sha256(data).hexdigest()
def env_of(pid):
 b=Path(f"/proc/{pid}/environ").read_bytes()
 need(len(b)<150000,"UNBOUNDED_ORIGINAL_ENVIRONMENT")
 return dict(x.split(b"=",1) for x in b.split(b"\0") if b"=" in x)
def proc_identity(pid,uid,cgroup):
 st=Path(f"/proc/{pid}/status").read_text()
 v=re.search(r"^Uid:\s+(\d+)",st,re.M)
 need(v and int(v.group(1))==uid,"PROCESS_UID_DRIFT")
 need(Path(f"/proc/{pid}/cgroup").read_text().strip()=="0::"+cgroup,
      "PROCESS_CGROUP_DRIFT")
 need(Path(f"/proc/{pid}/exe").resolve()==Path("/usr/bin/node"),
      "NODE_EXECUTABLE_DRIFT")
 return True
def endpoint(env,key,port):
 value=env.get(key.encode(),b"")
 need(value,"LEGACY_LOCAL_ENDPOINT_UNCONFIGURED")
 try:
  u=urlparse(value.decode("utf-8"))
  need(u.scheme=="http" and u.hostname=="127.0.0.1" and u.port==port
       and not u.query and not u.fragment,"LEGACY_ENDPOINT_CHANGED")
 except (UnicodeError,ValueError) as e:raise Hold("LEGACY_ENDPOINT_UNTRUSTED") from None
def identity():
 need(os.geteuid()==0 and sys.platform=="linux","HEL1_ROOT_ONLY")
 need(proc_identity(ORIGIN_PID,OLD_UID,OLD_CGROUP),"ROLLBACK_IDENTITY_CHANGED")
 need(proc_identity(R25_PID,R25_UID,R25_CGROUP),"R25_IDENTITY_CHANGED")
 env=env_of(ORIGIN_PID)
 endpoint(env,"WOLO_SETTLEMENT_URL",8092)
 endpoint(env,"WOLO_FOUNDER_SETTLEMENT_URL",8093)
 for key in ("WOLO_SETTLEMENT_AUTH_TOKEN","WOLO_FOUNDER_SETTLEMENT_AUTH_TOKEN"):
  need(bool(env.get(key.encode())),"LEGACY_AUTH_MATERIAL_MISSING_"+key)
 r25=env_of(R25_PID)
 need(r25.get(b"WARGRAPH_RUNTIME_DISABLED")==b"true" and
      not r25.get(b"WOLO_SETTLEMENT_URL") and
      not r25.get(b"WOLO_FOUNDER_SETTLEMENT_URL"),"R25_FINANCE_PROFILE_CHANGED")
 need(Path(f"/proc/{ORIGIN_PID}/cwd").resolve()==Path(ROOT),
      "ROLLBACK_WORKTREE_DRIFT")
 need(Path(f"/proc/{R25_PID}/cwd").resolve()==Path(ARCHIVE),
      "R25_WORKTREE_DRIFT")
 for path,expected in FILES.items():
  p=Path(ROOT)/path
  need(p.is_file() and not p.is_symlink() and sha(p.read_bytes())==expected,
       "OLD_FINANCE_HANDLER_SOURCE_CHANGED")
 return True
def websites():
 for p in (3030,3032):
  status=run(["/usr/bin/curl","-sS","--max-time","5","-o","/dev/null",
              "-w","%{http_code}",f"http://127.0.0.1:{p}/"]).stdout
  need(status=="200","WEB_CONTINUITY_"+str(p))
def connect_probe(port,*,actor="root"):
 code=f"import socket,sys\ntry:\n s=socket.create_connection(('127.0.0.1',{port}),timeout=2)\n s.close();sys.exit(0)\nexcept (OSError,TimeoutError):sys.exit(3)\n"
 args=["/usr/bin/python3","-I","-B","-c",code]
 if actor=="tony":args=["/usr/sbin/runuser","-u",OLD_USER,"--"]+args
 return run(args,timeout=5,check=False).returncode==0
def verify_rule():
 p=run(["/usr/sbin/nft","-a","list","table","inet",TABLE])
 s=p.stdout
 need("type filter hook output priority -12;" in s and "policy accept;" in s,
      "NFT_HOOK_SCOPE_DRIFT")
 need(f"meta skuid {OLD_UID} ip daddr 127.0.0.1" in s and
      "tcp dport { 8092, 8093 }" in s and
      "reject with tcp reset" in s,"NFT_LEGACY_PORT_DENY_MISSING")
 need(s.count("meta skuid")==1,"NFT_UNEXPECTED_AUTHORITY")
def no_table():
 p=run(["/usr/sbin/nft","list","table","inet",TABLE],check=False)
 need(p.returncode!=0,"NFT_TABLE_ALREADY_PRESENT_REVIEW_REQUIRED")
def audit(mode):
 identity()
 websites()
 if mode=="inspect":
  no_table()
  run(["/usr/sbin/nft","-c","-f","/dev/stdin"],input=NFT)
  need(connect_probe(8092) and connect_probe(8093),
       "LOCAL_WOLO_LISTENER_NOT_AVAILABLE")
  return {"status":"PASS_C03_LEGACY_TWO_PORT_DENY_PREFLIGHT_NOT_INSTALLED"}
 verify_rule()
 need(connect_probe(8092) and connect_probe(8093),
      "LOCAL_WOLO_LISTENER_BROKEN")
 need(not connect_probe(8092,actor="tony") and not connect_probe(8093,actor="tony"),
      "OLD_UID_STILL_REACHES_FINANCE_TRANSPORT")
 websites()
 return {"status":"PASS_C03_TWO_PORT_LEGACY_DENY_ONLY_NOT_GLOBAL_FINANCE_FENCE"}
def apply():
 no_table()
 need(not ACCEPTANCE.exists(),"PREVIOUS_RECEIPT_REVIEW_REQUIRED")
 audit("inspect")
 # Prove old UID could reach both live listeners BEFORE installing this deny.
 need(connect_probe(8092,actor="tony") and connect_probe(8093,actor="tony"),
      "OLD_UID_ALREADY_BLOCKED_UNRELATED_DENIAL")
 need(ACCEPTANCE.parent.exists() and
      not ACCEPTANCE.parent.is_symlink() and
      ACCEPTANCE.parent.stat().st_uid==0 and
      stat.S_IMODE(ACCEPTANCE.parent.stat().st_mode)==0o700,
      "ROOT_PROTECTED_RECEIPT_DIRECTORY_REQUIRED")
 installed=False
 try:
  run(["/usr/sbin/nft","-f","/dev/stdin"],input=NFT)
  installed=True
  data=audit("verify")
  data.update({
   "schema":SCHEMA,"timestamp_utc":datetime.now(timezone.utc).isoformat(),
   "legacy_pid":ORIGIN_PID,"legacy_uid":OLD_UID,
   "protected_pid":R25_PID,"protected_uid":R25_UID,
   "nft_rules_source_sha256":sha(NFT.encode()),
   "production_http_3030_and_3032_preserved":True,
   "legacy_two_loopback_finance_ports_denied":True,
   "existing_chain_validator_ports_8092_8093_preserved":True,
   "financial_scope_complete":False,
   "direct_chain_rpc_cli_and_signer_fenced":False,
   "all_database_writers_fenced":False,
   "live_c03_gate_accepted":False,
   "coordinated_c06_capture_authorized":False,
   "funded_release_authorized":False,
  })
  raw=(json.dumps(data,sort_keys=True,indent=2)+"\n").encode()
  fd=os.open(ACCEPTANCE,os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_WRONLY,0o600)
  with os.fdopen(fd,"wb") as f:
   f.write(raw);f.flush();os.fsync(f.fileno())
  print("PHYSICAL_ACCEPTANCE_SHA256",sha(raw))
  return data
 except Exception:
  if installed:
   run(["/usr/sbin/nft","delete","table","inet",TABLE],check=False)
  raise
def main():
 a=argparse.ArgumentParser()
 a.add_argument("--mode",choices=("inspect","verify","apply"),default="inspect")
 mode=a.parse_args().mode
 try:
  result=apply() if mode=="apply" else audit(mode)
  print(json.dumps(result,sort_keys=True))
  return 0 if mode!="verify" or result["status"].startswith("PASS_") else 3
 except (Hold,OSError,subprocess.TimeoutExpired,ValueError) as e:
  print(json.dumps({"schema":SCHEMA,"status":"HOLD","reason":str(e)[:110],
          "live_c03_gate_accepted":False,"funded_release_authorized":False},
          sort_keys=True))
  return 3
if __name__=="__main__":sys.exit(main())

#!/usr/bin/env python3
"""Read-only C03 host transport witness. NEVER a financial fencing authority.

Prove that existing UID1000 egress denial on 8092/8093 does not certify
root-owned 8092/8093 writers or UID1000's direct 1318/27657 reachability.
Connect-only TCP tests send exactly ZERO application bytes. The only
successful observation exits 3/HOLD, never PASS or release authority.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
from datetime import datetime, timezone

SCHEMA = "wolo.c03.root-finance-transport-connect-only-hold.v1"
HOST = "ubuntu-4gb-hel1-11"
PORT_UNIT = {
    8092: "wolochain-mainnet-settlement.service",
    8093: "wolochain-founder-rewards-settlement.service",
    1318: "wolochaind-mainnet.service",
    27657: "wolochaind-mainnet.service",
}
FUNDED = (8094, 8095)
MAX_BYTES = 16384

class Hold(ValueError):
    pass

def require(condition, message):
    if not condition:
        raise Hold(message)

def run(argv, *, seconds=6):
    p = subprocess.run(argv, text=True, capture_output=True, timeout=seconds)
    require(p.returncode == 0 and not p.stderr.strip()
            and len(p.stdout.encode()) <= MAX_BYTES,
            "READ_ONLY_COMMAND_UNAVAILABLE")
    return p.stdout

def parse_units(raw, unit):
    vals = {}
    for line in raw.splitlines():
        require("=" in line, "UNIT_PROPERTY_SHAPE")
        k,v = line.split("=",1)
        require(k in ("Id","ActiveState","MainPID") and k not in vals,
                "UNIT_PROPERTY_UNKNOWN_OR_DUPLICATE")
        vals[k] = v
    require(set(vals)=={"Id","ActiveState","MainPID"} and
            vals["Id"]==unit and vals["ActiveState"] in ("active","inactive","failed") and
            vals["MainPID"].isdigit(), "UNIT_IDENTITY_DRIFT")
    return vals

def parse_ss(raw):
    listeners={}
    for line in raw.splitlines():
        f=line.split()
        require(len(f)>=5 and f[0]=="LISTEN","LISTENER_SHAPE")
        endpoint=f[3]
        require(":" in endpoint,"LISTENER_ENDPOINT")
        suffix=endpoint.rsplit(":",1)[1]
        if not suffix.isdigit():
            continue
        port=int(suffix)
        if port not in PORT_UNIT and port not in FUNDED:
            continue
        require(endpoint==f"127.0.0.1:{port}" and port not in listeners,
                "UNEXPECTED_FINANCIAL_LISTENER_BIND_OR_DUPLICATE")
        pids=re.findall(r"pid=(\d+)",line)
        require(len(pids)==1 and int(pids[0])>0,"PORT_PID_MISSING_OR_AMBIGUOUS")
        listeners[port]=int(pids[0])
    require(not any(p in listeners for p in FUNDED),
            "FUNDED_PORT_ACTIVE_STOP")
    return listeners

def parse_uid(raw):
    match=re.search(r"^Uid:\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s*$",
                    raw,re.MULTILINE)
    require(match is not None,"OWNER_EFFECTIVE_UID_MISSING")
    return tuple(int(x) for x in match.groups())

def net_connect(port, user):
    require(port in PORT_UNIT and user in ("root","tony"),
            "UNREVIEWED_NETWORK_PROBE")
    code=("import socket,sys;"
          "s=socket.socket();s.settimeout(1);"
          "x=s.connect_ex(('127.0.0.1',int(sys.argv[1])));"
          "s.close();print('1' if x==0 else '0')")
    argv=["/usr/bin/python3","-I","-B","-c",code,str(port)]
    if user=="tony":
        argv=["/usr/sbin/runuser","-u","tony","--"]+argv
    r=run(argv,seconds=4).strip()
    require(r in ("0","1"),"CONNECT_PROBE_RETURN_SHAPE")
    return r=="1"

def observe():
    require(os.geteuid()==0 and sys.platform=="linux" and
            socket.gethostname()==HOST,"ROOT_ON_EXACT_HEL1_REQUIRED")
    require(run(["/usr/bin/id","-u","tony"]).strip()=="1000",
            "LEGACY_WEB_UID_DRIFT")
    listener=parse_ss(run(["/usr/bin/ss","-ltnpH"]))
    unit_names=sorted(set(PORT_UNIT.values()))
    units={}
    for unit in unit_names:
        vals=parse_units(run(["/usr/bin/systemctl","show","--no-pager",
                              "-p","Id,ActiveState,MainPID","--",unit]),unit)
        units[unit]=vals
    identities={}
    for port,unit in sorted(PORT_UNIT.items()):
        pid=listener.get(port)
        vals=units[unit]
        if pid is None:
            identities[str(port)]={"listening":False,"root_owned":False,
                                   "same_as_systemd_main_pid":False}
            continue
        require(vals["ActiveState"]=="active" and str(pid)==vals["MainPID"],
                "FINANCE_LISTENER_NOT_REVIEWED_SYSTEMD_PROCESS")
        uids=parse_uid(Path(f"/proc/{pid}/status").read_text())
        identities[str(port)]={"listening":True,"root_owned":uids[0]==0 and uids[1]==0,
                               "same_as_systemd_main_pid":True}
    nft=run(["/usr/sbin/nft","list","chain","inet",
             "aoe2war_c03_legacy_finance_deny","output"])
    nft_partial=all(t in nft for t in ("meta skuid 1000",
                                        "8092, 8093","reject"))
    reach={}
    for user in ("root","tony"):
        reach["UID0" if user=="root" else "UID1000"]={
            str(port):net_connect(port,user) for port in PORT_UNIT}
    return {
        "schema":SCHEMA,
        "observed_utc":datetime.now(timezone.utc).isoformat(),
        "status":"HOLD_C03_ROOT_AND_DIRECT_RPC_FINANCE_WRITERS_UNCONTAINED",
        "only_transport_tcp_connects_no_requests":True,
        "bytes_sent_to_financial_services":0,
        "protected_two_systemd_web_units_unchanged_by_observer":True,
        "funded_8094_8095_off":True,
        "uid1000_partial_8092_8093_kernel_deny":nft_partial,
        "listener_systemd_process_identity":identities,
        "loopback_connect_reachability":reach,
        "root_owned_services_transferred_or_stopped":False,
        "complete_pg_financial_writer_fence_proven":False,
        "external_signer_and_cli_fenced":False,
        "financial_release_authorized":False,
        "production_modified":False,
    }

def main():
    try:
        print(json.dumps(observe(),sort_keys=True))
        return 3
    except (Hold,OSError,subprocess.SubprocessError,UnicodeError) as e:
        reason=str(e) if isinstance(e,Hold) else "HOST_OBSERVATION_UNAVAILABLE"
        print(json.dumps({"schema":SCHEMA,"status":"STOP",
                          "reason":reason,
                          "financial_release_authorized":False,
                          "production_modified":False},sort_keys=True))
        return 2

if __name__=="__main__":
    sys.exit(main())

"""Native systemd barrier building block for coordinated C06, source only.

The complete protected driver must authenticate and consume the expanded
capture/resume packet with the independently enrolled witness before use.
No CLI, no automatic resume, no admission from an environment flag. This
does not fence direct privileged processes, external signers or non-systemd
schedulers; those remain separately admitted hard prerequisites.
"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
from settlement_c06_checkpoint_rehearsal import require, canonical, digest
from settlement_financial_maintenance import no_jobs, show

HOLD = Path("/etc/wolochain-financial-maintenance/C06-COORDINATED-HOLD")
SYSTEMD = Path("/etc/systemd/system")
DROPIN = "91-wolo-c06-coordinated.conf"
UNIT = re.compile(r"[A-Za-z0-9_.@-]+\.(service|timer|socket|path)\Z")
QUARANTINED = frozenset({
    "aoe2hdbets-bet-stake-reconcile.timer",
    "aoe2hdbets-bet-stake-reconcile.service",
    "aoe2hdbets-staking-rewards.timer",
    "aoe2hdbets-staking-rewards.service",
    "wolochain-mainnet-settlement.service",
    "wolochain-founder-rewards-settlement.service",
})
# Always preserve independent Traffic ingestion and the scheduling daemon.
NEVER_STOP = frozenset({"cron.service","atd.service","nginx.service"})
REQUIRED = frozenset({"postgresql.service","postgresql@16-main.service",
    "wolochaind-mainnet.service","aoe2hdbets-web-prod.service",
    "aoe2hdbets-web.service","aoe2hdbets-api.service",
    "aoe2hdbets-web-r24.service","aoe2hdbets-web-candidate-3033.service",
    "aoe2dewarwagers-api.service","aoe2dewarwagers-web.service",
    "aoe2war-appearance-writer.service","aoe2war-social-writer.service",
    "tokenchain-hasura.service","tokenchain-indexer.service","tokenchain-web.service"})

# Confirmed unit-file identities on HEL1; disabled is not an activation fence.
# These dormant financial/chain producers must never be resumed by C06.
DORMANT_DENY = frozenset({"aoe2hdbets-bet-stake-reconcile-plan.service",
    "wolochain-mainnet-osmosis-relayer.service","wolochain-settlement.service",
    # Native HEL1 Nov24 readback: loaded, inactive, MainPID=0. Inactive
    # custody/signing and alternate chain/website units are not safe to start.
    "wolo-satchel-c01.service","wolo-reviewer-c01.service",
    "tokenchain-callisto.service","tokenchain-faucet.service",
    "tokenchain-daily-allocation.service","tokenchain-daily-allocation.timer",
    "tokenchain-osmo-ibc-bootstrap.service","tokenchain-osmo-ibc-bootstrap.timer",
    "tokenchain-relayer.service","aoe2war-r25-f7fdae2-candidate.service"})
# Observed enabled timers and their static service targets. Stopping only
# the website/PG leaves these scheduled activation paths open.
SCHEDULED_PRODUCERS = frozenset(
    name+suffix for name in (
        "aoe2-wolo-transfer-heartbeat","aoe2hdbets-challenge-reconcile",
        "aoe2hdbets-replay-auto-recovery","aoe2hdbets-trophy-tributes",
        "aoe2war-prewarm")
    for suffix in (".timer",".service"))
REQUIRED = REQUIRED | DORMANT_DENY | SCHEDULED_PRODUCERS
PG_UNITS = frozenset({"postgresql.service","postgresql@16-main.service"})
PG_CLIENTS = REQUIRED - PG_UNITS - {"wolochaind-mainnet.service"}

def validate_scope(scope):
    require(type(scope) is dict and set(scope)=={"stop","resume","prestate"},
            "SERVICE_SCOPE_SCHEMA")
    stop,resume=scope["stop"],scope["resume"]
    require(type(stop) is list and type(resume) is list and
        all(type(u) is str and UNIT.fullmatch(u) for u in stop+resume) and
        len(stop)==len(set(stop)) and len(resume)==len(set(resume)) and
        REQUIRED<=set(stop) and set(resume)<=set(stop) and
        not (set(stop)&(QUARANTINED|NEVER_STOP)) and
        not any(u.startswith("traffic-") for u in stop),
        "UNSAFE_OR_INCOMPLETE_SERVICE_SCOPE")
    require(type(scope["prestate"]) is dict and set(scope["prestate"])==set(stop),
            "PRESTATE_SCOPE")
    for u,fields in scope["prestate"].items():
        require(type(fields) is dict and fields.get("Id")==u and
            fields.get("LoadState")=="loaded" and
            fields.get("ActiveState") in ("active","inactive"),
            "UNKNOWN_OR_TRANSITIONAL_SERVICE_STATE")
    require(set(resume)=={u for u in stop if scope["prestate"][u]["ActiveState"]=="active"},
            "RESUME_MUST_MATCH_ORIGINAL_ACTIVE_SET")
    require(not (set(resume)&DORMANT_DENY),"DORMANT_FINANCIAL_PRODUCER_ACTIVE")
    # Explicit dependency ordering for the whole shared cluster, including
    # both preserved fallback runtimes. Stopping does not delete either.
    require(all(stop.index(u)<stop.index(pg) for u in PG_CLIENTS for pg in PG_UNITS),
            "PG_STOP_ORDER")
    if "postgresql@16-main.service" in resume:
        for u in PG_CLIENTS:
            if u in resume:require(resume.index(u)>resume.index("postgresql@16-main.service"),"PG_RESUME_ORDER")
    for u in stop:
        if u.endswith((".timer",".socket",".path")):
            require(all(stop.index(u)<stop.index(s) for s in stop if s.endswith(".service")),
                    "ACTIVATOR_STOP_ORDER")
    for u in resume:
        if u.endswith((".timer",".socket",".path")):
            require(all(resume.index(u)>resume.index(s) for s in resume if s.endswith(".service")),
                    "ACTIVATOR_RESUME_ORDER")
    return digest(canonical(scope))

def native_run(argv):
    require(os.geteuid()==0,"ROOT_REQUIRED")
    p=subprocess.run(argv,capture_output=True,text=True,timeout=45,check=True,
        env={"PATH":"/usr/sbin:/usr/bin:/sbin:/bin","LANG":"C"})
    return p.stdout

def gate_bytes(hold):
    return ("# C06 coordinated checkpoint; no automatic resume\n"
            "[Unit]\nConditionPathExists=!"+str(hold)+"\n").encode()

def sync_dir(path):
    fd=os.open(path,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:os.fsync(fd)
    finally:os.close(fd)

def new_root_file(path,data):
    require(os.geteuid()==0,"ROOT_REQUIRED")
    for parent in path.parents:
        s=parent.lstat()
        require(stat.S_ISDIR(s.st_mode) and s.st_uid==0 and
                not s.st_mode&0o022,"UNSAFE_PARENT")
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,"wb") as out:
        out.write(data);out.flush();os.fsync(out.fileno())
    sync_dir(path.parent)

def exact_root_file(path,expected):
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(fd,"rb") as f:
        s=os.fstat(f.fileno())
        require(stat.S_ISREG(s.st_mode) and s.st_uid==0 and s.st_nlink==1
                and stat.S_IMODE(s.st_mode)==0o600 and s.st_size==len(expected)
                and f.read(len(expected)+1)==expected,"OWNED_GATE_DRIFT")

def effective_gate(unit,hold,run):
    obj=json.loads(run(["busctl","--system","--json=short","call",
        "org.freedesktop.systemd1","/org/freedesktop/systemd1",
        "org.freedesktop.systemd1.Manager","LoadUnit","s",unit]))
    require(obj.get("type")=="o" and type(obj.get("data")) is list and len(obj["data"])==1
        and re.fullmatch(r"/org/freedesktop/systemd1/unit/[A-Za-z0-9_]+",obj["data"][0]),
        "UNIT_DBUS_IDENTITY")
    cond=json.loads(run(["busctl","--system","--json=short","get-property",
        "org.freedesktop.systemd1",obj["data"][0],"org.freedesktop.systemd1.Unit","Conditions"]))
    require(cond.get("type")=="a(sbbsi)" and
        any(type(x) is list and len(x)==5 and x[:4]==["ConditionPathExists",False,True,str(hold)]
            for x in cond.get("data",[])),"C06_GATE_NOT_EFFECTIVE")

class NativeBarrier:
    """Actual systemd operations; library only, no production dispatcher.

    Native admission is deliberately injected at the integration boundary.
    It must revalidate the real signed phase and external lease before every
    effect, and durably anchor every intent. A structural packet is not enough.
    """
    def __init__(self,scope,*,admit_effect,anchor_intent,complete_effect=None,run=native_run):
        self.scope=scope
        self.sha=validate_scope(scope)
        self.admit_effect=admit_effect
        self.anchor_intent=anchor_intent
        self.complete_effect=complete_effect
        self.run=run
        self.marker=canonical({"schema":"wolo.c06.native-hold.v1","scope":self.sha})

    def gate(self,u):return SYSTEMD/(u+".d")/DROPIN

    def effect(self,phase,action,fn):
        require(validate_scope(self.scope)==self.sha,"SCOPE_DRIFT")
        # Both must raise on refusal. There is no retry on an ambiguous effect.
        self.admit_effect(phase,self.sha,action)
        self.anchor_intent(phase,self.sha,action)
        self.admit_effect(phase,self.sha,action)
        result=fn()
        if self.complete_effect is not None:
            self.complete_effect(phase,self.sha,action)
        return result

    def check_quarantine(self):
        for u in sorted(QUARANTINED):
            raw=self.run(["systemctl","show","--no-pager",
                    "--property=Id,ActiveState,UnitFileState","--",u])
            fields=dict(s.split("=",1) for s in raw.splitlines())
            require(fields.get("Id")==u and fields.get("ActiveState")=="inactive"
                and fields.get("UnitFileState")=="masked","QUARANTINE_DRIFT")

        # Unlike the six masked units, these two installed successors were
        # static/inactive, so their inactive state is independently checked
        # throughout the capture and selective release sequence.
        for u in ("wolo-satchel-c01.service","wolo-reviewer-c01.service"):
            fields=show(u,self.run)
            require(fields.get("Id")==u and fields.get("ActiveState")=="inactive"
                    and fields.get("MainPID")=="0","CUSTODY_OR_REVIEWER_ACTIVATED")
        # Check actual TCP listeners, not a firewall assertion or service name.
        listeners=self.run(["ss","-H","-ltn"])
        for line in listeners.splitlines():
            fields=line.split()
            require(len(fields)>=5 and fields[0]=="LISTEN","SOCKET_OBSERVATION_INVALID")
            port=fields[3].rsplit(":",1)[-1]
            require(port.isdecimal(),"SOCKET_PORT_UNQUALIFIED")
            require(int(port) not in range(8092,8096),"FINANCIAL_LISTENER_PRESENT")

    def fence(self):
        require(os.geteuid()==0,"ROOT_REQUIRED")
        self.check_quarantine()
        no_jobs(self.run)
        require(not os.path.lexists(HOLD),"EXISTING_HOLD_RECONCILE")
        for u in self.scope["stop"]:
            require(show(u,self.run)==self.scope["prestate"][u],"PRESTATE_DRIFT")
            require(not os.path.lexists(self.gate(u)),"FOREIGN_GATE")
        self.effect("capture","hold",lambda:new_root_file(HOLD,self.marker))
        for u in self.scope["stop"]:
            path=self.gate(u)
            def install():
                path.parent.mkdir(mode=0o755,exist_ok=True)
                new_root_file(path,gate_bytes(HOLD))
            self.effect("capture","gate:"+u,install)
        self.effect("capture","reload",lambda:self.run(["systemctl","daemon-reload"]))
        for u in self.scope["stop"]:effective_gate(u,HOLD,self.run)
        for u in self.scope["stop"]:
            self.effect("capture","stop:"+u,lambda:self.run(["systemctl","stop","--",u]))
        return self.verify_fenced()

    def verify_fenced(self):
        exact_root_file(HOLD,self.marker)
        no_jobs(self.run);self.check_quarantine()
        observed={}
        for u in self.scope["stop"]:
            exact_root_file(self.gate(u),gate_bytes(HOLD))
            effective_gate(u,HOLD,self.run)
            s=show(u,self.run)
            require(s.get("ActiveState")=="inactive" and s.get("MainPID","0")=="0"
                    and str(self.gate(u)) in s.get("DropInPaths","").split(),"NOT_FENCED")
            group=s.get("ControlGroup","")
            if group:
                require(group.startswith("/") and ".." not in Path(group).parts,"CGROUP_PATH")
                events=Path("/sys/fs/cgroup")/group.lstrip("/")/"cgroup.events"
                require(events.is_file() and "populated 0" in events.read_text().splitlines(),
                        "PRODUCER_CGROUP_POPULATED")
            observed[u]=s
        no_jobs(self.run)
        return digest(canonical(observed))

    def resume(self):
        """Separate authenticated resume only. Never starts a quarantined unit.

        No automatic cleanup if gate removal/start is interrupted. The external
        driver must first verify actual capture/recovery, absence of other
        activation paths, dependencies and its exact signed restart plan.
        """
        self.verify_fenced()
        # Release only one exact unit at a time. The hold remains until
        # every authorized restart and every original inactive-unit release
        # has been recorded. A crash cannot release the remaining units.
        pending=set(self.scope["stop"])
        def release(u):
            path=self.gate(u)
            def remove():
                exact_root_file(path,gate_bytes(HOLD));path.unlink();sync_dir(path.parent)
            self.effect("resume","remove:"+u,remove)
            self.effect("resume","reload:"+u,lambda:self.run(["systemctl","daemon-reload"]))
            pending.remove(u)
            for other in sorted(pending):
                effective_gate(other,HOLD,self.run)
                s=show(other,self.run)
                require(s.get("ActiveState")=="inactive" and s.get("MainPID","0")=="0",
                        "PENDING_SERVICE_ACTIVATED")
        for u in self.scope["resume"]:
            self.check_quarantine()
            release(u)
            self.effect("resume","start:"+u,lambda:self.run(["systemctl","start","--",u]))
            require(show(u,self.run).get("ActiveState")=="active","RESTART_POSTSTATE")
        for u in self.scope["stop"]:
            if u not in self.scope["resume"]:
                self.check_quarantine()
                release(u)
                require(show(u,self.run).get("ActiveState")=="inactive","UNEXPECTED_ACTIVATION")
        require(not pending,"UNRELEASED_GATES")
        def remove_marker():
            exact_root_file(HOLD,self.marker);HOLD.unlink();sync_dir(HOLD.parent)
        self.effect("resume","release-hold",remove_marker)
        self.check_quarantine();no_jobs(self.run)
        result={u:show(u,self.run) for u in self.scope["stop"]}
        require(all(s.get("ActiveState")==self.scope["prestate"][u]["ActiveState"]
                    for u,s in result.items()),"SERVICE_POSTSTATE_DRIFT")
        return digest(canonical(result))

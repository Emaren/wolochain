"""Protected expanded-C06 witness transport/dispatcher source.

No installer or enrollment writer. Existing legacy forced command is untouched.
Both endpoints must receive independently approved exact source/plan enrollment;
the same legacy nonce store is mandatory. No live driver activation here.
"""
from __future__ import annotations
import base64
import hashlib
import os
from pathlib import Path
import stat
import subprocess
import sys

import settlement_solo_owner_intent_review as owner
import settlement_solo_runtime as legacy
import settlement_c06_checkpoint_authority as authority
from settlement_c06_checkpoint_coordinator import Journal, validate_plan
from settlement_c06_checkpoint_rehearsal import canonical, digest, hash64

SCHEMA = "wolo.c06.native-witness-enrollment.v1"
COMMAND = "wolo-c06-expanded-witness-v1"
MAX_REQUEST = 131071
SOURCES = legacy.SOURCES | frozenset({
    "settlement_c06_native_witness.py",
    "settlement_c06_checkpoint_authority.py",
    "settlement_c06_checkpoint_coordinator.py",
    "settlement_c06_checkpoint_rehearsal.py",
    "settlement_c06_native_service_barrier.py",
    "settlement_c06_native_pg_checkpoint.py",
    "settlement_c06_image_stream.py",
})
require = owner.require


def load_expanded(raw, old_raw):
    c = owner.parse(raw)
    old = legacy.load_config(old_raw)
    require(set(c) == {"schema", "source_commit", "plan_sha256",
                       "legacy_enrollment_sha256", "controller_files"}
            and c["schema"] == SCHEMA
            and type(c["source_commit"]) is str
            and owner.HEX40.fullmatch(c["source_commit"])
            and c["source_commit"] != "0"*40
            and hash64(c["plan_sha256"])
            and c["legacy_enrollment_sha256"] == digest(old_raw)
            and type(c["controller_files"]) is dict
            and set(c["controller_files"]) == SOURCES
            and all(hash64(v) for v in c["controller_files"].values())
            and all(c["controller_files"][k]==v for k,v in old["controller_files"].items()),
            "C06_EXPANDED_ENROLLMENT_INVALID")
    return c, old


def source_pins(c):
    for name, expected in c["controller_files"].items():
        p = Path(__file__).resolve().with_name(name)
        require(p.resolve(strict=True) == p, "C06_SOURCE_PATH_DRIFT")
        fd = os.open(p, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, "rb") as f:
            s = os.fstat(f.fileno())
            require(stat.S_ISREG(s.st_mode) and s.st_uid in {0,os.geteuid()}
                    and not s.st_mode & 0o022 and s.st_nlink == 1
                    and 0 < s.st_size <= legacy.MAX_PINNED_CONTROLLER_SOURCE_BYTES,
                    "C06_SOURCE_UNSAFE")
            require(hashlib.file_digest(f,"sha256").hexdigest() == expected,
                    "C06_SOURCE_PIN_DRIFT")
            t = os.fstat(f.fileno())
            require((s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
                    == (t.st_dev,t.st_ino,t.st_size,t.st_mtime_ns,t.st_ctime_ns),
                    "C06_SOURCE_CHANGED")


def bindings(c, old, *, witness):
    identity = legacy.host_identity()
    expected = old["witness"]["host_identity_sha256"] if witness else old["host_identity_sha256"]
    require(identity == expected, "C06_NATIVE_HOST_DRIFT")
    source_pins(c)
    return dict(source_commit=c["source_commit"],
                enrollment_pin=old["owner_enrollment_sha256"],
                owner_pin=old["owner_der_sha256"],
                openssl_path=legacy.crypto_path(old,witness=witness))


def check_plan(c,old,plan):
    require(validate_plan(plan) == c["plan_sha256"]
            and plan["host"] == old["host_identity_sha256"],
            "C06_NATIVE_PLAN_DRIFT")


def request(raw):
    require(0 < len(raw) <= MAX_REQUEST, "C06_WITNESS_INPUT_LIMIT")
    r = owner.parse(raw)
    require(type(r) is dict and r.get("action") in ("consume","anchor"),
            "C06_WITNESS_ACTION")
    expected = ({"action","plan","phase","previous","packet_b64"}
                if r["action"] == "consume" else {"action","plan","record"})
    require(set(r)==expected, "C06_WITNESS_REQUEST_SCHEMA")
    if r["action"]=="consume":
        require(r["phase"] in authority.PHASE_STEPS, "C06_WITNESS_PHASE")
        p = base64.b64decode(r["packet_b64"],validate=True)
        require(0 < len(p) <= MAX_REQUEST, "C06_PACKET_LIMIT")
    return r


def verify_anchor_ack(ack,record,witness_identity):
    expected = dict(schema=authority.ANCHOR_SCHEMA, plan=record["plan"],
                    step=record["step"], tip=digest(canonical(record)),
                    witness_identity=witness_identity,
                    status="EXISTING_TIP_READBACK" if record["step"] in authority.ADMISSION_STEPS
                    else "NEW_TIP_ANCHORED",
                    production_authorized=False,funding_authorized=False)
    require(type(ack) is dict and canonical(ack)==canonical(expected),
            "C06_NATIVE_ANCHOR_ACK_DRIFT_OR_REPLAY")
    return expected["tip"]


def dispatch(raw,c,old,enrollment,journal,nonce_root,crypto):
    """Only called after native host/source/plan enrollment readback."""
    r=request(raw); plan=r["plan"]; check_plan(c,old,plan)
    identity=old["witness"]["host_identity_sha256"]
    bound=dict(local_identity=identity,witness_identity=identity,
               source_identity=old["host_identity_sha256"],
               expected_plan_sha=c["plan_sha256"])
    if r["action"]=="consume":
        return authority.consume_expanded_witness(enrollment,
            base64.b64decode(r["packet_b64"],validate=True),plan,
            phase=r["phase"],previous=r["previous"],journal=journal,
            nonce_root=nonce_root,**bound,**crypto)
    return authority.anchor_witness_record(journal,r["record"],plan=plan,**bound)


def native_exchange(old,payload):
    """Same protected SSH route, fixed new protocol command, never fallback."""
    from settlement_financial_maintenance import private_read,run
    w=old["witness"]
    require(digest(private_read(w["known_hosts_path"]))==w["known_hosts_sha256"],
            "WITNESS_SSH_HOST_KEY_DRIFT")
    p=Path(w["identity_path"]); s=p.lstat()
    require(p==p.resolve(strict=True) and stat.S_ISREG(s.st_mode)
            and s.st_uid==0 and stat.S_IMODE(s.st_mode)==0o600 and s.st_nlink==1,
            "WITNESS_TRANSPORT_IDENTITY_UNSAFE")
    argv=["/usr/bin/ssh","-F","/dev/null","-T","-oBatchMode=yes",
          "-oStrictHostKeyChecking=yes","-oGlobalKnownHostsFile=/dev/null",
          "-oUserKnownHostsFile="+w["known_hosts_path"],"-oIdentitiesOnly=yes",
          "-oConnectionAttempts=1","-oConnectTimeout=5","-oForwardAgent=no",
          "-oClearAllForwardings=yes","-p",str(w["port"]),"-i",str(p),
          w["user"]+"@"+w["host"],COMMAND]
    try:
        raw=run(argv,input=canonical(payload),timeout=10)
        require(0<len(raw)<4096,"C06_WITNESS_RESPONSE_LIMIT")
        return owner.parse(raw)
    except (OSError,ValueError,RuntimeError,subprocess.SubprocessError) as exc:
        raise owner.AuthorityHold("C06_WITNESS_OUTCOME_UNCERTAIN_NO_RETRY") from exc


class NativeWitnessClient:
    """Coordinator client; only protected on-host reads, no caller ACK files."""
    def __init__(self,plan):
        require(os.geteuid()==0,"C06_SOURCE_ROOT_REQUIRED")
        self.plan=plan
        self.expanded=legacy.CONFIG.with_name("c06-expanded-runtime.json")
        self.raw=legacy.private_file(self.expanded)
        self.oldraw=legacy.private_file(legacy.CONFIG)
        self.enrollment=legacy.private_file(legacy.ENROLLMENT)
        self.c,self.old=load_expanded(self.raw,self.oldraw)
        self.check()

    def check(self):
        require(legacy.private_file(self.expanded)==self.raw
                and legacy.private_file(legacy.CONFIG)==self.oldraw
                and legacy.private_file(legacy.ENROLLMENT)==self.enrollment,
                "C06_NATIVE_ENROLLMENT_CHANGED")
        check_plan(self.c,self.old,self.plan)
        return bindings(self.c,self.old,witness=False)

    def consume(self,packet,phase,previous):
        crypto=self.check()
        authority.review(self.enrollment,packet,self.plan,
                         phase=phase,previous=previous,**crypto)
        ack=native_exchange(self.old,dict(action="consume",plan=self.plan,
            phase=phase,previous=previous,packet_b64=base64.b64encode(packet).decode()))
        self.check()
        return authority.verify_expanded_witness_ack(ack,self.enrollment,packet,
            self.plan,phase=phase,previous=previous,
            witness_identity=self.old["witness"]["host_identity_sha256"],**crypto)

    def anchor(self,record):
        self.check()
        require(record["plan"]==self.c["plan_sha256"],"C06_ANCHOR_PLAN_DRIFT")
        ack=native_exchange(self.old,dict(action="anchor",plan=self.plan,record=record))
        self.check()
        return verify_anchor_ack(ack,record,self.old["witness"]["host_identity_sha256"])


class CoordinatorWitnessBinding:
    """Native coordinator authority seam. No effects, lease issuer or installer.

    Packet files are pre-existing root-private, exact-plan, owner-signed
    inputs. No caller-provided ACK, arbitrary packet path or fallback route.
    The coordinator remains fixture-gated until the full native driver,
    producer exclusion, effect anchoring and external lease are admitted.
    """
    def __init__(self,plan,journal):
        require(os.geteuid()==0,"C06_SOURCE_ROOT_REQUIRED")
        self.sha=validate_plan(plan)
        self.j=journal
        self.client=NativeWitnessClient(plan)
        self.attempted=set()
        self.anchored=set()
        self.check_journal()

    def check_journal(self):
        require(self.j.fd is not None and self.j.lock is not None
                and self.j.plan_sha==self.sha and self.j.read()==self.j.records,
                "C06_SOURCE_JOURNAL_DRIFT")

    def authenticate_and_consume(self,phase,plan,previous):
        self.check_journal()
        require(validate_plan(plan)==self.sha and self.j.tip==previous
                and phase in authority.PHASE_STEPS and phase not in self.attempted,
                "C06_SOURCE_PHASE_BINDING")
        before,_=authority.PHASE_STEPS[phase]
        require((self.j.records[-1]["step"] if self.j.records else None)==before,
                "C06_SOURCE_PHASE_ORDER")
        packet_path=legacy.CONFIG.parent/"c06-expanded-packets"/self.sha/(phase+".json")
        packet=legacy.private_file(packet_path)
        # An uncertain witness outcome is never retried within this binding.
        self.attempted.add(phase)
        receipt=self.client.consume(packet,phase,previous)
        self.check_journal()
        require(self.j.tip==previous,"C06_SOURCE_PHASE_JOURNAL_CHANGED")
        from settlement_c06_checkpoint_coordinator import validate_receipt
        validate_receipt(receipt,phase,self.sha,previous)
        return receipt

    def anchor(self,plan_sha,step,tip):
        self.check_journal()
        require(plan_sha==self.sha and self.j.records
                and self.j.records[-1]["step"]==step and self.j.tip==tip
                and tip not in self.anchored,"C06_SOURCE_ANCHOR_BINDING")
        self.anchored.add(tip)
        require(self.client.anchor(self.j.records[-1])==tip,
                "C06_SOURCE_ANCHOR_ACK_DRIFT")
        self.check_journal()
        require(self.j.tip==tip,"C06_SOURCE_ANCHOR_JOURNAL_CHANGED")
        return tip


def barrier_schedule(scope,phase):
    """Exact existing native barrier effects; no caller-selected commands."""
    from settlement_c06_native_service_barrier import validate_scope
    validate_scope(scope)
    if phase=="capture":
        return (["hold"]+["gate:"+u for u in scope["stop"]]+["reload"]+
                ["stop:"+u for u in scope["stop"]])
    require(phase=="resume","EFFECT_PHASE")
    result=[]
    for u in scope["resume"]:
        result+=["remove:"+u,"reload:"+u,"start:"+u]
    for u in scope["stop"]:
        if u not in scope["resume"]:
            result+=["remove:"+u,"reload:"+u]
    return result+["release-hold"]


class BarrierEffectJournal(Journal):
    """Separate private per-phase subeffect intent chain.

    Reuses the coordinator's locked directory mechanism. No installer or
    transport dispatcher; no automatic retry after an existing intent.
    A local intent is never an independently authenticated witness ACK.
    """
    def __init__(self,path,plan,scope,phase,phase_tip,admission_sha):
        from settlement_c06_native_service_barrier import validate_scope
        super().__init__(path,validate_plan(plan))
        self.scope_sha=validate_scope(scope)
        require(self.scope_sha==plan["scope"] and hash64(phase_tip)
                and hash64(admission_sha),"EFFECT_JOURNAL_BINDING")
        self.phase=phase;self.phase_tip=phase_tip;self.admission_sha=admission_sha
        self.schedule=tuple(barrier_schedule(scope,phase))
        require(0<len(self.schedule)<=1024,"EFFECT_COUNT")
    def expected(self,index,previous):
        require(type(index) is int and 0<=index<len(self.schedule),"EFFECT_SEQUENCE")
        return dict(schema="wolo.c06.barrier-effect-intent.v1",plan=self.plan_sha,
                    scope=self.scope_sha,phase=self.phase,phase_tip=self.phase_tip,
                    admission_sha256=self.admission_sha,index=index,
                    previous=previous,action=self.schedule[index])
    def read(self):
        files=sorted(set(os.listdir(self.fd))- {".lock"})
        require(len(files)<=len(self.schedule),"EFFECT_JOURNAL_LENGTH")
        records=[]
        for n,name in enumerate(files):
            require(name==f"{n:04d}.json","EFFECT_JOURNAL_GAP")
            fd=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=self.fd)
            with os.fdopen(fd,"rb") as f:
                st=os.fstat(f.fileno())
                require(stat.S_ISREG(st.st_mode) and st.st_uid==os.geteuid()
                        and stat.S_IMODE(st.st_mode)==0o600 and st.st_nlink==1
                        and 0<st.st_size<=4096,"EFFECT_JOURNAL_PRIVATE")
                raw=f.read(4097)
            r=self.expected(n,digest(canonical(records[-1])) if records else None)
            require(raw==canonical(r),"EFFECT_JOURNAL_RECORD_DRIFT")
            records.append(r)
        return records
    def append(self,action):
        require(self.fd is not None and self.lock is not None
                and self.read()==self.records,"EFFECT_JOURNAL_DRIFT")
        n=len(self.records);r=self.expected(n,self.tip)
        require(r["action"]==action,"EFFECT_ACTION_ORDER")
        fd=os.open(f"{n:04d}.json",os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|
                   os.O_WRONLY,0o600,dir_fd=self.fd)
        with os.fdopen(fd,"wb") as f:
            f.write(canonical(r));f.flush();os.fsync(f.fileno())
        os.fsync(self.fd)
        self.records.append(r)
        require(self.read()==self.records,"EFFECT_JOURNAL_READBACK")
        return r


def verify_barrier_phase(plan,scope,phase,receipt,packet,enrollment,journal,**crypto):
    """Revalidate the genuine phase packet and its independently anchored admission.

    Caller must hold the native phase journal lock; crypto pins originate
    from protected enrollment, not caller-controlled values. No lease
    assertion here: the driver must separately check the external lease.
    """
    from settlement_c06_checkpoint_coordinator import validate_receipt
    from settlement_c06_native_service_barrier import validate_scope
    sha=validate_plan(plan)
    require(validate_scope(scope)==plan["scope"] and phase in ("capture","resume")
            and journal.fd is not None and journal.lock is not None
            and journal.plan_sha==sha and journal.read()==journal.records,
            "EFFECT_PHASE_JOURNAL")
    step="FENCE_INTENT" if phase=="capture" else "RESTART_INTENT"
    require(journal.records and journal.records[-1]["step"]==step,
            "EFFECT_PHASE_NOT_AT_INTENT")
    before,admitted=authority.PHASE_STEPS[phase]
    entries=[r for r in journal.records if r["step"]==admitted]
    require(len(entries)==1,"EFFECT_ADMISSION_MISSING")
    entry=entries[0];prev=entry["previous"]
    admission=validate_receipt(receipt,phase,sha,prev)
    require(entry["evidence"]==admission,"EFFECT_ADMISSION_DRIFT")
    checked=authority.review(enrollment,packet,plan,phase=phase,previous=prev,**crypto)
    require(all(checked[k]==receipt[k] for k in ("packet","nonce","expires")),
            "EFFECT_PHASE_SIGNATURE_DRIFT")
    return journal.tip,admission


def anchor_barrier_effect(record,*,plan,scope,phase,receipt,packet,enrollment,
                          phase_journal,effect_journal,witness_identity,**crypto):
    """Witness-side durable exact next intent. Never returns fresh ACK on replay.

    This library requires an independently enrolled native dispatcher and
    the exact source/witness plan; it cannot establish channel authenticity.
    """
    tip,admission=verify_barrier_phase(plan,scope,phase,receipt,packet,enrollment,
                                     phase_journal,**crypto)
    sha=validate_plan(plan)
    require(hash64(witness_identity) and witness_identity!=plan["host"]
            and effect_journal.plan_sha==sha and effect_journal.phase==phase
            and effect_journal.phase_tip==tip and effect_journal.admission_sha==admission
            and effect_journal.scope_sha==plan["scope"]
            and effect_journal.fd is not None and effect_journal.lock is not None
            and effect_journal.read()==effect_journal.records,"EFFECT_WITNESS_BINDING")
    expected=effect_journal.expected(len(effect_journal.records),effect_journal.tip)
    require(type(record) is dict and canonical(record)==canonical(expected),
            "EFFECT_WITNESS_ORDER_OR_REPLAY")
    got=effect_journal.append(expected["action"])
    require(canonical(got)==canonical(record),"EFFECT_WITNESS_READBACK")
    # Expiry after durable write remains ambiguous/spent; never reissue.
    verify_barrier_phase(plan,scope,phase,receipt,packet,enrollment,phase_journal,**crypto)
    return dict(schema="wolo.c06.barrier-effect-anchor.v1",plan=sha,
                phase=phase,tip=effect_journal.tip,witness_identity=witness_identity,
                status="NEW_EFFECT_INTENT_ANCHORED",production_authorized=False,
                funding_authorized=False)


class BarrierEffectBinding:
    """Source-side barrier callbacks; native transport and lease still required.

    No existing source effect journal may be resumed automatically. A failed
    action or uncertain external ACK permanently poisons this in-memory run.
    The outer phase journal remains at INTENT until poststate is verified.
    This is library composition, not an installed live dispatcher.
    """
    def __init__(self,journal,*,verify_phase,verify_lease,anchor_native,witness_identity):
        require(journal.fd is not None and journal.lock is not None
                and journal.read()==journal.records and not journal.records
                and hash64(witness_identity)
                and all(callable(fn) for fn in (verify_phase,verify_lease,anchor_native)),
                "EFFECT_SOURCE_EXISTING_OR_UNADMITTED")
        self.j=journal;self.verify_phase=verify_phase;self.verify_lease=verify_lease
        self.anchor_native=anchor_native;self.identity=witness_identity
        self.state="READY";self.action=None
    def check(self,phase,scope,action):
        require(phase==self.j.phase and scope==self.j.scope_sha
                and self.j.read()==self.j.records,"EFFECT_SOURCE_SCOPE_DRIFT")
        self.verify_lease()
        require(self.verify_phase()==(self.j.phase_tip,self.j.admission_sha),
                "EFFECT_SOURCE_PHASE_DRIFT")
        self.verify_lease()
    def admit_effect(self,phase,scope,action):
        if self.state=="READY":
            self.state="HOLD"
            self.check(phase,scope,action)
            require(self.j.expected(len(self.j.records),self.j.tip)["action"]==action,
                    "EFFECT_SOURCE_ACTION_ORDER")
            self.action=action;self.state="ADMITTED"
        elif self.state=="ANCHORED" and action==self.action:
            self.state="HOLD"
            self.check(phase,scope,action)
            self.state="EFFECT_IN_FLIGHT"
        else:
            self.state="HOLD"
            raise owner.AuthorityHold("EFFECT_SOURCE_SEQUENCE_OR_UNCERTAINTY")
    def anchor_intent(self,phase,scope,action):
        valid=self.state=="ADMITTED" and action==self.action
        self.state="HOLD"
        require(valid,"EFFECT_SOURCE_ANCHOR_ORDER")
        self.check(phase,scope,action)
        record=self.j.append(action)
        expected=dict(schema="wolo.c06.barrier-effect-anchor.v1",plan=self.j.plan_sha,
                      phase=phase,tip=self.j.tip,witness_identity=self.identity,
                      status="NEW_EFFECT_INTENT_ANCHORED",production_authorized=False,
                      funding_authorized=False)
        ack=self.anchor_native(record)
        require(type(ack) is dict and canonical(ack)==canonical(expected),
                "EFFECT_SOURCE_WITNESS_ACK_DRIFT")
        self.check(phase,scope,action)
        self.state="ANCHORED"
    def complete_effect(self,phase,scope,action):
        valid=self.state=="EFFECT_IN_FLIGHT" and action==self.action
        self.state="HOLD"
        require(valid,"EFFECT_SOURCE_COMPLETION_ORDER")
        self.check(phase,scope,action)
        self.action=None;self.state="READY"
    def verify_complete(self):
        require(self.state=="READY" and self.j.read()==self.j.records
                and len(self.j.records)==len(self.j.schedule),
                "EFFECT_SOURCE_INCOMPLETE")
        return self.j.tip


def witness_main():
    # An independently installed forced-command wrapper must invoke this only
    # for COMMAND; no change to the legacy command or authorized_keys here.
    require(os.environ.get("SSH_ORIGINAL_COMMAND")==COMMAND,"C06_FORCED_COMMAND_REQUIRED")
    cfg=legacy.WITNESS_CONFIG.with_name("c06-expanded-witness.json")
    raw=legacy.private_file(cfg); oldraw=legacy.private_file(legacy.WITNESS_CONFIG)
    enrollment=legacy.private_file(legacy.WITNESS_ENROLLMENT)
    c,old=load_expanded(raw,oldraw)
    crypto=bindings(c,old,witness=True)
    data=sys.stdin.buffer.read(MAX_REQUEST+1)
    # Pre-created separately enrolled journal; no implicit directory creation.
    path=legacy.WITNESS_NONCES.parent/"c06-expanded-journal"/c["plan_sha256"]
    with Journal(path,c["plan_sha256"]) as journal:
        ack=dispatch(data,c,old,enrollment,journal,legacy.WITNESS_NONCES,crypto)
        require(legacy.private_file(cfg)==raw
                and legacy.private_file(legacy.WITNESS_CONFIG)==oldraw
                and legacy.private_file(legacy.WITNESS_ENROLLMENT)==enrollment,
                "C06_WITNESS_ENROLLMENT_CHANGED")
        bindings(c,old,witness=True)
        sys.stdout.buffer.write(canonical(ack)+b"\n")
    return 0


if __name__=="__main__":
    try:
        if len(sys.argv)!=1:
            raise owner.AuthorityHold("C06_WITNESS_NO_ARGUMENTS")
        raise SystemExit(witness_main())
    except (OSError,ValueError,RuntimeError,KeyError,TypeError,subprocess.SubprocessError):
        print('{"status":"HOLD_C06_EXPANDED_WITNESS"}',file=sys.stderr)
        raise SystemExit(2)

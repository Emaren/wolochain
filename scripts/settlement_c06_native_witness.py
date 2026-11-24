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

#!/usr/bin/env python3
"""C03 isolated PostgreSQL lock limitation and release-queue reproduction.

Never connects to HEL1 or live databases; creates a private local unix-socket
PostgreSQL cluster in an exclusive, auto-deleted temporary directory.
"""
import contextlib
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import sys
import getpass

APPROVED_BINARY_DIR = Path("/opt/homebrew/bin")
SCHEMA="aoe2war.c03.isolated-lock-counterexample.v1"

class Hold(Exception):
    pass

def must(x,message):
    if not x:raise Hold(message)

def invoke(args,**kw):
    return subprocess.run(args,capture_output=True,text=True,timeout=kw.pop("timeout",12),**kw)

REQUIRED_TRUE = frozenset((
    "shareModeLockAcquired", "selectStillAllowed",
    "tableInsertBlockedWhileLockHeld", "sameTableDdlBlocked",
    "ownedSequenceNextvalStillAllowed", "newTableCreationStillAllowed",
    "concurrentWriterQueued", "queuedWriterExecutedAfterBarrierReleased",
))
REQUIRED_FALSE = frozenset((
    "globalFinanceQuiescenceProven", "noNewSchemaWritingProven",
    "ownedSequenceWritingDenied",
))

def validate_counterexample(observations):
    must(type(observations) is dict
         and set(observations)==REQUIRED_TRUE|REQUIRED_FALSE,
         "COUNTEREXAMPLE_SCOPE_DRIFT")
    must(all(observations[key] is True for key in REQUIRED_TRUE)
         and all(observations[key] is False for key in REQUIRED_FALSE),
         "COUNTEREXAMPLE_EVIDENCE_NOT_EXACT")
    return True

def main():
    base=Path.home()/".cache/aoe2war"
    must(base.is_dir() and not base.is_symlink(),"PRIVATE_C03_CACHE_ABSENT")
    must(os.geteuid()!=0 and sys.platform=="darwin","NONROOT_MAC_REQUIRED")
    required=("initdb","pg_ctl","psql")
    for name in required:
        p=APPROVED_BINARY_DIR/name
        must(p.is_file() and os.access(p,os.X_OK),"MAC_POSTGRES_BINARY_NOT_FOUND")
    report={"schema":SCHEMA,"result":"HOLD","financialAuthority":False,
            "productionConnectAttempted":False,"testDatabase":"ephemeral-unix-only",
            "controlPlane":"Mac-local PostgreSQL 14 temporary cluster",
            "observations":{}}
    with tempfile.TemporaryDirectory(prefix="c03-isolated-pg-",dir=base) as tmp:
        root=Path(tmp)
        os.chmod(root,0o700)
        data=root/"data"
        sock=root/"socket";sock.mkdir(mode=0o700)
        p=invoke([str(APPROVED_BINARY_DIR/"initdb"),"-A","trust","-U",getpass.getuser(),"-D",str(data)],timeout=30)
        must(p.returncode==0,"ISOLATED_INITDB_FAILED")
        print("C03_STAGE=INITDB_OK",file=sys.stderr,flush=True)
        pgctl=str(APPROVED_BINARY_DIR/"pg_ctl")
        options=f"-c listen_addresses='' -c unix_socket_directories={sock} -c unix_socket_permissions=0700 -c fsync=off -c synchronous_commit=off -c logging_collector=off"
        start=subprocess.run([pgctl,"-D",str(data),"-o",options,
                               "-l",str(root/"ephemeral-postgres.log"),"-w","start"],
                              stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL,timeout=12,check=False)
        if start.returncode != 0:
            # The child can outlive a failed pg_ctl confirmation. Never
            # remove an unverified live cluster's files without attempting
            # its exact temporary-datadir stop first.
            subprocess.run([pgctl,"-D",str(data),"-m","immediate","-w","stop"],
                           stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL,timeout=12,check=False)
        must(start.returncode==0,"ISOLATED_PG_START_FAILED")
        print("C03_STAGE=PGCTL_START_OK",file=sys.stderr,flush=True)
        barrier=None; queued=None
        try:
            cmd=[str(APPROVED_BINARY_DIR/"psql"),"-X","-qAt","-v","ON_ERROR_STOP=1",
                 "-h",str(sock),"-p","5432","-U",getpass.getuser(),"-d","postgres"]
            def q(sql,*,timeout=10):
                return invoke(cmd+["-c",sql],timeout=timeout)
            setup=q("CREATE TABLE public.financial_shadow (id BIGSERIAL PRIMARY KEY, amount INTEGER NOT NULL); INSERT INTO public.financial_shadow(amount) VALUES (100);")
            must(setup.returncode==0,"ISOLATED_SCHEMA_SETUP_FAILED")
            print("C03_STAGE=SCHEMA_SETUP_OK",file=sys.stderr,flush=True)
            barrier=subprocess.Popen(cmd+["-c",
              "BEGIN; LOCK TABLE public.financial_shadow IN SHARE MODE; SELECT pg_sleep(10); COMMIT;"],
              stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
              stderr=subprocess.PIPE, text=True)
            acquired=False
            for _ in range(35):
                locked=q("SELECT count(*) FROM pg_locks WHERE locktype='relation' AND relation='public.financial_shadow'::regclass AND mode='ShareLock' AND granted",timeout=3)
                if locked.returncode==0 and locked.stdout.strip()=="1":
                    acquired=True
                    break
                if barrier.poll() is not None:break
                time.sleep(.1)
            must(acquired and barrier.poll() is None,"BARRIER_NOT_ACQUIRED")
            print("C03_STAGE=BARRIER_ACQUIRED",file=sys.stderr,flush=True)
            report["observations"]["shareModeLockAcquired"]=True
            read=q("SELECT count(*) FROM public.financial_shadow")
            must(read.returncode==0 and read.stdout.strip()=="1","SELECT_BLOCKED")
            report["observations"]["selectStillAllowed"]=True
            insert=q("SET lock_timeout='350ms'; INSERT INTO public.financial_shadow(amount) VALUES (200)")
            must(insert.returncode!=0 and "lock timeout" in insert.stderr.lower(),"TABLE_INSERT_NOT_BLOCKED")
            report["observations"]["tableInsertBlockedWhileLockHeld"]=True
            mutate=q("SET lock_timeout='350ms'; ALTER TABLE public.financial_shadow ADD COLUMN bypass INTEGER")
            must(mutate.returncode!=0 and "lock timeout" in mutate.stderr.lower(),"DDL_NOT_BLOCKED")
            report["observations"]["sameTableDdlBlocked"]=True
            sequence=q("SELECT nextval('public.financial_shadow_id_seq')")
            must(sequence.returncode==0 and sequence.stdout.strip().isdigit(),"OWNED_SEQUENCE_NOT_INDEPENDENT")
            report["observations"]["ownedSequenceNextvalStillAllowed"]=True
            bypass=q("CREATE TABLE public.new_financial_path (event_id INTEGER)")
            must(bypass.returncode==0,"SCHEMA_CREATE_NOT_INDEPENDENT")
            report["observations"]["newTableCreationStillAllowed"]=True
            print("C03_STAGE=COUNTEREXAMPLES_PROVEN",file=sys.stderr,flush=True)
            queued=subprocess.Popen(cmd+["-c","INSERT INTO public.financial_shadow(amount) VALUES (300)"],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
            time.sleep(.35)
            must(queued.poll() is None,"QUEUED_WRITER_DID_NOT_WAIT")
            report["observations"]["concurrentWriterQueued"]=True
            stdout,stderr=barrier.communicate(timeout=14)
            must(barrier.returncode==0,"BARRIER_RELEASE_FAILED")
            barrier=None
            print("C03_STAGE=BARRIER_RELEASED",file=sys.stderr,flush=True)
            queued_out,queued_err=queued.communicate(timeout=4)
            must(queued.returncode==0,"QUEUED_WRITER_FAILED_AFTER_RELEASE")
            queued=None
            count=q("SELECT count(*) FROM public.financial_shadow")
            must(count.returncode==0 and count.stdout.strip()=="2","WRITER_RESUME_COUNT_CHANGED")
            report["observations"]["queuedWriterExecutedAfterBarrierReleased"]=True
            report["observations"]["globalFinanceQuiescenceProven"]=False
            report["observations"]["noNewSchemaWritingProven"]=False
            report["observations"]["ownedSequenceWritingDenied"]=False
            validate_counterexample(report["observations"])
            report["result"]="PASS_COUNTEREXAMPLE_HOLD_FOR_REAL_FINANCIAL_FREEZE"
        finally:
            if queued is not None:
                if queued.poll() is None: queued.kill()
                queued.communicate(timeout=4)
            if barrier is not None:
                if barrier.poll() is None: barrier.kill()
                barrier.communicate(timeout=4)
            print("C03_STAGE=TEARDOWN_BEGIN",file=sys.stderr,flush=True)
            stop=subprocess.run([pgctl,"-D",str(data),"-m","immediate","-w","stop"],
                                stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL,timeout=12,check=False)
            print("C03_STAGE=TEARDOWN_FINISHED",file=sys.stderr,flush=True)
            if stop.returncode!=0:
                report["result"]="HOLD_ISOLATED_PG_TEARDOWN_FAILED"
        # TemporaryDirectory also removes all data; no persistent cluster.
    return report

if __name__=="__main__":
    try:
        r=main()
        print(json.dumps(r,sort_keys=True,indent=2))
        sys.exit(0 if r["result"].startswith("PASS_COUNTEREXAMPLE") else 2)
    except (Hold,OSError,subprocess.SubprocessError,ValueError) as e:
        print(json.dumps({"schema":SCHEMA,"result":"STOP","reason":str(e) if isinstance(e,Hold) else "ISOLATED_REHEARSAL_"+type(e).__name__,"financialAuthority":False},sort_keys=True))
        sys.exit(2)

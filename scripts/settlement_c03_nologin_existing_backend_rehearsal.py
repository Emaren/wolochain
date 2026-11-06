#!/usr/bin/env python3
"""Isolated PG14 proof: NOLOGIN blocks new connects, NOT existing writers."""
from __future__ import annotations
import hashlib,json,os,subprocess,tempfile,time,sys,getpass
from pathlib import Path
B=Path("/opt/homebrew/bin")
ROOT=Path.home()/".cache/aoe2war"
REQUIRED=(
    "newLegacyConnectionDenied",
    "existingLegacySessionStillWritesAfterNoLogin",
    "independentPublicRoleKeepsReading",
    "terminatedLegacyBackendCannotCommit",
    "roleLoginReinstatementRestoresWrites",
)
def require_proofs(observations):
    if type(observations) is not dict or set(observations)!=set(REQUIRED):
        raise ValueError("PROOF_SHAPE_DRIFT")
    if not all(observations[x] is True for x in REQUIRED):
        raise ValueError("FIVE_EXACT_TRUE_PROOFS_REQUIRED")
    return True
def run(cmd,timeout=18):
    return subprocess.run(cmd,stdin=subprocess.DEVNULL,capture_output=True,text=True,timeout=timeout)
def main():
    if sys.platform!="darwin" or os.geteuid()==0 or not ROOT.is_dir() or ROOT.is_symlink():
        raise ValueError("MAC_NONROOT_ONLY")
    report={"schema":"aoe2war.c03.temp-nologin-existing-session-counterexample.v1",
            "status":"HOLD","syntheticOnly":True,"productionDatabaseTouched":False,
            "financialPermitIssued":False,"observations":{}}
    with tempfile.TemporaryDirectory(dir=ROOT,prefix="c03-nologin-session-") as td:
        r=Path(td); data=r/"data";sock=r/"sock";sock.mkdir(mode=0o700)
        init=run([str(B/"initdb"),"-A","trust","-U",getpass.getuser(),"-D",str(data)],35)
        if init.returncode:raise ValueError("INITDB_FAIL")
        started=False
        ctl=str(B/"pg_ctl")
        try:
            opts=f"-c listen_addresses='' -c unix_socket_directories={sock} -c unix_socket_permissions=0700 -c fsync=off"
            start=subprocess.run([ctl,"-D",str(data),"-o",opts,"-l",str(r/"postgres.log"),"-w","start"],
                    stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=20)
            started=start.returncode==0
            if not started:raise ValueError("PG_START_FAIL")
            cmd=[str(B/"psql"),"-X","-qAt","-v","ON_ERROR_STOP=1","-h",str(sock),"-p","5432","-d","postgres"]
            def sql(statement,user=None):
                return run(cmd+["-U",user or getpass.getuser(),"-c",statement],16)
            stage=[0]
            def check(statement,user=None):
                stage[0]+=1
                out=sql(statement,user)
                if out.returncode:raise ValueError("EXPECTED_SQL_FAILURE_STAGE_"+str(stage[0])+"_"+statement.split()[0]+"_ERR_"+out.stderr[-160:].replace(chr(10)," "))
                return out.stdout.strip()
            check("""CREATE ROLE c03_test_legacy LOGIN;
                     CREATE ROLE c03_test_public LOGIN;
                     CREATE TABLE public.c03_test_finance (id SERIAL PRIMARY KEY, amount INT);
                     INSERT INTO public.c03_test_finance(amount) VALUES(100);
                     GRANT SELECT,INSERT,UPDATE,DELETE ON public.c03_test_finance TO c03_test_legacy;
                     GRANT USAGE,SELECT ON SEQUENCE public.c03_test_finance_id_seq TO c03_test_legacy;
                     GRANT SELECT ON public.c03_test_finance TO c03_test_public;""")
            # A connected client has entered a delayed operation before
            # NOLOGIN; it will not reauthenticate when the role changes.
            legacy=cmd+["-U","c03_test_legacy","-c",
                "SELECT pg_sleep(3); INSERT INTO public.c03_test_finance(amount) VALUES (200);"]
            existing=subprocess.Popen(legacy,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
            try:
                got=False
                for _ in range(30):
                    count=check("SELECT count(*) FROM pg_stat_activity WHERE usename='c03_test_legacy'")
                    if count=="1":got=True;break
                    time.sleep(.1)
                if not got:raise ValueError("CLIENT_NOT_CONNECTED")
                check("ALTER ROLE c03_test_legacy NOLOGIN")
                denied=sql("SELECT 1","c03_test_legacy")
                if denied.returncode==0:raise ValueError("NOLOGIN_NEW_SESSION_ALLOWED")
                report["observations"]["newLegacyConnectionDenied"]=True
                output,error=existing.communicate(timeout=9)
                if existing.returncode!=0:raise ValueError("EXISTING_BACKEND_DID_NOT_COMPLETE")
                if check("SELECT count(*) FROM public.c03_test_finance")!="2":
                    raise ValueError("EXISTING_SESSION_WRITE_NOT_OBSERVED")
                report["observations"]["existingLegacySessionStillWritesAfterNoLogin"]=True
                if check("SELECT count(*) FROM public.c03_test_finance","c03_test_public")!="2":
                    raise ValueError("SEPARATE_PUBLIC_READ_INTERRUPTED")
                report["observations"]["independentPublicRoleKeepsReading"]=True
                check("ALTER ROLE c03_test_legacy LOGIN")
                existing2=subprocess.Popen(cmd+["-U","c03_test_legacy","-c",
                  "SELECT pg_sleep(8); INSERT INTO public.c03_test_finance(amount) VALUES(300);"],
                  stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
                try:
                    ready=False
                    for _ in range(30):
                        if check("SELECT count(*) FROM pg_stat_activity WHERE usename='c03_test_legacy'")=="1":
                            ready=True;break
                        time.sleep(.1)
                    if not ready:raise ValueError("CLIENT2_NOT_CONNECTED")
                    check("ALTER ROLE c03_test_legacy NOLOGIN")
                    target=check("SELECT pid FROM pg_stat_activity WHERE usename='c03_test_legacy' AND pid <> pg_backend_pid()")
                    if not target.isdecimal() or int(target)<1:
                        raise ValueError("EXACT_TARGET_BACKEND_PID_REQUIRED")
                    terminated=check("SELECT pg_terminate_backend("+str(int(target))+")")
                    if terminated!="t":raise ValueError("EXACT_BACKEND_TERMINATE_UNPROVEN")
                    _out,_err=existing2.communicate(timeout=10)
                    if existing2.returncode==0:raise ValueError("TERMINATED_WRITER_SUCCESS")
                    if check("SELECT count(*) FROM public.c03_test_finance")!="2":
                        raise ValueError("TERMINATED_WRITER_COMMITTED")
                    report["observations"]["terminatedLegacyBackendCannotCommit"]=True
                finally:
                    if existing2.poll() is None:
                        existing2.kill();existing2.communicate(timeout=3)
                check("ALTER ROLE c03_test_legacy LOGIN")
                if check("INSERT INTO public.c03_test_finance(amount) VALUES(400) RETURNING amount","c03_test_legacy")!="400":
                    raise ValueError("ROLLBACK_LOGIN_FAIL")
                report["observations"]["roleLoginReinstatementRestoresWrites"]=True
                require_proofs(report["observations"])
                report["status"]="PASS_SYNTHETIC_NOLOGIN_COUNTEREXAMPLE_HOLD_FOR_PRODUCTION"
            finally:
                if existing.poll() is None:
                    existing.kill();existing.communicate(timeout=3)
        finally:
            if started:
                end=subprocess.run([ctl,"-D",str(data),"-m","immediate","-w","stop"],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=15)
                if end.returncode:raise ValueError("DISPOSABLE_CLUSTER_TEARDOWN_FAIL")
    return report
if __name__=="__main__":
    try:
        val=main()
        print(json.dumps(val,sort_keys=True,indent=2))
    except Exception as exc:
        print(json.dumps({"schema":"aoe2war.c03.temp-nologin-existing-session-counterexample.v1",
                          "status":"STOP","reason":type(exc).__name__+":"+str(exc)[:70],
                          "productionDatabaseTouched":False},sort_keys=True))
        sys.exit(2)

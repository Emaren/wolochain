#!/usr/bin/env python3
"""C03 disposable PG14 demonstration of NOLOGIN finance ownership partition.

This is a local, private, Unix-socket-only synthetic database. It does not
connect to HEL1 or manipulate production grants.
"""
from __future__ import annotations
import getpass
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

BIN=Path("/opt/homebrew/bin")
SCHEMA="aoe2war.c03.isolated-nologin-owner-denial.v1"
TRUE=(
 "legacyFinanceTableDmlDenied",
 "legacyFinanceSequenceDenied",
 "legacyFinanceDdlDenied",
 "legacySchemaCreateDenied",
 "legacyRoleCannotBecomeFinanceOwner",
 "neutralFinanceOwnerCannotLogin",
 "legacySelectPermitted",
 "nonfinanceWritesPermitted",
 "rollbackRestoresLegacyFinanceWrite",
)

class Hold(ValueError):pass
def require(test,msg):
    if not test:raise Hold(msg)

def run(argv,timeout=10):
    return subprocess.run(argv,stdin=subprocess.DEVNULL,
                          stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                          text=True,timeout=timeout,check=False)

def validate_proof(checks):
    require(type(checks) is dict and set(checks)==set(TRUE),
            "SYNTHETIC_PROOF_KEY_DRIFT")
    require(all(checks[key] is True for key in TRUE),
            "SYNTHETIC_PROOF_MISSING_POSITIVE")
    return True

def main():
    base=Path.home()/".cache/aoe2war"
    require(sys.platform=="darwin" and os.geteuid()!=0,"MAC_NONROOT_REQUIRED")
    require(base.is_dir() and not base.is_symlink(),"PRIVATE_SCRATCH_NOT_FOUND")
    for name in ("initdb","pg_ctl","psql"):
        require((BIN/name).is_file() and os.access(BIN/name,os.X_OK),
                "LOCAL_PG14_REQUIRED")
    results={"schema":SCHEMA,"status":"HOLD","financialReleaseAuthorized":False,
             "productionConnectionAttempted":False,"synthetic":True,
             "checks":{}}
    with tempfile.TemporaryDirectory(prefix="c03-owner-partition-",dir=base) as td:
        root=Path(td)
        data=root/"data"
        sock=root/"socket"
        sock.mkdir(mode=0o700)
        init=run([str(BIN/"initdb"),"-A","trust","-U",getpass.getuser(),
                  "-D",str(data)],timeout=25)
        require(init.returncode==0,"ISOLATED_INIT_FAILED")
        pgctl=str(BIN/"pg_ctl")
        opts=f"-c listen_addresses='' -c unix_socket_directories={sock} -c unix_socket_permissions=0700 -c fsync=off"
        started=False
        try:
            start=subprocess.run([pgctl,"-D",str(data),"-o",opts,
                 "-l",str(root/"pg.log"),"-w","start"],
                 stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,
                 stderr=subprocess.DEVNULL,timeout=12,check=False)
            started=start.returncode==0
            require(started,"ISOLATED_START_FAILED")
            basecmd=[str(BIN/"psql"),"-X","-qAt","-v","ON_ERROR_STOP=1",
                     "-h",str(sock),"-p","5432","-d","postgres"]
            def sql(statement,role=None,timeout=8):
                return run(basecmd+["-U",role or getpass.getuser(),"-c",statement],timeout)
            def positive(statement, role=None):
                p=sql(statement,role)
                require(p.returncode==0,"ISOLATED_POSITIVE_SQL_FAILED")
                return p.stdout.strip()
            def negative(statement, role=None):
                p=sql(statement,role)
                require(p.returncode!=0,"ISOLATED_NEGATIVE_SQL_UNEXPECTEDLY_ALLOWED")
                return p.stderr
            positive("CREATE ROLE c03_legacy LOGIN; CREATE ROLE c03_finance_owner NOLOGIN; ALTER DATABASE postgres OWNER TO c03_legacy; ALTER SCHEMA public OWNER TO c03_legacy;")
            positive("CREATE TABLE public.finance_shadow(id BIGSERIAL PRIMARY KEY, amount INTEGER NOT NULL); CREATE TABLE public.profile_shadow(id INT PRIMARY KEY, label TEXT NOT NULL); INSERT INTO public.finance_shadow(amount) VALUES(100); INSERT INTO public.profile_shadow VALUES(1,'original')",role="c03_legacy")
            positive("""CREATE FUNCTION public.finance_guard() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF NEW.amount < 0 THEN RAISE EXCEPTION 'negative'; END IF; RETURN NEW; END $$;
             CREATE TRIGGER guard_finance BEFORE INSERT ON public.finance_shadow FOR EACH ROW EXECUTE FUNCTION public.finance_guard();""",role="c03_legacy")
            positive("""ALTER DATABASE postgres OWNER TO c03_finance_owner;
              ALTER SCHEMA public OWNER TO c03_finance_owner;
              REVOKE CREATE ON SCHEMA public FROM PUBLIC;
              REVOKE CREATE ON DATABASE postgres FROM PUBLIC;
              GRANT CONNECT ON DATABASE postgres TO c03_legacy;
              GRANT USAGE ON SCHEMA public TO c03_legacy;
              ALTER TABLE public.finance_shadow OWNER TO c03_finance_owner;
              ALTER SEQUENCE public.finance_shadow_id_seq OWNER TO c03_finance_owner;
              ALTER FUNCTION public.finance_guard() OWNER TO c03_finance_owner;
              REVOKE ALL ON TABLE public.finance_shadow FROM c03_legacy;
              REVOKE ALL ON SEQUENCE public.finance_shadow_id_seq FROM c03_legacy;
              GRANT SELECT ON TABLE public.finance_shadow TO c03_legacy;""")
            # Each denial is a separate real login/session using only synthetic
            # legacy role identity. No mocked role or ALTER OWNER in production.
            for statement in (
              "INSERT INTO public.finance_shadow(amount) VALUES(200)",
              "UPDATE public.finance_shadow SET amount=200",
              "DELETE FROM public.finance_shadow",
              "TRUNCATE public.finance_shadow",
            ):
                negative(statement,role="c03_legacy")
            results["checks"]["legacyFinanceTableDmlDenied"]=True
            for statement in (
              "SELECT nextval('public.finance_shadow_id_seq')",
              "SELECT setval('public.finance_shadow_id_seq',500)",
            ):
                negative(statement,role="c03_legacy")
            results["checks"]["legacyFinanceSequenceDenied"]=True
            negative("ALTER TABLE public.finance_shadow ADD COLUMN forbidden integer",
                     role="c03_legacy")
            results["checks"]["legacyFinanceDdlDenied"]=True
            negative("CREATE TABLE public.shadow_bypass (id integer)",
                     role="c03_legacy")
            negative("CREATE SCHEMA c03_shadow_bypass",role="c03_legacy")
            results["checks"]["legacySchemaCreateDenied"]=True
            negative("SET ROLE c03_finance_owner",role="c03_legacy")
            results["checks"]["legacyRoleCannotBecomeFinanceOwner"]=True
            negative("SELECT 1",role="c03_finance_owner")
            results["checks"]["neutralFinanceOwnerCannotLogin"]=True
            require(positive("SELECT count(*) FROM public.finance_shadow",
                role="c03_legacy")=="1","LEGACY_SELECT_BROKEN")
            results["checks"]["legacySelectPermitted"]=True
            positive("UPDATE public.profile_shadow SET label='updated' WHERE id=1",
                role="c03_legacy")
            results["checks"]["nonfinanceWritesPermitted"]=True
            # Prove a reversible ownership restoration in this same isolated
            # synthetic cluster; NEVER extrapolate to the real HD/DE restore.
            positive("""ALTER TABLE public.finance_shadow OWNER TO c03_legacy;
              ALTER SEQUENCE public.finance_shadow_id_seq OWNER TO c03_legacy;
              ALTER FUNCTION public.finance_guard() OWNER TO c03_legacy;
              ALTER SCHEMA public OWNER TO c03_legacy;
              ALTER DATABASE postgres OWNER TO c03_legacy;
              GRANT CREATE ON SCHEMA public TO c03_legacy;""")
            positive("INSERT INTO public.finance_shadow(amount) VALUES(300)",
                     role="c03_legacy")
            require(positive("SELECT count(*) FROM public.finance_shadow")== "2",
                    "SYNTHETIC_ROLLBACK_NOT_EFFECTIVE")
            results["checks"]["rollbackRestoresLegacyFinanceWrite"]=True
            validate_proof(results["checks"])
            results["status"]="PASS_SYNTHETIC_MIGRATION_AND_ROLLBACK_HOLD_FOR_LIVE"
        finally:
            if started:
                stop=subprocess.run([pgctl,"-D",str(data),"-m","immediate",
                    "-w","stop"],stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                    timeout=12,check=False)
                if stop.returncode!=0:
                    results["status"]="STOP_SYNTHETIC_CLUSTER_TEARDOWN_FAILED"
    return results

if __name__=="__main__":
    try:
        r=main()
        print(json.dumps(r,sort_keys=True,indent=2))
        sys.exit(0 if r["status"].startswith("PASS_SYNTHETIC_") else 2)
    except (Hold,OSError,ValueError,subprocess.SubprocessError) as exc:
        reason=str(exc) if isinstance(exc,Hold) else type(exc).__name__
        print(json.dumps({"schema":SCHEMA,"status":"STOP","reason":reason,
             "financialReleaseAuthorized":False},sort_keys=True))
        sys.exit(2)

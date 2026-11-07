#!/usr/bin/env python3
"""C03 conservative money-name/column HD/DE schema owner rehearsal, INTEL ONLY.

Reads exact SHA-pinned PostgreSQL schema-only dumps; never connects to HEL1
or production. Does not authorize a live database ownership migration.
"""
from __future__ import annotations
import getpass
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile

SCHEMA="aoe2war.c03.intel-conservative-money-column-owner-isolated.v3"
BASE=Path.home()/".cache/aoe2war"
SOURCE=BASE/"c03-live-schema-only-20261106"
BINARY=Path.home()/".local/aoe2war-pg16-16.15/bin"
PINS={
 "hd":("aoe2hd_db","f70f244080296a46b92722d331fc3087fcf75e68629092e9b72d5f00603b6228",54),
 "de":("aoe2de_db","54e79f002c0d6691633e7616e4ca992b52bd67d2f17509357c69dad98c31de89",20),
}
FINANCE="(wolo|bet|wager|settle|claim|escrow|refund|reward|stake|treasury|wallet|founder|bonus|payout|transfer)"
SEMANTIC="(amount.*wolo|wolo.*amount|tx_hash|transaction_hash|recipient_address|owner_address|escrow|payment|payout|withdraw|deposit|balance|stake|reward)"
SEQ_PINS={"hd":52,"de":20}
PAYOUT_TABLES={"hd":(
    "public.bounty_payouts","public.championship_transfer_groups",
    "public.championship_transfer_seats","public.trophy_payout_allocations",
    "public.trophy_payouts","public.war_graph_payout_events"),
    "de":("public.trophy_payouts",)}


class Hold(RuntimeError):pass
def need(ok,reason):
    if not ok: raise Hold(reason)
def run(args,timeout=90):
    return subprocess.run([str(a) for a in args],stdin=subprocess.DEVNULL,
                          capture_output=True,text=True,timeout=timeout,check=False)
def check_sql_output(s):
    # Structured catalog data, not an execution authority.
    need(isinstance(s,str) and len(s.encode())<200000,"UNBOUNDED_CATALOG_OUTPUT")
    return [x for x in s.strip().splitlines() if x.strip()]
def check_exact_archive(lane):
    name,expected,total=PINS[lane]
    file=SOURCE/(name+".schema.dump")
    st=file.lstat()
    need(stat.S_ISREG(st.st_mode) and not file.is_symlink() and st.st_uid==os.getuid()
         and stat.S_IMODE(st.st_mode)==0o600 and st.st_size<20000000,
         "PRIVATE_SCHEMA_FILE_INVALID_"+lane)
    need(hashlib.sha256(file.read_bytes()).hexdigest()==expected,"SOURCE_ARCHIVE_HASH_DRIFT_"+lane)
    return file,total
def admission():
    need(sys.platform=="darwin" and os.uname().machine=="x86_64" and os.geteuid()!=0,
         "INTEL_DARWIN_NONROOT_ONLY")
    for root in (BASE,SOURCE):
        st=root.lstat()
        need(stat.S_ISDIR(st.st_mode) and not root.is_symlink()
             and st.st_uid==os.getuid() and not(st.st_mode & 0o022),
             "OWNER_PRIVATE_ROOT_REQUIRED")
    for name in ("postgres","initdb","pg_ctl","pg_restore","psql"):
        need((BINARY/name).is_file() and os.access(BINARY/name,os.X_OK),
             "EXACT_PG16_TOOLCHAIN_MISSING_"+name)
    return {lane:check_exact_archive(lane) for lane in PINS}
def finance_identifiers(sql,db):
    query=("SELECT format('%I.%I',n.nspname,c.relname) "
      "FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
      "WHERE n.nspname='public' AND c.relkind IN ('r','p') "
      "AND (c.relname ~* '"+FINANCE+"' OR EXISTS ("
      "SELECT 1 FROM pg_attribute a WHERE a.attrelid=c.oid "
      "AND a.attnum>0 AND NOT a.attisdropped AND a.attname ~* '"+SEMANTIC+"')) "
      "ORDER BY c.relname;")
    return check_exact_identifiers(sql(db,query))
def check_exact_identifiers(rows):
    need(rows and len(rows)==len(set(rows)) and all(
         re.fullmatch(r'(?:(?:public)|(?:"(?:[^"]|"")*"))\.(?:(?:[a-z_][a-z0-9_]*)|(?:"(?:[^"]|"")*"))',v) for v in rows),
         "UNEXPECTED_CATALOG_IDENTIFIER")
    return rows
def sequence_identifiers(sql,db):
    query=("SELECT DISTINCT format('%I.%I',sn.nspname,sc.relname) "
      "FROM pg_class sc JOIN pg_namespace sn ON sn.oid=sc.relnamespace "
      "JOIN pg_depend dep ON dep.objid=sc.oid "
      "JOIN pg_class tab ON dep.refobjid=tab.oid "
      "JOIN pg_namespace tn ON tn.oid=tab.relnamespace "
      "WHERE sc.relkind='S' AND dep.deptype IN ('a','i') "
      "AND tn.nspname='public' AND (tab.relname ~* '"+FINANCE+"' OR EXISTS ("
      "SELECT 1 FROM pg_attribute a WHERE a.attrelid=tab.oid "
      "AND a.attnum>0 AND NOT a.attisdropped AND a.attname ~* '"+SEMANTIC+"')) "
      "ORDER BY 1;")
    rows=sql(db,query)
    return check_exact_identifiers(rows) if rows else []
def restore_and_rehearse(sock,archives):
    owner_account=getpass.getuser()
    psql=[BINARY/"psql","-X","-qAt","-v","ON_ERROR_STOP=1",
          "-h",sock,"-p","54382"]
    def query(db,statement,user=owner_account,allow_fail=False):
        r=run(psql+["-U",user,"-d",db,"-c",statement],35)
        if not allow_fail:need(r.returncode==0,"SQL_STAGE_FAILED_"+db)
        return r
    def text(db,statement,user=owner_account):
        return query(db,statement,user).stdout.strip()
    report={}
    for lane,(archive,count) in archives.items():
        db=f"c03_{lane}_schema";legacy=f"c03_{lane}_legacy";neutral=f"c03_{lane}_neutral"
        # CREATE DATABASE must be a separate statement, never combined with CREATE ROLE.
        text("postgres",f"CREATE ROLE {legacy} LOGIN")
        text("postgres",f"CREATE ROLE {neutral} NOLOGIN")
        text("postgres",f"CREATE DATABASE {db}")
        r=run([BINARY/"pg_restore","--exit-on-error","--no-owner","--no-privileges",
               "--no-comments","-h",sock,"-p","54382","-U",owner_account,
               "-d",db,archive],150)
        need(r.returncode==0,"SOURCE_SCHEMA_RESTORE_FAILURE_"+lane)
        def sql(database,statement):
            return check_sql_output(text(database,statement))
        finance=finance_identifiers(sql,db)
        need(len(finance)==count,"FINANCE_TABLE_COUNT_DRIFT_"+lane)
        need(all(name in finance for name in PAYOUT_TABLES[lane]),
             "MISSING_EXPANDED_PAYOUT_OR_TRANSFER_TABLE_"+lane)
        seq=sequence_identifiers(sql,db)
        need(len(seq)==SEQ_PINS[lane],"EXPANDED_SEQUENCE_COUNT_DRIFT_"+lane)
        # Model incumbent database and finance-table ownership in this disposable cluster.
        text("postgres",f"ALTER DATABASE {db} OWNER TO {legacy}")
        text(db,f"GRANT CREATE,USAGE ON SCHEMA public TO {legacy}")
        for name in finance:
            text(db,f"ALTER TABLE {name} OWNER TO {legacy}")
        first=finance[0]
        need(text(db,f"SELECT has_table_privilege('{legacy}','{first}'::regclass,'INSERT,UPDATE,DELETE,TRUNCATE')::int")=="1",
             "INCUMBENT_OWNER_WRITE_NOT_MODELED_"+lane)
        # Reassign actual finance tables, attached sequences, database and schema owners.
        text("postgres",f"ALTER DATABASE {db} OWNER TO {neutral}")
        text(db,f"ALTER SCHEMA public OWNER TO {neutral}")
        text(db,f"REVOKE CREATE ON SCHEMA public FROM PUBLIC, {legacy}")
        text(db,f"GRANT USAGE ON SCHEMA public TO {legacy}")
        for name in finance:
            text(db,f"ALTER TABLE {name} OWNER TO {neutral}")
            text(db,f"GRANT SELECT ON TABLE {name} TO {legacy}")
        for name in seq:
            text(db,f"ALTER SEQUENCE {name} OWNER TO {neutral}")
        names=",".join("'"+x.replace("'","''")+"'" for x in finance)
        remaining=text(db,f"SELECT count(*) FROM (SELECT unnest(ARRAY[{names}])::regclass rel) f "
                        f"WHERE has_table_privilege('{legacy}',rel,'INSERT,UPDATE,DELETE,TRUNCATE')")
        need(remaining=="0","LEGACY_FINANCE_WRITES_REMAIN_"+lane)
        need(text(db,f"SELECT has_schema_privilege('{legacy}','public','CREATE')::int")=="0",
             "SCHEMA_CREATE_BYPASS_"+lane)
        need(text(db,f"SELECT pg_has_role('{legacy}','{neutral}','MEMBER')::int")=="0",
             "OWNER_MEMBERSHIP_BYPASS_"+lane)
        need(query(db,"SELECT count(*) FROM "+first,user=legacy).returncode==0,
             "APPROVED_FINANCE_READ_DENIED_"+lane)
        negative={
         "TRUNCATE":f"TRUNCATE TABLE {first}",
         "TABLE_DDL":f"ALTER TABLE {first} ADD COLUMN c03_unpermitted INT",
         "SCHEMA_CREATE":"CREATE TABLE public.c03_unpermitted(id INT)",
         "SET_ROLE":f"SET ROLE {neutral}",
        }
        for name,statement in negative.items():
            need(query(db,statement,user=legacy,allow_fail=True).returncode!=0,
                 name+"_UNAUTHORIZED_SUCCESS_"+lane)
        # Prove rollback to modeled incumbent ownership, but NEVER on the real host.
        for name in finance:
            text(db,f"ALTER TABLE {name} OWNER TO {legacy}")
        for name in seq:
            text(db,f"ALTER SEQUENCE {name} OWNER TO {legacy}")
        text(db,f"GRANT CREATE ON SCHEMA public TO {legacy}")
        text(db,"ALTER SCHEMA public OWNER TO pg_database_owner")
        text("postgres",f"ALTER DATABASE {db} OWNER TO {legacy}")
        need(text(db,f"SELECT has_table_privilege('{legacy}','{first}'::regclass,'INSERT,UPDATE,DELETE,TRUNCATE')::int")=="1",
             "ROLLBACK_DML_PRIVILEGE_NOT_RESTORED_"+lane)
        report[lane]={"financeNamedTables":len(finance),"attachedSequences":len(seq),
          "allNewPayoutTablesIncluded":True,
          "conservative_semantic_candidates_included":True,
          "fullDataNotIncluded":True,
          "liveProductionFinanceMutationProven":False,
          "incumbentOwnerWriteModeled":True,"postMigrationDmlDeniedOnAllTables":True,
          "physicalTruncateDenied":True,"physicalTableDdlDenied":True,
          "physicalSchemaCreateDenied":True,"setRoleDenied":True,
          "financeSelectPreserved":True,"isolatedRollbackVerified":True}
    return report
def main():
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument("--mode",choices=("inspect","run-isolated"),default="inspect")
    args=parser.parse_args()
    archives=admission()
    report={"schema":SCHEMA,"status":"HOLD","syntheticOnly":True,
       "prior24Hd10DeRehearsalsInsufficientForC03":True,
      "prior30Hd11DeRehearsalsInsufficientForC03":True,
      "full_app_money_codepath_categorization_proven":False,
      "realSchemaWithoutData":True,"productionDatabasesConnected":False,
      "productionRolesChanged":False,"financialReleaseAuthorized":False,
      "sourceArchiveSha256":{lane:PINS[lane][1] for lane in PINS}}
    if args.mode=="inspect":
        report["status"]="PASS_PINNED_INTEL_REAL_SCHEMA_INPUT_HOLD"
        return report
    with tempfile.TemporaryDirectory(dir=BASE,prefix="c03-real-schema-owner-") as td:
        root=Path(td);sock=root/"sock";sock.mkdir(mode=0o700);data=root/"pgdata"
        need(run([BINARY/"initdb","-A","trust","-U",getpass.getuser(),"-D",data],60).returncode==0,
             "PRIVATE_INITDB_FAILED")
        started=False
        try:
            opts=(f"-c listen_addresses='' -c unix_socket_directories={sock} "
                  f"-c unix_socket_permissions=0700 -c fsync=off -p 54382")
            need(run([BINARY/"pg_ctl","-D",data,"-o",opts,"-l",root/"postgres.log",
                      "-w","start"],30).returncode==0,"PRIVATE_PG_START_FAILED")
            started=True
            report["lanes"]=restore_and_rehearse(sock,archives)
            report["status"]="PASS_REAL_PRODUCTION_SCHEMA_ISOLATED_FINANCE_OWNER_REHEARSAL"
        finally:
            if started:
                need(run([BINARY/"pg_ctl","-D",data,"-m","immediate","-w","stop"],30).returncode==0,
                     "PRIVATE_PG_STOP_FAILED")
    return report
if __name__=="__main__":
    try:
        print(json.dumps(main(),sort_keys=True))
    except (Hold,ValueError,OSError,subprocess.SubprocessError) as exc:
        print(json.dumps({"schema":SCHEMA,"status":"HOLD","reason":str(exc)[:128],
                          "productionDatabasesConnected":False,
                          "financialReleaseAuthorized":False},sort_keys=True))
        sys.exit(2)

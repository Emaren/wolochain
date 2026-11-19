#!/usr/bin/env python3
"""WE1 C03 disposable PostgreSQL16 evidence harness. NEVER targets an existing cluster."""
import hashlib, json, os, pathlib, subprocess, tempfile, getpass, shutil, time
BIN=pathlib.Path(os.environ.get("WE1_C03_PG16_BIN") or ("/usr/lib/postgresql/16/bin" if pathlib.Path("/usr/lib/postgresql/16/bin/initdb").is_file() else "/opt/homebrew/opt/postgresql@16/bin"))
assert all((BIN/x).is_file() for x in ("initdb","pg_ctl","psql","postgres"))
def sha(x):return hashlib.sha256(x).hexdigest()
def run(cmd,**kwargs):
 p=subprocess.run([str(x) for x in cmd],text=True,capture_output=True,timeout=35,**kwargs)
 return p
def expect(b,why):
 if not b:raise RuntimeError("FAILED "+why)
def textsql(s,username=None,ok=True):
 cmd=[BIN/"psql","-X","-A","-t","-v","ON_ERROR_STOP=1","-h",sock,"-p",str(port),"-U",username or actor,"-d","postgres","-c",s]
 p=run(cmd);expect((p.returncode==0)==ok,"PSQL "+repr(s)+" "+p.stderr[-350:]);return p.stdout.strip()
def probe(sql,u,ok=True):
 p=run([BIN/"psql","-X","-q","-t","-A","-v","ON_ERROR_STOP=1","-h",sock,"-p",str(port),"-U",u,"-d","postgres","-c",sql])
 expect((p.returncode==0)==ok,"PROBE "+u+" "+sql+" "+p.stderr[-250:]);return p
def got(line):
 writer.stdin.write(line+"\n\\echo C03_END\n");writer.stdin.flush()
 lines=[]
 for i in range(20):
  s=writer.stdout.readline()
  if not s:raise RuntimeError("WRITER_EXIT "+str(lines))
  lines.append(s.rstrip())
  if "C03_END" in s:return "\n".join(lines)
 raise RuntimeError("WRITER_NO_SENTINEL")
def got_on(proc, line):
 proc.stdin.write(line+"\n\\echo C03_END\n")
 proc.stdin.flush()
 lines=[]
 for _ in range(20):
  msg=proc.stdout.readline()
  if not msg: raise RuntimeError("SECOND_SESSION_EXIT "+str(lines))
  lines.append(msg.rstrip())
  if "C03_END" in msg: return "\n".join(lines)
 raise RuntimeError("SECOND_SESSION_NO_SENTINEL")

def main():
    global sock, port, actor, writer
    if os.environ.get("WE1_C03_DISPOSABLE_ONLY") != "1":
        raise RuntimeError("C03_DISPOSABLE_EXPLICIT_OPT_IN_REQUIRED")
    with tempfile.TemporaryDirectory(prefix="we1-c03-pg16-disposable-") as root:
     root=pathlib.Path(root)
     expect(root.name.startswith("we1-c03-pg16-disposable-") and root.parent!=pathlib.Path("/var/lib/postgresql"),"path")
     data=root/"cluster";sp=root/"socket";sp.mkdir(mode=0o700);sock=str(sp)
     port=57000+(os.getpid()%3000);actor=getpass.getuser()
     init=run([BIN/"initdb","-D",data,"--no-sync","--auth-local=trust","--auth-host=reject"])
     expect(init.returncode==0,"INITDB "+init.stderr[-700:])
     expect((data/"PG_VERSION").read_text().strip()=="16","PG_VERSION")
     hba=data/"pg_hba.conf";orig=hba.read_bytes();origsha=sha(orig)
     params=f"-c listen_addresses= -c unix_socket_directories={sock} -c port={port} -c max_connections=15"
     def ctl(*args):
      return run([BIN/"pg_ctl","-D",data,*args])
     def start():
      p=ctl("-o",params,"-w","-l",root/"postgres.log","start");expect(p.returncode==0,"PG_START "+p.stderr+" "+p.stdout[-400:])
     def stop():
      p=ctl("-m","immediate","-w","stop");expect(p.returncode==0,"PG_STOP "+p.stderr)
     writer=None;pool_writer=None;started=False
     try:
      start();started=True
      # Plain synthetic fixture. Owner is NOLOGIN; legacy writer and reader LOGIN.
      textsql("CREATE ROLE c03_guarded_owner NOLOGIN; CREATE ROLE c03_legacy_writer LOGIN; CREATE ROLE c03_reader LOGIN;")
      textsql("CREATE TABLE public.c03_ledger(id serial primary key, val int not null); ALTER TABLE public.c03_ledger OWNER TO c03_guarded_owner; ALTER SEQUENCE public.c03_ledger_id_seq OWNER TO c03_guarded_owner;")
      textsql("GRANT USAGE ON SCHEMA public TO c03_legacy_writer,c03_reader; GRANT SELECT,INSERT,UPDATE,DELETE ON public.c03_ledger TO c03_legacy_writer; GRANT USAGE,UPDATE ON SEQUENCE public.c03_ledger_id_seq TO c03_legacy_writer; GRANT SELECT ON public.c03_ledger TO c03_reader;")
      textsql("CREATE FUNCTION public.c03_definer_write() RETURNS void LANGUAGE sql SECURITY DEFINER AS $$ INSERT INTO public.c03_ledger(val) VALUES(777); $$; ALTER FUNCTION public.c03_definer_write() OWNER TO c03_guarded_owner;")
      textsql("GRANT EXECUTE ON FUNCTION public.c03_definer_write() TO c03_legacy_writer;")
      before=textsql("SELECT rolcanlogin::text FROM pg_roles WHERE rolname='c03_legacy_writer'; SELECT relacl::text FROM pg_class WHERE oid='public.c03_ledger'::regclass; SELECT relacl::text FROM pg_class WHERE oid='public.c03_ledger_id_seq'::regclass; SELECT proacl::text FROM pg_proc WHERE oid='public.c03_definer_write()'::regprocedure")
      writer=subprocess.Popen([str(BIN/"psql"),"-X","-q","-t","-A","-v","ON_ERROR_STOP=0","-h",sock,"-p",str(port),"-U","c03_legacy_writer","-d","postgres"],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,bufsize=1)
      expect("1" in got("SELECT 1;"),"preconnected writer startup")
      pool_writer=subprocess.Popen([str(BIN/"psql"),"-X","-q","-t","-A","-v","ON_ERROR_STOP=0","-h",sock,"-p",str(port),"-U","c03_legacy_writer","-d","postgres"],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,bufsize=1)
      first_id=got("SELECT pg_backend_pid();").splitlines()[0].strip()
      second_id=got_on(pool_writer,"SELECT pg_backend_pid();").splitlines()[0].strip()
      expect(first_id.isdigit() and second_id.isdigit() and first_id!=second_id,"distinct persistent writer backends")
      initial=got("INSERT INTO public.c03_ledger(val) VALUES(1);")
      expect("ERROR" not in initial,"initial connected write denied unexpectedly: "+initial)
      expect(textsql("SELECT count(*) FROM public.c03_ledger WHERE val=1")=="1","initial preconnected writer insert not visible")
      # A live HBA reload only affects NEW connections. Existing sessions are not evicted.
      # Exercise the counterexample inside this fresh disposable cluster only.
      deny_reload=b"\n".join((b"# C03 DISPOSABLE RELOAD TEST ONLY",
                               b"local all all reject",
                               b"local replication all reject",
                               b"host all all 0.0.0.0/0 reject",
                               b"host all all ::/0 reject"))+b"\n"
      hba.write_bytes(deny_reload)
      reload_result=ctl("reload")
      expect(reload_result.returncode==0,"HBA reload refused "+reload_result.stderr)
      new_conn=run([BIN/"psql","-X","-h",sock,"-p",str(port),"-U",actor,"-d","postgres","-c","SELECT 1"])
      expect(new_conn.returncode!=0 and ("reject" in new_conn.stderr.lower() or "pg_hba" in new_conn.stderr.lower()),"HBA reload must deny fresh connection")
      live_write=got("INSERT INTO public.c03_ledger(val) VALUES(99); SELECT count(*) FROM public.c03_ledger WHERE val=99;")
      expect("ERROR" not in live_write and "1" in live_write.splitlines(),"already connected writer survives all-reject HBA reload: "+live_write)
      retained=got_on(pool_writer,"SELECT pg_backend_pid(); INSERT INTO public.c03_ledger(val) VALUES(98); SELECT count(*) FROM public.c03_ledger WHERE val=98;")
      expect("ERROR" not in retained and second_id in retained.splitlines() and "1" in retained.splitlines(),"second backend survives all-reject HBA reload: "+retained)
      hba.write_bytes(orig)
      reload_result=ctl("reload")
      expect(reload_result.returncode==0,"HBA reload inverse failed "+reload_result.stderr)
      expect(textsql("SELECT count(*) FROM public.c03_ledger WHERE val=99")=="1","HBA counterexample write did not persist")
      textsql("ALTER ROLE c03_legacy_writer NOLOGIN;")
      expect(probe("SELECT 1;","c03_legacy_writer",False).returncode!=0,"NOLOGIN must deny new")
      still=got("INSERT INTO public.c03_ledger(val) VALUES(2);")
      expect("ERROR" not in still,"NOLOGIN should not revoke existing session DML")
      # Critical bypass: SECURITY DEFINER remains callable until its EXECUTE is revoked.
      attack=got("SELECT public.c03_definer_write();")
      expect("ERROR" not in attack,"definer baseline should bypass NOLOGIN")
      # Enforce an actual synthetic permissions fence, with both direct and transitive revocations.
      textsql("REVOKE ALL PRIVILEGES ON TABLE public.c03_ledger FROM c03_legacy_writer; REVOKE ALL PRIVILEGES ON SEQUENCE public.c03_ledger_id_seq FROM c03_legacy_writer; REVOKE ALL ON FUNCTION public.c03_definer_write() FROM PUBLIC,c03_legacy_writer;")
      denied1=got("INSERT INTO public.c03_ledger(val) VALUES(3);")
      denied2=got("SELECT nextval('public.c03_ledger_id_seq');")
      denied3=got("SELECT public.c03_definer_write();")
      for i,s in enumerate((denied1,denied2,denied3),1):expect("ERROR" in s,"denial existing client "+str(i)+" "+s)
      denied_second=(got_on(pool_writer,"INSERT INTO public.c03_ledger(val) VALUES(444);"),
                     got_on(pool_writer,"SELECT nextval('public.c03_ledger_id_seq');"),
                     got_on(pool_writer,"SELECT public.c03_definer_write();"))
      expect(all("ERROR" in msg for msg in denied_second),"second backend DML/seq/definer still authorized "+str(denied_second))
      expect(second_id in got_on(pool_writer,"SELECT pg_backend_pid();").splitlines(),"second backend identity drift")
      # PostgreSQL role membership is a separate transitive grant path.
      # These operations occur ONLY in this fresh, disposable synthetic cluster.
      textsql("CREATE ROLE c03_inherited_writer NOLOGIN; GRANT c03_inherited_writer TO c03_legacy_writer WITH INHERIT TRUE; GRANT INSERT ON TABLE public.c03_ledger TO c03_inherited_writer; GRANT USAGE,UPDATE ON SEQUENCE public.c03_ledger_id_seq TO c03_inherited_writer; GRANT EXECUTE ON FUNCTION public.c03_definer_write() TO c03_inherited_writer;")
      expect(textsql("SELECT pg_has_role('c03_legacy_writer','c03_inherited_writer','USAGE')")=="t","role inheritance unexpected")
      inherited=(got_on(pool_writer,"INSERT INTO public.c03_ledger(val) VALUES(510);"),
                 got_on(pool_writer,"SELECT nextval('public.c03_ledger_id_seq');"),
                 got_on(pool_writer,"SELECT public.c03_definer_write();"))
      expect(all("ERROR" not in msg for msg in inherited),"inherited group bypass not reproduced: "+str(inherited))
      expect(textsql("SELECT count(*) FROM public.c03_ledger WHERE val=510")=="1","inherited committed row absent")
      textsql("REVOKE ALL PRIVILEGES ON TABLE public.c03_ledger FROM c03_inherited_writer; REVOKE ALL PRIVILEGES ON SEQUENCE public.c03_ledger_id_seq FROM c03_inherited_writer; REVOKE EXECUTE ON FUNCTION public.c03_definer_write() FROM c03_inherited_writer; REVOKE c03_inherited_writer FROM c03_legacy_writer; DROP ROLE c03_inherited_writer;")
      closed=(got_on(pool_writer,"INSERT INTO public.c03_ledger(val) VALUES(511);"),
              got_on(pool_writer,"SELECT nextval('public.c03_ledger_id_seq');"),
              got_on(pool_writer,"SELECT public.c03_definer_write();"))
      expect(all("ERROR" in msg for msg in closed),"inherited role path not closed: "+str(closed))
      expect(probe("SELECT count(*) FROM public.c03_ledger","c03_reader").returncode==0,"reader continuity")
      expect(textsql("SELECT has_function_privilege('c03_legacy_writer','public.c03_definer_write()','EXECUTE')")=="f","definer ACL")
      expect(textsql("SELECT has_sequence_privilege('c03_legacy_writer','public.c03_ledger_id_seq','USAGE')")=="f","sequence ACL")
      # Evidence that on-disk pg_hba.conf survives PG shutdown and restart and denies all client auth.
      pool_writer.terminate()
      try:pool_writer.communicate(timeout=5)
      except subprocess.TimeoutExpired:pool_writer.kill();pool_writer.communicate()
      pool_writer=None
      writer.terminate()
      try:writer.communicate(timeout=5)
      except subprocess.TimeoutExpired:writer.kill();writer.communicate()
      writer=None
      stop();started=False
      deny=b"# WE1 C03 DISPOSABLE ONLY; NEVER for production\nlocal all all reject\nlocal replication all reject\nhost all all 0.0.0.0/0 reject\nhost all all ::/0 reject\n"
      hba.write_bytes(deny)
      expect(sha(hba.read_bytes())==sha(deny),"deny HBA source")
      start();started=True
      for i in range(2):
       attempt=run([BIN/"psql","-X","-h",sock,"-p",str(port),"-U",actor,"-d","postgres","-c","SELECT 1"])
       expect(attempt.returncode!=0 and ("reject" in attempt.stderr.lower() or "pg_hba" in attempt.stderr.lower()),"all-client rejection")
       if i==0:stop();started=False;start();started=True
      # Simulated interrupted restoration must not reopen auth on a newly restarted server.
      expect(sha(hba.read_bytes())==sha(deny),"restart drift")
      stop();started=False
      hba.write_bytes(orig);expect(sha(hba.read_bytes())==origsha,"HBA exact bytes")
      start();started=True
      # Exact synthetic SQL inverse, including role LOGIN and all directly granted accesses.
      textsql("ALTER ROLE c03_legacy_writer LOGIN; REVOKE SELECT ON TABLE public.c03_ledger FROM c03_reader; REVOKE ALL ON FUNCTION public.c03_definer_write() FROM c03_guarded_owner; GRANT SELECT,INSERT,UPDATE,DELETE ON public.c03_ledger TO c03_legacy_writer; GRANT SELECT ON TABLE public.c03_ledger TO c03_reader; GRANT USAGE,UPDATE ON SEQUENCE public.c03_ledger_id_seq TO c03_legacy_writer; GRANT EXECUTE ON FUNCTION public.c03_definer_write() TO PUBLIC,c03_guarded_owner,c03_legacy_writer;")
      after=textsql("SELECT rolcanlogin::text FROM pg_roles WHERE rolname='c03_legacy_writer'; SELECT relacl::text FROM pg_class WHERE oid='public.c03_ledger'::regclass; SELECT relacl::text FROM pg_class WHERE oid='public.c03_ledger_id_seq'::regclass; SELECT proacl::text FROM pg_proc WHERE oid='public.c03_definer_write()'::regprocedure")
      expect(before==after,"SQL raw ACL/role parity: "+repr((before,after)))
      expect(probe("INSERT INTO public.c03_ledger(val) VALUES(4);","c03_legacy_writer").returncode==0,"inverse restored writer only on isolated temp cluster")
      # Synthetic nonfinancial writer, never used as an actual production admission.
      textsql("CREATE ROLE c03_social_owner NOLOGIN NOINHERIT; CREATE ROLE c03_social_writer LOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS; CREATE TABLE public.c03_social_messages(id serial primary key, body text not null); ALTER TABLE public.c03_social_messages OWNER TO c03_social_owner; ALTER SEQUENCE public.c03_social_messages_id_seq OWNER TO c03_social_owner; GRANT USAGE ON SCHEMA public TO c03_social_writer; GRANT INSERT(body) ON TABLE public.c03_social_messages TO c03_social_writer; GRANT USAGE ON SEQUENCE public.c03_social_messages_id_seq TO c03_social_writer;")
      expect(probe("INSERT INTO public.c03_social_messages(body) VALUES('synthetic hello');","c03_social_writer").returncode==0,"limited social INSERT rejected")
      expect(probe("INSERT INTO public.c03_ledger(val) VALUES(900);","c03_social_writer",False).returncode!=0,"social writer financial table direct DML succeeded")
      expect(probe("SELECT nextval('public.c03_ledger_id_seq');","c03_social_writer",False).returncode!=0,"social writer financial sequence succeeded")
      expect(probe("SET ROLE c03_guarded_owner;","c03_social_writer",False).returncode!=0,"social writer assumed finance owner")
      original_function_acl=textsql("SELECT proacl::text FROM pg_proc WHERE oid='public.c03_definer_write()'::regprocedure")
      expect(textsql("SELECT has_function_privilege('c03_social_writer','public.c03_definer_write()','EXECUTE')")=="t","PUBLIC definer path counterexample not visible")
      expect(probe("SELECT public.c03_definer_write();","c03_social_writer").returncode==0,"PUBLIC SECURITY DEFINER bypass not reproduced")
      textsql("REVOKE EXECUTE ON FUNCTION public.c03_definer_write() FROM PUBLIC;")
      expect(probe("SELECT public.c03_definer_write();","c03_social_writer",False).returncode!=0,"social writer finance SECURITY DEFINER still callable")
      expect(probe("INSERT INTO public.c03_social_messages(body) VALUES('still permitted');","c03_social_writer").returncode==0,"social INSERT lost after financial definer revocation")
      # Reconstruct the entire original raw proacl order, not just PUBLIC semantics.
      textsql("REVOKE EXECUTE ON FUNCTION public.c03_definer_write() FROM c03_guarded_owner,c03_legacy_writer,PUBLIC; GRANT EXECUTE ON FUNCTION public.c03_definer_write() TO PUBLIC,c03_guarded_owner,c03_legacy_writer;")
      inverse_function_acl=textsql("SELECT proacl::text FROM pg_proc WHERE oid='public.c03_definer_write()'::regprocedure")
      expect(inverse_function_acl==original_function_acl,"PUBLIC function ACL exact inverse drift "+repr((original_function_acl,inverse_function_acl)))
      # New synthetic trigger path: a restricted social INSERT must not be able
      # to execute an OWNER-owned finance definer indirectly via a trigger.
      textsql("CREATE FUNCTION public.c03_hidden_finance_trigger() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path TO pg_catalog,public AS $$ BEGIN INSERT INTO public.c03_ledger(val) VALUES (888); RETURN NEW; END $$; ALTER FUNCTION public.c03_hidden_finance_trigger() OWNER TO c03_guarded_owner; REVOKE EXECUTE ON FUNCTION public.c03_hidden_finance_trigger() FROM PUBLIC; CREATE TRIGGER c03_social_finance_echo AFTER INSERT ON public.c03_social_messages FOR EACH ROW EXECUTE FUNCTION public.c03_hidden_finance_trigger();")
      expect(textsql("SELECT has_function_privilege('c03_social_writer','public.c03_hidden_finance_trigger()','EXECUTE')")=="f","restricted social role unexpectedly has direct trigger EXECUTE")
      before_trigger_count=textsql("SELECT count(*) FROM public.c03_ledger WHERE val=888")
      expect(probe("INSERT INTO public.c03_social_messages(body) VALUES('trigger bypass');","c03_social_writer").returncode==0,"social trigger insert rejected")
      after_trigger_count=textsql("SELECT count(*) FROM public.c03_ledger WHERE val=888")
      expect(int(after_trigger_count)==int(before_trigger_count)+1,"social INSERT did not provoke hidden financial trigger write")
      textsql("DROP TRIGGER c03_social_finance_echo ON public.c03_social_messages; DROP FUNCTION public.c03_hidden_finance_trigger();")
      expect(probe("INSERT INTO public.c03_social_messages(body) VALUES('trigger removed');","c03_social_writer").returncode==0,"legitimate social INSERT failed after trigger removal")
      expect(textsql("SELECT count(*) FROM public.c03_ledger WHERE val=888")==after_trigger_count,"finance insert persisted despite trigger removal")
      expect(textsql("SELECT to_regprocedure('public.c03_hidden_finance_trigger()') IS NULL")=="t","trigger function inverse not exact")
      expect(textsql("SELECT count(*) FROM pg_trigger WHERE tgname='c03_social_finance_echo' AND NOT tgisinternal")=="0","trigger relation inverse not exact")
      print(json.dumps({"status":"PASS","postgres":"16","ephemeral_cluster":True,"tcp_listening":False,"case_count":29,"checks":["PG16 private initdb/version","social INSERT activates financial SECURITY DEFINER trigger despite no direct EXECUTE","trigger removal restores financial negative while social INSERT succeeds","trigger and helper function exact absence restored","dedicated social-only writer grants insert narrowly","social writer direct financial table denied","social writer finance sequence denied","social writer SET ROLE finance owner denied","PUBLIC SECURITY DEFINER finance write counterexample","PUBLIC definer revocation prevents finance call and exact ACL inverse","inherited-role membership bypasses direct writer ACL revocation","revoke inherited-role privileges and membership denies all three write paths","distinct persistent writer backends","second existing writer retains committed DML after HBA reload","second writer denied DML sequence and SECURITY DEFINER after revocation","HBA live reload denies new clients","existing writer survives all-reject HBA reload","existing writer persists after NOLOGIN","new writer denied NOLOGIN","definer bypass exists before revocation","synthetic ACL revocation denies preconnected writer","sequence bypass denied","SECURITY DEFINER denied","reader SELECT survives","all-client HBA persisted over two restarts","no auth release after restart","HBA byte-exact rollback","role+ACL preimage byte parity","isolated inverse returns initial writer rights"],"hba_original_sha256":origsha,"hba_deny_sha256":sha(deny)},sort_keys=True))
     finally:
      if pool_writer is not None:
       pool_writer.terminate()
       try:pool_writer.communicate(timeout=3)
       except subprocess.TimeoutExpired:pool_writer.kill();pool_writer.communicate()
      if writer is not None:
       writer.terminate()
       try:writer.communicate(timeout=3)
       except:writer.kill()
      if started:
       p=ctl("-m","immediate","-w","stop")
       if p.returncode!=0:print("CLEANUP_WARNING",p.stderr)



if __name__ == "__main__":
    main()

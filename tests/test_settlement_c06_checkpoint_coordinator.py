import copy
import hashlib
import os
from pathlib import Path
import sys
import tempfile
import time
import subprocess
import select
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
import settlement_c06_checkpoint_coordinator as c

def h(s):return hashlib.sha256(s.encode()).hexdigest()
def plan():
    return {"schema":"wolo.c06.coordinated-plan.v1",**{k:h(k) for k in (
        "source","host","boot","scope","producer_prestate","shared_database_scope",
        "b_prepare","we2_window","archive_budget","quarantine","restart_plan",
        "abort_plan","recovery_target")}}

class Driver:
    is_disposable_fixture=True
    def __init__(self, fail=None):
        self.fail=fail;self.calls=[]
    def op(self,n):
        self.calls.append(n)
        if self.fail==n:raise RuntimeError(n)
    def verify_lease(self,p):self.op("lease")
    def authenticate_and_consume(self,phase,p,prev):
        self.op("admit_"+phase)
        return dict(phase=phase,plan=c.validate_plan(p),previous=prev,
                    packet=h(phase),witness=h("witness"+phase),
                    nonce=h("nonce"+phase),expires=int(time.time())+60)
    def anchor(self,p,s,t):self.op("anchor_"+s)
    def fence_and_deny_reconnect(self,p):self.op("fence");return h("fence")
    def checkpoint(self,p):self.op("checkpoint");return h("checkpoint")
    def capture_encrypted(self,p,x):self.op("capture");return h("cipher")
    def verify_frozen(self,p,x):self.op("frozen");return True
    def verify_receiver(self,x):self.op("receiver");return x
    def restore_isolated(self,x):self.op("restore");return x
    def restore_original_nonfinancial_services(self,p):
        self.op("restart");return h("post")
    def verify_quarantine_and_poststate(self,p):self.op("post");return True

class TestCoordinator(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name).resolve()
        self.root.chmod(0o700);self.p=plan();self.sha=c.validate_plan(self.p)
    def tearDown(self):self.tmp.cleanup()
    def run_driver(self,d):
        with c.Journal(self.root,self.sha) as j:
            return c.Coordinator(self.p,j,d).run()
    def test_order_and_no_replay(self):
        d=Driver();self.assertEqual(self.run_driver(d),h("cipher"))
        with c.Journal(self.root,self.sha) as j:
            self.assertEqual([r["step"] for r in j.records],list(c.STEPS))
            self.assertEqual(c.recovery_disposition(j),"COMPLETE_REVERIFY_EXTERNAL_ANCHOR")
        with self.assertRaises(c.Hold):self.run_driver(Driver())
    def test_all_failure_boundaries(self):
        for name in ("admit_capture","anchor_FENCE_INTENT","fence","checkpoint",
                     "capture","receiver","admit_restore","restore","admit_resume",
                     "anchor_RESTART_INTENT","restart","post"):
            with self.subTest(name=name),tempfile.TemporaryDirectory(dir=self.root) as t:
                path=Path(t);path.chmod(0o700);d=Driver(name)
                with c.Journal(path,self.sha) as j:
                    with self.assertRaises(RuntimeError):
                        c.Coordinator(self.p,j,d).run()
                with c.Journal(path,self.sha) as j:
                    self.assertNotEqual(c.recovery_disposition(j),"COMPLETE_REVERIFY_EXTERNAL_ANCHOR")
                    if name!="admit_capture":
                        with self.assertRaises(c.Hold):
                            c.Coordinator(self.p,j,Driver()).run()
                if name not in ("restart","post"):self.assertNotIn("restart",d.calls)
    def test_ambiguous_restart(self):
        d=Driver("restart")
        with self.assertRaises(RuntimeError):self.run_driver(d)
        with c.Journal(self.root,self.sha) as j:
            self.assertEqual(c.recovery_disposition(j),
                "AMBIGUOUS_EFFECT_FRESH_CONTAINMENT_AUTHORITY_REQUIRED")
    def test_corrupt_and_gap(self):
        with self.assertRaises(RuntimeError):self.run_driver(Driver("fence"))
        (self.root/"01.json").write_text("bad")
        with self.assertRaises(c.Hold):
            with c.Journal(self.root,self.sha):pass
        (self.root/"01.json").unlink()
        (self.root/"03.json").touch(mode=0o600)
        with self.assertRaises(c.Hold):
            with c.Journal(self.root,self.sha):pass
    def test_cipher_mismatch(self):
        d=Driver();d.restore_isolated=lambda x:h("different")
        with self.assertRaises(c.Hold):self.run_driver(d)
        self.assertNotIn("restart",d.calls)
    def test_live_refusal(self):
        d=Driver();d.is_disposable_fixture=False
        with self.assertRaises(c.Hold):self.run_driver(d)
        self.assertFalse(d.calls)
    def test_plan_missing_shared_scope(self):
        p=copy.deepcopy(self.p);del p["shared_database_scope"]
        with self.assertRaises(c.Hold):c.validate_plan(p)
    def test_wrong_phase_binding(self):
        d=Driver();orig=d.authenticate_and_consume
        d.authenticate_and_consume=lambda a,b,e:orig("wrong",b,e)
        with self.assertRaises(c.Hold):self.run_driver(d)
        self.assertNotIn("fence",d.calls)
    def test_expired_capture_does_not_progress_to_checkpoint(self):
        d=Driver()
        orig=d.fence_and_deny_reconnect
        def fence(p):
            x=orig(p)
            clock[0]+=120
            return x
        clock=[1000]
        d.fence_and_deny_reconnect=fence
        with patch.object(c.time,"time",side_effect=lambda:clock[0]):
            with self.assertRaisesRegex(c.Hold,"PHASE_EXPIRED"):
                self.run_driver(d)
        self.assertNotIn("checkpoint",d.calls)
        self.assertNotIn("restart",d.calls)
    def test_deterministic_handoff_never_claims_authority(self):
        with c.Journal(self.root,self.sha) as j:
            initial=c.phase_handoff(j)
            self.assertEqual(initial,c.phase_handoff(j))
            self.assertEqual(initial["payload"]["next_action"],
                             "OBTAIN_EXACT_ADMISSION_AND_EXTERNAL_LEASE")
            j.append("ADMITTED",h("admitted"))
            j.append("FENCE_INTENT",h("intent"))
            result=c.phase_handoff(j)
            self.assertEqual(result["sha256"],c.digest(c.canonical(result["payload"])))
            self.assertEqual(result["payload"]["next_action"],
                             "CONTAIN_AMBIGUOUS_EFFECT_WITH_FRESH_AUTHORITY")
            self.assertFalse(result["payload"]["gate_closure_claimed"])
            self.assertFalse(result["payload"]["external_anchor_verified"])
    def test_actual_process_death_after_intent(self):
        pid=os.fork()
        if pid==0:
            with c.Journal(self.root,self.sha) as j:
                j.append("ADMITTED",h("receipt"))
                j.append("FENCE_INTENT",h("prestate"))
                os._exit(74)
        _,status=os.waitpid(pid,0)
        self.assertEqual(os.WEXITSTATUS(status),74)
        with c.Journal(self.root,self.sha) as j:
            self.assertEqual(c.recovery_disposition(j),
                "AMBIGUOUS_EFFECT_FRESH_CONTAINMENT_AUTHORITY_REQUIRED")
            with self.assertRaises(c.Hold):c.Coordinator(self.p,j,Driver()).run()
@unittest.skipUnless(os.geteuid()!=0 and os.environ.get("C06_PG_BIN"),
                     "explicit disposable PG16 path required")
class PhysicalReconnectTests(unittest.TestCase):
    def test_preconnected_writer_and_reconnect_after_shutdown(self):
        pg=Path(os.environ["C06_PG_BIN"])
        with tempfile.TemporaryDirectory(prefix="c06-reconnect-") as td:
            root=Path(td).resolve();data=root/"data";sock=root/"s"
            sock.mkdir(mode=0o700)
            def run(args,check=True):
                return subprocess.run([str(x) for x in args],capture_output=True,
                                      timeout=30,check=check)
            def ctl(action):
                args=[pg/"pg_ctl","-D",data,"-w"]
                if action=="start":args+=["-l",sock/"server.log","-o",
                                         "-h '' -k "+str(sock)+" -p 56501","start"]
                else:args+=["-m","fast","stop"]
                return run(args)
            def args(db,user):
                return [str(pg/"psql"),"-X","-w","-At","-v","ON_ERROR_STOP=1",
                        "-h",str(sock),"-p","56501","-U",user,"-d",db]
            run([pg/"initdb","-D",data,"-U","fixture_admin",
                 "--auth-local=trust","--auth-host=reject","--no-locale"])
            active=False;client=None
            try:
                ctl("start");active=True
                system_id=run(args("postgres","fixture_admin")+["-c","SELECT system_identifier FROM pg_control_system()"]).stdout.decode().strip()
                run(args("postgres","fixture_admin")+["-c","CREATE ROLE fixture_writer LOGIN"])
                for db in ("aoe2hd_db","aoe2de_db","website_shared"):
                    run(args("postgres","fixture_admin")+["-c","CREATE DATABASE "+db])
                    run(args(db,"fixture_admin")+["-c",
                        "CREATE TABLE t(id integer); GRANT INSERT, SELECT ON t TO fixture_writer"])
                client=subprocess.Popen(args("aoe2hd_db","fixture_writer"),
                                        stdin=subprocess.PIPE,stdout=subprocess.PIPE,
                                        stderr=subprocess.PIPE,bufsize=0)
                client.stdin.write(b"BEGIN;\nINSERT INTO t VALUES (99);\nSELECT 'PRECONNECTED_UNCOMMITTED';\n")
                ready=b"";deadline=time.monotonic()+8
                while b"PRECONNECTED_UNCOMMITTED" not in ready and time.monotonic()<deadline:
                    if select.select([client.stdout],[],[],.2)[0]:
                        block=os.read(client.stdout.fileno(),4096)
                        if not block:break
                        ready+=block
                self.assertIn(b"PRECONNECTED_UNCOMMITTED",ready)
                ctl("stop");active=False
                # Preconnected transaction cannot commit after the clean stop.
                # BrokenPipe or nonzero psql exit is an expected failure.
                try:
                    client.stdin.write(b"COMMIT;\n")
                    client.stdin.close()
                except BrokenPipeError:pass
                client.wait(timeout=8)
                self.assertNotEqual(client.returncode,0)
                for db in ("aoe2hd_db","aoe2de_db","website_shared"):
                    for user in ("fixture_writer","fixture_admin"):
                        self.assertNotEqual(run(args(db,user)+["-c","SELECT 1"],False).returncode,0)
                from settlement_c06_native_pg_checkpoint import parse_control,inspect_tree
                raw=run([pg/"pg_controldata",data]).stdout
                self.assertIn(b"shut down",raw)
                control=parse_control(raw,system_id)
                fd=os.open(data,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
                try:
                    self.assertEqual(len(inspect_tree(fd,control)),64)
                finally:os.close(fd)
                print("PASS_NATIVE_PG16_CONTROL_AND_REDO_SEGMENT",flush=True)
                # Deliberate fixture-only resume, no autonomous retry.
                ctl("start");active=True
                for db in ("aoe2hd_db","aoe2de_db","website_shared"):
                    self.assertEqual(run(args(db,"fixture_admin")+["-c","SELECT count(*) FROM t"]).stdout,b"0\n")
                self.assertEqual(run(args("postgres","fixture_admin")+["-c","SHOW listen_addresses"]).stdout,b"\n")
                ctl("stop");active=False
                print("PASS_DISPOSABLE_PRECONNECTED_ROLLBACK_SIX_RECONNECT_DENIALS_THREE_DATABASE_RESTART",flush=True)
            finally:
                if client is not None and client.poll() is None:
                    client.kill();client.wait(timeout=5)
                if active:ctl("stop")

if __name__=="__main__":unittest.main()


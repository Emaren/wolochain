import copy
import hashlib
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
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
if __name__=="__main__":unittest.main()

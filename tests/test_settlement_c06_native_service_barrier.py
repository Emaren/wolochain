import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
import settlement_c06_native_service_barrier as b
from settlement_c06_checkpoint_rehearsal import Hold

def scope():
    stop=sorted(b.REQUIRED-{"postgresql.service","postgresql@16-main.service"}, key=lambda u:(not u.endswith((".timer",".socket",".path")),u))
    stop+=["postgresql@16-main.service","postgresql.service"]
    resume=["postgresql@16-main.service","postgresql.service"]+sorted([u for u in stop if u not in ("postgresql.service","postgresql@16-main.service")],key=lambda u:(u.endswith((".timer",".socket",".path")),u))
    return {"stop":stop,"resume":[u for u in resume if u not in b.DORMANT_DENY],"prestate":{
        u:{"Id":u,"LoadState":"loaded","ActiveState":"inactive" if u in b.DORMANT_DENY else "active"} for u in stop}}
class ScopeTests(unittest.TestCase):
    def test_native_scope(self):self.assertEqual(len(b.validate_scope(scope())),64)
    def test_missing_producer(self):
        for unit in b.REQUIRED:
            p=scope();p["stop"].remove(unit)
            if unit in p["resume"]:p["resume"].remove(unit)
            del p["prestate"][unit]
            with self.assertRaises(Hold):b.validate_scope(p)
    def test_quarantine_and_traffic(self):
        for unit in b.QUARANTINED|b.NEVER_STOP|{"traffic-ingest.timer"}:
            p=scope();p["stop"].insert(0,unit);p["prestate"][unit]={"Id":unit,"LoadState":"loaded","ActiveState":"inactive"}
            with self.assertRaises(Hold):b.validate_scope(p)
    def test_dormant_financial_producers_never_restart(self):
        for u in b.DORMANT_DENY:
            p=scope();p["resume"].append(u);p["prestate"][u]["ActiveState"]="active"
            with self.assertRaises(Hold):b.validate_scope(p)
    def test_fallback_clients_stop_before_shared_cluster(self):
        for u in ("aoe2hdbets-web-r24.service","aoe2hdbets-web-candidate-3033.service"):
            p=scope();p["stop"].remove(u);p["stop"].append(u)
            with self.assertRaises(Hold):b.validate_scope(p)
    def test_resume_exact(self):
        p=scope();p["resume"].pop()
        with self.assertRaises(Hold):b.validate_scope(p)
    def test_native_effect_admission_precedes_mutation(self):
        events=[]
        def admit(phase,sha,action):events.append("admit")
        def anchor(phase,sha,action):events.append("anchor")
        obj=b.NativeBarrier(scope(),admit_effect=admit,anchor_intent=anchor)
        obj.effect("capture","fixture",lambda:events.append("effect"))
        self.assertEqual(events,["admit","anchor","admit","effect"])
    def test_anchor_failure_no_effect(self):
        def bad(*args):raise RuntimeError("no anchor")
        obj=b.NativeBarrier(scope(),admit_effect=lambda *x:None,anchor_intent=bad)
        effects=[]
        with self.assertRaises(RuntimeError):obj.effect("capture","fixture",lambda:effects.append(1))
        self.assertFalse(effects)
    def test_new_scheduled_activation_paths_are_mandatory(self):
        self.assertEqual(len(b.SCHEDULED_PRODUCERS),10)
        for unit in b.SCHEDULED_PRODUCERS:
            p=scope();p["stop"].remove(unit);p["resume"].remove(unit)
            del p["prestate"][unit]
            with self.assertRaises(Hold):b.validate_scope(p)
    def test_activator_order(self):
        p=scope();u="aoe2hdbets-challenge-reconcile.timer"
        p["stop"].remove(u);p["stop"].append(u)
        with self.assertRaises(Hold):b.validate_scope(p)
        p=scope();p["resume"].remove(u);p["resume"].insert(0,u)
        with self.assertRaises(Hold):b.validate_scope(p)
    def test_actual_socket_and_custody_boundary(self):
        from unittest.mock import patch
        def run(args):
            if args[0]=="ss":return "LISTEN 0 128 127.0.0.1:5432 0.0.0.0:*\n"
            return "Id="+args[-1]+"\nActiveState=inactive\nUnitFileState=masked\n"
        obj=b.NativeBarrier(scope(),admit_effect=lambda *x:None,anchor_intent=lambda *x:None,run=run)
        with patch.object(b,"show",side_effect=lambda u,r:{"Id":u,"ActiveState":"inactive","MainPID":"0"}):
            obj.check_quarantine()
            obj.run=lambda args: "LISTEN 0 128 [::]:8094 [::]:*\n" if args[0]=="ss" else run(args)
            with self.assertRaises(Hold):obj.check_quarantine()
        with patch.object(b,"show",side_effect=lambda u,r:{"Id":u,"ActiveState":"active","MainPID":"123"}):
            with self.assertRaises(Hold):obj.check_quarantine()
if __name__=="__main__":unittest.main()

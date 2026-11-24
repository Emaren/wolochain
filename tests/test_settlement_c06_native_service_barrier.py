import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
import settlement_c06_native_service_barrier as b
from settlement_c06_checkpoint_rehearsal import Hold

def scope():
    stop=sorted(b.REQUIRED-{"postgresql.service","postgresql@16-main.service"})
    stop+=["postgresql@16-main.service","postgresql.service"]
    resume=["postgresql@16-main.service","postgresql.service"]+[u for u in stop if u not in ("postgresql.service","postgresql@16-main.service")]
    return {"stop":stop,"resume":resume,"prestate":{
        u:{"Id":u,"LoadState":"loaded","ActiveState":"active"} for u in stop}}
class ScopeTests(unittest.TestCase):
    def test_native_scope(self):self.assertEqual(len(b.validate_scope(scope())),64)
    def test_missing_producer(self):
        for unit in b.REQUIRED:
            p=scope();p["stop"].remove(unit);p["resume"].remove(unit);del p["prestate"][unit]
            with self.assertRaises(Hold):b.validate_scope(p)
    def test_quarantine_and_traffic(self):
        for unit in b.QUARANTINED|b.NEVER_STOP|{"traffic-ingest.timer"}:
            p=scope();p["stop"].insert(0,unit);p["prestate"][unit]={"Id":unit,"LoadState":"loaded","ActiveState":"inactive"}
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
if __name__=="__main__":unittest.main()

"""New completion-wire tests only; synthetic journals, real fixture signatures."""
import base64
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
import settlement_c06_native_witness as w
import settlement_c06_checkpoint_authority as a
from settlement_c06_checkpoint_coordinator import Journal,STEPS,validate_receipt
from settlement_c06_native_service_barrier import validate_scope
from test_settlement_c06_native_service_barrier import scope
import test_settlement_c06_native_witness as fixtures

class CompletionTests(unittest.TestCase):
    def exercise(self,phase,lost_ack=False):
        fixture=fixtures.NativeProtocol()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        f=fixture.fixture;sc=scope();f.plan["scope"]=validate_scope(sc)
        sha=a.validate_plan(f.plan);fixture.c["plan_sha256"]=sha
        f.q["plan_sha256"]=sha
        localpath=f.root/"local";localpath.mkdir(mode=0o700)
        ep=f.root/"remote-effects";ep.mkdir(mode=0o700)
        sp=f.root/"local-effects";sp.mkdir(mode=0o700)
        def refuse(fn,why):
            with self.assertRaises(w.owner.AuthorityHold,msg=why):fn()
        with Journal(fixture.root,sha) as remote,Journal(localpath,sha) as local:
            if phase=="resume":
                # Synthetic earlier phase evidence only. Resume itself uses
                # a genuine fixture signature and independent nonce consume.
                for step in STEPS[:10]:
                    remote.append(step,"d"*64);local.append(step,"d"*64)
            previous=remote.tip
            q=f.q|dict(phase=phase,operation=a.OPS[phase],previous_journal_sha256=previous)
            packet=f.packet(q);encoded=base64.b64encode(packet).decode()
            def dispatch(payload,**kw):
                return w.dispatch(w.canonical(payload),fixture.c,fixture.old,f.enroll,
                                  remote,fixture.nonces,fixture.crypto,**kw)
            ack=dispatch(dict(action="consume",phase=phase,previous=previous,
                              packet_b64=encoded,plan=f.plan))
            receipt=a.verify_expanded_witness_ack(ack,f.enroll,packet,f.plan,
                 phase=phase,previous=previous,witness_identity="c"*64,**fixture.crypto)
            adm=validate_receipt(receipt,phase,sha,previous)
            local.append(a.PHASE_STEPS[phase][1],adm)
            intent,step=("FENCE_INTENT","FENCED") if phase=="capture" else ("RESTART_INTENT","RESTORED_SERVICES")
            tip=local.append(intent,"e"*64);remote.append(intent,"e"*64)
            bogus=dict(schema="wolo.c06.checkpoint-journal.v1",index=len(remote.records),
                       step=step,plan=sha,previous=tip,evidence="a"*64)
            refuse(lambda:dispatch(dict(action="anchor",plan=f.plan,record=bogus)),
                   "generic anchor cannot skip completion proof")
            self.assertEqual(remote.tip,tip)
            with w.BarrierEffectJournal(ep,f.plan,sc,phase,tip,adm) as re, \
                 w.BarrierEffectJournal(sp,f.plan,sc,phase,tip,adm) as se:
                kw=dict(effect_journal=re,verify_lease=lambda p:p==f.plan)
                base=dict(action="anchor_barrier_completion",plan=f.plan,scope=sc,
                          phase=phase,receipt=receipt,packet_b64=encoded,
                          record=bogus,poststate_sha256="b"*64,effect_tip="a"*64)
                refuse(lambda:dispatch(base),"unadmitted witness provider")
                refuse(lambda:dispatch(base,**kw),"incomplete remote chain")
                client=object.__new__(w.NativeWitnessClient)
                client.plan=f.plan;client.c=fixture.c;client.old=fixture.old
                client.enrollment=f.enroll;client.check=lambda:fixture.crypto
                def exchange(old,p):
                    if p["action"]=="anchor_barrier_completion" and lost_ack:
                        # Remote append succeeds; source sees uncertain outcome.
                        dispatch(p,**kw)
                        raise w.owner.AuthorityHold("FIXTURE_ACK_LOST")
                    return dispatch(p,**kw)
                with patch.object(w,"native_exchange",side_effect=exchange) as transport:
                    binding=w.BarrierEffectBinding(se,verify_phase=lambda:(tip,adm),
                        verify_lease=lambda:True,
                        anchor_native=lambda record:client.anchor_effect(record,
                             scope=sc,phase=phase,receipt=receipt,packet=packet,
                             journal=local,verify_lease=lambda p:p==f.plan),
                        witness_identity="c"*64)
                    args=dict(scope=sc,phase=phase,receipt=receipt,packet=packet,
                              journal=local,binding=binding,poststate_sha256="b"*64,
                              verify_lease=lambda p:p==f.plan)
                    refuse(lambda:client.complete_barrier(**args),"incomplete source chain")
                    for action in se.schedule:
                        binding.admit_effect(phase,sc_sha:=f.plan["scope"],action)
                        binding.anchor_intent(phase,sc_sha,action)
                        binding.admit_effect(phase,sc_sha,action)
                        binding.complete_effect(phase,sc_sha,action)
                    self.assertEqual(se.records,re.records)
                    record=w.barrier_completion_record(f.plan,sc,phase,local,se,tip,adm,"b"*64)
                    valid=base|dict(record=record,effect_tip=se.tip)
                    for bad in (valid|dict(effect_tip="a"*64),
                                valid|dict(poststate_sha256="a"*64),
                                valid|dict(record=record|dict(evidence="a"*64))):
                        refuse(lambda:dispatch(bad,**kw),"completion binding drift")
                    refuse(lambda:dispatch(valid,effect_journal=re,verify_lease=lambda p:False),
                           "independent lease denied")
                    self.assertEqual(remote.tip,tip)
                    if lost_ack:
                        refuse(lambda:client.complete_barrier(**args),"lost completion ACK")
                        self.assertEqual(local.tip,tip)
                        self.assertEqual(remote.records[-1],record)
                    else:
                        self.assertEqual(client.complete_barrier(**args),remote.tip)
                        self.assertEqual(local.records,remote.records)
                    calls=transport.call_count
                    refuse(lambda:client.complete_barrier(**args),"no source retry")
                    self.assertEqual(transport.call_count,calls)
                    refuse(lambda:dispatch(valid,**kw),"no witness replay")
                    self.assertEqual(binding.state,"HOLD")
        print("PASS",phase,"lost_ack" if lost_ack else "exact_completion",flush=True)
    def test_capture(self):self.exercise("capture")
    def test_resume(self):self.exercise("resume")
    def test_lost_ack(self):self.exercise("capture",True)

if __name__=="__main__":unittest.main()

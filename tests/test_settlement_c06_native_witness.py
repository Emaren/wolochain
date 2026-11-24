"""New protocol boundary tests; no real Intel enrollment or native actions."""
import base64
from pathlib import Path
import sys
import unittest
from unittest.mock import patch, Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
import settlement_c06_native_witness as w
import settlement_c06_checkpoint_authority as a
import test_settlement_c06_checkpoint_authority as fixtures
from settlement_c06_checkpoint_coordinator import Journal


class NativeProtocol(unittest.TestCase):
    def setUp(self):
        self.fixture=fixtures.SignatureTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        f=self.fixture
        self.old={"schema":w.legacy.CONFIG_SCHEMA,"source_commit":"7"*40,
                  "owner_enrollment_sha256":w.digest(f.enroll),
                  "owner_der_sha256":f.pin,"host_identity_sha256":f.plan["host"],
                  "controller_files":{k:"a"*64 for k in w.legacy.SOURCES},
                  "witness":{"host":"127.0.0.1","port":22995,"user":"fixture",
                             "identity_path":"/fixture/id","known_hosts_path":"/fixture/known",
                             "known_hosts_sha256":"b"*64,"host_identity_sha256":"c"*64},
                  "crypto":{k:{"path":"/fixture/openssl","sha256":"a"*64}
                            for k in ("runtime","witness")}}
        self.oldraw=w.canonical(self.old)
        self.c={"schema":w.SCHEMA,"source_commit":"1"*40,
                "plan_sha256":a.validate_plan(f.plan),
                "legacy_enrollment_sha256":w.digest(self.oldraw),
                "controller_files":{k:"d"*64 for k in w.SOURCES}|self.old["controller_files"]}
        self.root=f.root/"journal";self.root.mkdir(mode=0o700)
        self.nonces=f.root/"nonces";self.nonces.mkdir(mode=0o700)
        self.crypto={k:v for k,v in f.witness_args().items() if k not in ("phase","previous")}
    def test_exact_config_and_legacy_anchor(self):
        self.assertEqual(w.load_expanded(w.canonical(self.c),self.oldraw),(self.c,self.old))
        for drift in ({"legacy_enrollment_sha256":"e"*64},{"source_commit":"0"*40},
                      {"controller_files":{}},{"controller_files":self.c["controller_files"]|{"settlement_solo_runtime.py":"e"*64}},{"plan_sha256":"not-a-hash"}):
            with self.subTest(drift=drift),self.assertRaises(w.owner.AuthorityHold):
                w.load_expanded(w.canonical(self.c|drift),self.oldraw)
    def test_dispatch_and_anchor_protocol(self):
        f=self.fixture
        req={"action":"consume","phase":"capture","previous":None,
             "packet_b64":base64.b64encode(f.packet()).decode(),"plan":f.plan}
        with Journal(self.root,self.c["plan_sha256"]) as j:
            ack=w.dispatch(w.canonical(req),self.c,self.old,f.enroll,j,self.nonces,self.crypto)
            self.assertTrue(ack["fresh_consumption_confirmed"])
            self.assertFalse(ack["production_authorized"])
            with self.assertRaises(w.owner.AuthorityHold):
                w.dispatch(w.canonical(req),self.c,self.old,f.enroll,j,self.nonces,self.crypto)
            r=j.records[-1]
            ack=w.dispatch(w.canonical({"action":"anchor","plan":f.plan,"record":r}),
                           self.c,self.old,f.enroll,j,self.nonces,self.crypto)
            self.assertEqual(w.verify_anchor_ack(ack,r,"c"*64),j.tip)
            next_record=r|{"index":1,"step":"FENCE_INTENT","previous":j.tip,"evidence":"e"*64}
            payload=w.canonical({"action":"anchor","plan":f.plan,"record":next_record})
            ack=w.dispatch(payload,self.c,self.old,f.enroll,j,self.nonces,self.crypto)
            self.assertEqual(w.verify_anchor_ack(ack,next_record,"c"*64),j.tip)
            replay=w.dispatch(payload,self.c,self.old,f.enroll,j,self.nonces,self.crypto)
            with self.assertRaises(w.owner.AuthorityHold):
                w.verify_anchor_ack(replay,next_record,"c"*64)
            with self.assertRaises(w.owner.AuthorityHold):
                w.verify_anchor_ack(ack|{"witness_identity":"a"*64},next_record,"c"*64)
    def test_native_coordinator_binding_exact_journal_and_no_retry(self):
        f=self.fixture
        client=Mock()
        packet=f.packet()
        with Journal(self.root,self.c["plan_sha256"]) as j, \
             patch.object(w.os,"geteuid",return_value=0), \
             patch.object(w,"NativeWitnessClient",return_value=client), \
             patch.object(w.legacy,"private_file",return_value=packet) as read:
            # Journal.read checks actual uid; fixture's test-only root shim
            # must not interfere with the already opened unprivileged journal.
            with patch.object(j,"read",return_value=j.records):
                b=w.CoordinatorWitnessBinding(f.plan,j)
                client.consume.side_effect=RuntimeError("uncertain")
                with self.assertRaises(RuntimeError):
                    b.authenticate_and_consume("capture",f.plan,None)
                with self.assertRaises(w.owner.AuthorityHold):
                    b.authenticate_and_consume("capture",f.plan,None)
                client.consume.assert_called_once_with(packet,"capture",None)
                self.assertEqual(read.call_args.args[0],
                    w.legacy.CONFIG.parent/"c06-expanded-packets"/b.sha/"capture.json")
                with self.assertRaises(w.owner.AuthorityHold):
                    b.anchor(b.sha,"ADMITTED","a"*64)
                self.assertFalse(client.anchor.called)

    def test_coordinator_binding_positive_crypto_and_independent_journal(self):
        # Test only: source and witness on distinct private fixture journals;
        # real Ed25519 signature, durable nonce reservation and exact ACK parser.
        f=self.fixture
        source=f.root/"source-journal";source.mkdir(mode=0o700)
        packet=f.packet()
        class LocalTransportFixture:
            def consume(self,raw,phase,previous):
                req=dict(action="consume",phase=phase,previous=previous,
                         packet_b64=base64.b64encode(raw).decode(),plan=f.plan)
                ack=w.dispatch(w.canonical(req),self_outer.c,self_outer.old,
                    f.enroll,remote,self_outer.nonces,self_outer.crypto)
                return a.verify_expanded_witness_ack(ack,f.enroll,raw,f.plan,
                    phase=phase,previous=previous,witness_identity="c"*64,
                    **self_outer.crypto)
            def anchor(self,record):
                ack=w.dispatch(w.canonical(dict(action="anchor",plan=f.plan,record=record)),
                    self_outer.c,self_outer.old,f.enroll,remote,self_outer.nonces,self_outer.crypto)
                return w.verify_anchor_ack(ack,record,"c"*64)
        self_outer=self
        with Journal(self.root,self.c["plan_sha256"]) as remote, \
             Journal(source,self.c["plan_sha256"]) as local:
            with patch.object(w.os,"geteuid",return_value=0), \
                 patch.object(w,"NativeWitnessClient",return_value=LocalTransportFixture()), \
                 patch.object(local,"read",return_value=local.records):
                b=w.CoordinatorWitnessBinding(f.plan,local)
            with patch.object(w.legacy,"private_file",return_value=packet):
                r=b.authenticate_and_consume("capture",f.plan,None)
            from settlement_c06_checkpoint_coordinator import validate_receipt
            tip=local.append("ADMITTED",validate_receipt(r,"capture",b.sha,None))
            self.assertEqual(b.anchor(b.sha,"ADMITTED",tip),tip)
            self.assertEqual(local.records,remote.records)
            tip=local.append("FENCE_INTENT","a"*64)
            self.assertEqual(b.anchor(b.sha,"FENCE_INTENT",tip),tip)
            self.assertEqual(local.records,remote.records)
            with self.assertRaises(w.owner.AuthorityHold):
                b.anchor(b.sha,"FENCE_INTENT",tip)
            self.assertEqual(len(list(self.nonces.glob("nonce-*.json"))),1)

    def test_effect_intent_witness_chain_and_replay(self):
        from settlement_c06_native_service_barrier import validate_scope
        from test_settlement_c06_native_service_barrier import scope
        from settlement_c06_checkpoint_coordinator import validate_receipt
        f=self.fixture;sc=scope()
        f.plan["scope"]=validate_scope(sc)
        f.q["plan_sha256"]=a.validate_plan(f.plan)
        self.c["plan_sha256"]=a.validate_plan(f.plan)
        packet=f.packet()
        psha=self.c["plan_sha256"]
        ep=f.root/"effects";ep.mkdir(mode=0o700)
        sp=f.root/"source-effects";sp.mkdir(mode=0o700)
        with Journal(self.root,psha) as j:
            ack=w.dispatch(w.canonical(dict(action="consume",phase="capture",
                previous=None,packet_b64=base64.b64encode(packet).decode(),plan=f.plan)),
                self.c,self.old,f.enroll,j,self.nonces,self.crypto)
            receipt=a.verify_expanded_witness_ack(ack,f.enroll,packet,f.plan,
                phase="capture",previous=None,witness_identity="c"*64,**self.crypto)
            admission=validate_receipt(receipt,"capture",psha,None)
            tip=j.append("FENCE_INTENT",f.plan["producer_prestate"])
            with w.BarrierEffectJournal(ep,f.plan,sc,"capture",tip,admission) as witness, \
                 w.BarrierEffectJournal(sp,f.plan,sc,"capture",tip,admission) as source:
                kw=dict(plan=f.plan,scope=sc,phase="capture",receipt=receipt,
                    packet=packet,enrollment=f.enroll,phase_journal=j,effect_journal=witness,
                    witness_identity="c"*64,**self.crypto)
                r=source.append("hold")
                with self.assertRaises(w.owner.AuthorityHold):
                    w.anchor_barrier_effect(dict(r,action="start:foreign.service"),**kw)
                got=w.anchor_barrier_effect(r,**kw)
                self.assertEqual(got["tip"],source.tip)
                self.assertFalse(got["production_authorized"])
                with self.assertRaises(w.owner.AuthorityHold):
                    w.anchor_barrier_effect(r,**kw)
                next_record=source.append("gate:"+sc["stop"][0])
                with self.assertRaises(w.owner.AuthorityHold):
                    w.anchor_barrier_effect(next_record,**(kw|{"receipt":dict(receipt,packet="a"*64)}))
                got=w.anchor_barrier_effect(next_record,**kw)
                self.assertEqual(got["tip"],source.tip)
                self.assertEqual(source.records,witness.records)
            with w.BarrierEffectJournal(ep,f.plan,sc,"capture",tip,admission) as reopened:
                self.assertEqual(len(reopened.records),2)
                with self.assertRaises(w.owner.AuthorityHold):reopened.append("hold")

    def test_effect_source_binding_no_progress_after_ambiguous_effect(self):
        from settlement_c06_native_service_barrier import NativeBarrier,validate_scope
        from test_settlement_c06_native_service_barrier import scope
        f=self.fixture;sc=scope();f.plan["scope"]=validate_scope(sc)
        tip="a"*64;admission="b"*64
        sp=f.root/"source-effects";sp.mkdir(mode=0o700)
        events=[]
        def anchor(r):
            events.append("anchor")
            return dict(schema="wolo.c06.barrier-effect-anchor.v1",plan=j.plan_sha,
                        phase="capture",tip=j.tip,witness_identity="c"*64,
                        status="NEW_EFFECT_INTENT_ANCHORED",production_authorized=False,
                        funding_authorized=False)
        with w.BarrierEffectJournal(sp,f.plan,sc,"capture",tip,admission) as j:
            b=w.BarrierEffectBinding(j,verify_phase=lambda:(tip,admission),
                verify_lease=lambda:(events.append("lease") or True),anchor_native=anchor,
                witness_identity="c"*64)
            barrier=NativeBarrier(sc,admit_effect=b.admit_effect,
                anchor_intent=b.anchor_intent,complete_effect=b.complete_effect)
            barrier.effect("capture","hold",lambda:events.append("effect"))
            self.assertEqual(events.count("anchor"),1)
            self.assertLess(events.index("anchor"),events.index("effect"))
            self.assertEqual(b.state,"READY")
            def fail():
                raise RuntimeError("ambiguous")
            with self.assertRaises(RuntimeError):
                barrier.effect("capture","gate:"+sc["stop"][0],fail)
            self.assertEqual(b.state,"EFFECT_IN_FLIGHT")
            with self.assertRaises(w.owner.AuthorityHold):
                barrier.effect("capture","gate:"+sc["stop"][1],lambda:events.append("bad"))
            self.assertNotIn("bad",events)
            with self.assertRaises(w.owner.AuthorityHold):b.verify_complete()
        with w.BarrierEffectJournal(sp,f.plan,sc,"capture",tip,admission) as j:
            with self.assertRaises(w.owner.AuthorityHold):
                w.BarrierEffectBinding(j,verify_phase=lambda:(tip,admission),
                    verify_lease=lambda:None,anchor_native=anchor,witness_identity="c"*64)

    def test_effect_wire_independent_lease_and_exact_ack(self):
        from settlement_c06_native_service_barrier import validate_scope
        from test_settlement_c06_native_service_barrier import scope
        from settlement_c06_checkpoint_coordinator import validate_receipt
        f=self.fixture;sc=scope();f.plan["scope"]=validate_scope(sc)
        f.q["plan_sha256"]=a.validate_plan(f.plan)
        self.c["plan_sha256"]=a.validate_plan(f.plan)
        packet=f.packet();psha=self.c["plan_sha256"]
        ep=f.root/"effects";ep.mkdir(mode=0o700)
        with Journal(self.root,psha) as j:
            ack=w.dispatch(w.canonical(dict(action="consume",phase="capture",
                previous=None,packet_b64=base64.b64encode(packet).decode(),plan=f.plan)),
                self.c,self.old,f.enroll,j,self.nonces,self.crypto)
            r=a.verify_expanded_witness_ack(ack,f.enroll,packet,f.plan,
                phase="capture",previous=None,witness_identity="c"*64,**self.crypto)
            admission=validate_receipt(r,"capture",psha,None)
            tip=j.append("FENCE_INTENT",f.plan["producer_prestate"])
            with w.BarrierEffectJournal(ep,f.plan,sc,"capture",tip,admission) as effects:
                record=effects.expected(0,None)
                payload=dict(action="anchor_effect",plan=f.plan,scope=sc,
                    phase="capture",receipt=r,packet_b64=base64.b64encode(packet).decode(),
                    record=record)
                args=(w.canonical(payload),self.c,self.old,f.enroll,j,self.nonces,self.crypto)
                with self.assertRaises(w.owner.AuthorityHold):w.dispatch(*args)
                with self.assertRaises(w.owner.AuthorityHold):
                    w.dispatch(*args,effect_journal=effects,verify_lease=lambda p:None)
                self.assertFalse(effects.records)
                client=object.__new__(w.NativeWitnessClient)
                client.plan=f.plan;client.c=self.c;client.old=self.old
                client.enrollment=f.enroll;client.check=lambda:self.crypto
                def exchange(old,p):
                    self.assertEqual(p,payload)
                    return w.dispatch(w.canonical(p),self.c,self.old,f.enroll,j,
                        self.nonces,self.crypto,effect_journal=effects,
                        verify_lease=lambda plan: plan==f.plan)
                with patch.object(w,"native_exchange",side_effect=exchange) as native:
                    out=client.anchor_effect(record,scope=sc,phase="capture",receipt=r,
                        packet=packet,journal=j,verify_lease=lambda p: p==f.plan)
                    self.assertEqual(out["tip"],effects.tip)
                    self.assertFalse(out["production_authorized"])
                    native.assert_called_once()
                    with self.assertRaises(w.owner.AuthorityHold):
                        client.anchor_effect(record,scope=sc,phase="capture",receipt=r,
                            packet=packet,journal=j,verify_lease=lambda p:None)
                    self.assertEqual(native.call_count,1)
                self.assertEqual(len(effects.records),1)
                with self.assertRaises(w.owner.AuthorityHold):
                    w.dispatch(*args,effect_journal=effects,verify_lease=lambda p:True)
                # A lost lease after durable append spends this intent and
                # returns no ACK. A retry cannot turn it into fresh authority.
                new=effects.expected(1,effects.tip)
                args=(w.canonical(dict(payload,record=new)),*args[1:])
                checks=iter((True,False))
                with self.assertRaises(w.owner.AuthorityHold):
                    w.dispatch(*args,effect_journal=effects,verify_lease=lambda p:next(checks))
                self.assertEqual(len(effects.records),2)
                with self.assertRaises(w.owner.AuthorityHold):
                    w.dispatch(*args,effect_journal=effects,verify_lease=lambda p:True)

    def test_unenrolled_scope_and_arbitrary_action_rejected(self):
        f=self.fixture
        req={"action":"consume","phase":"capture","previous":None,
             "packet_b64":base64.b64encode(f.packet()).decode(),
             "plan":f.plan|{"scope":"f"*64}}
        with Journal(self.root,self.c["plan_sha256"]) as j:
            with self.assertRaises(w.owner.AuthorityHold):
                w.dispatch(w.canonical(req),self.c,self.old,f.enroll,j,self.nonces,self.crypto)
            self.assertFalse(j.records)
            self.assertFalse(list(self.nonces.iterdir()))
        for data in (b'{"action":"shell"}',w.canonical(req|{"command":"start"}),
                     w.canonical(req|{"phase":"contain"})):
            with self.assertRaises(w.owner.AuthorityHold): w.request(data)


if __name__=="__main__": unittest.main()

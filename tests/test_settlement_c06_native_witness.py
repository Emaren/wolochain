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

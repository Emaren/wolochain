import base64
import hashlib
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
import settlement_c06_checkpoint_authority as a
import settlement_solo_owner_intent_review as owner
from test_settlement_c06_checkpoint_coordinator import plan
from settlement_c06_checkpoint_coordinator import Journal

def sha(b):return hashlib.sha256(b).hexdigest()
def utc(t):return t.strftime("%Y-%m-%dT%H:%M:%SZ")

class SignatureTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        self.ssl=os.environ.get("C06_OPENSSL") or shutil.which("openssl")
        self.assertIsNotNone(self.ssl)
        self.key=self.root/"fixture-key.pem"
        self.run_ssl("genpkey","-algorithm","ED25519","-out",str(self.key))
        pub=self.run_ssl("pkey","-in",str(self.key),"-pubout")
        der=self.run_ssl("pkey","-pubin","-outform","DER",input=pub)
        self.pin=sha(der)
        self.now=datetime.now(timezone.utc).replace(microsecond=0)
        self.enroll=owner.canonical({"schema":owner.ENROLL_SCHEMA,"owner_key_id":"fixture-owner",
            "public_key_pem":pub.decode(),"valid_from":utc(self.now-timedelta(hours=1)),
            "valid_until":utc(self.now+timedelta(hours=1)),"revoked":False})
        self.plan=plan()
        self.q={"schema":a.SCHEMA,"chain_id":"wolo-1","phase":"capture",
            "operation":a.OPS["capture"],"source_commit":"1"*40,
            "plan_sha256":a.validate_plan(self.plan),"previous_journal_sha256":None,
            "nonce":"2"*32,"not_before":utc(self.now-timedelta(seconds=10)),
            "expires_at":utc(self.now+timedelta(minutes=10))}
    def tearDown(self):self.tmp.cleanup()
    def run_ssl(self,*args,input=None):
        return subprocess.run([self.ssl,*args],input=input,capture_output=True,
                              check=True,timeout=8).stdout
    def packet(self,q=None,domain=a.DOMAIN,schema=a.PACKET):
        q=self.q if q is None else q
        msg=self.root/"message"
        msg.write_bytes(domain+owner.canonical({"owner_key_id":"fixture-owner","request":q}))
        sig=self.run_ssl("pkeyutl","-sign","-rawin","-inkey",str(self.key),"-in",str(msg))
        return owner.canonical({"schema":schema,"owner_key_id":"fixture-owner",
                                "request":q,"signature_b64":base64.b64encode(sig).decode()})
    def review(self,p,**kw):
        args=dict(phase="capture",previous=None,source_commit="1"*40,
                  enrollment_pin=sha(self.enroll),owner_pin=self.pin,
                  openssl_path=self.ssl,now=self.now)
        return a.review(self.enroll,p,self.plan,**(args|kw))
    def test_actual_signature_only(self):
        r=self.review(self.packet())
        self.assertEqual(r["status"],"CRYPTO_VALID_NONAUTHORIZING")
        self.assertFalse(r["production_authorized"])
        self.assertFalse(r["independent_witness_consumed"])
    def test_old_domain_rejected(self):
        with self.assertRaises(owner.AuthorityHold):self.review(self.packet(domain=owner.DOMAIN))
        with self.assertRaises(owner.AuthorityHold):self.review(self.packet(schema=owner.PACKET_SCHEMA))
    def test_scope_and_time(self):
        for k,v in [("plan_sha256","a"*64),("operation","funded_activate"),
                    ("nonce","0"*32),("expires_at",utc(self.now))]:
            with self.subTest(k=k),self.assertRaises(owner.AuthorityHold):
                self.review(self.packet(self.q|{k:v}))
    def test_resume_requires_exact_prior(self):
        q=self.q|{"phase":"resume","operation":a.OPS["resume"],
                  "previous_journal_sha256":"a"*64}
        with self.assertRaises(owner.AuthorityHold):
            self.review(self.packet(q),phase="resume",previous="b"*64)
        self.assertFalse(self.review(self.packet(q),phase="resume",previous="a"*64)["production_authorized"])
    def test_wrong_anchor(self):
        with self.assertRaises(owner.AuthorityHold):
            self.review(self.packet(),owner_pin="a"*64)

    def witness_args(self):
        return dict(phase="capture",previous=None,source_commit="1"*40,
                    enrollment_pin=sha(self.enroll),owner_pin=self.pin,
                    openssl_path=self.ssl,now=self.now)

    def consume(self, packet, **overrides):
        root=self.root/"nonces"
        root.mkdir(mode=0o700,exist_ok=True)
        args=self.witness_args()|dict(local_identity="c"*64,
            witness_identity="c"*64,source_identity=self.plan["host"],
            expected_plan_sha=a.validate_plan(self.plan),nonce_root=root)
        witness=self.root/"journal";witness.mkdir(mode=0o700,exist_ok=True)
        with Journal(witness,a.validate_plan(self.plan)) as journal:
            return a.consume_expanded_witness(self.enroll,packet,self.plan,
                                               journal=journal,**(args|overrides))

    def test_real_signature_durable_witness_and_ack(self):
        packet=self.packet()
        ack=self.consume(packet)
        self.assertTrue(ack["fresh_consumption_confirmed"])
        self.assertFalse(ack["production_authorized"])
        got=a.verify_expanded_witness_ack(ack,self.enroll,packet,self.plan,
                witness_identity="c"*64,**self.witness_args())
        self.assertEqual(got["packet"],sha(packet))
        self.assertEqual(got["witness"],sha(a.canonical(ack)))
        self.assertEqual(len(list((self.root/"nonces").glob("nonce-*.json"))),1)
        with self.assertRaises(owner.AuthorityHold):self.consume(packet)
        for k,v in (("packet","d"*64),("witness_identity","d"*64),
                    ("record_sha256","d"*64),("fresh_consumption_confirmed",1),
                    ("production_authorized",True)):
            with self.subTest(k=k),self.assertRaises(owner.AuthorityHold):
                a.verify_expanded_witness_ack(ack|{k:v},self.enroll,packet,self.plan,
                    witness_identity="c"*64,**self.witness_args())

    def test_same_host_and_unenrolled_plan_refused(self):
        p=self.packet()
        for kwargs in ({"local_identity":self.plan["host"]},
                       {"witness_identity":self.plan["host"]},
                       {"source_identity":"d"*64},
                       {"expected_plan_sha":"d"*64}):
            with self.subTest(kwargs=kwargs),self.assertRaises(owner.AuthorityHold):
                self.consume(p,**kwargs)
        self.assertFalse(list((self.root/"nonces").glob("nonce-*.json")))

    def test_legacy_nonce_collision_refused(self):
        root=self.root/"nonces";root.mkdir(mode=0o700)
        a.nonces.reserve_once(root,self.q["nonce"],"e"*64,"live_capture")
        with self.assertRaises(a.nonces.ReservationRefused):self.consume(self.packet())

    def test_wrong_signature_never_spends_nonce(self):
        with self.assertRaises(owner.AuthorityHold):
            self.consume(self.packet(domain=owner.DOMAIN))
        self.assertFalse(list((self.root/"nonces").glob("nonce-*.json")))

    def anchor_args(self):
        return dict(plan=self.plan,local_identity="c"*64,witness_identity="c"*64,
                    source_identity=self.plan["host"],expected_plan_sha=a.validate_plan(self.plan))

    def test_witness_preanchors_phase_and_exact_source_mirror(self):
        packet=self.packet()
        ack=self.consume(packet)
        with Journal(self.root/"journal",a.validate_plan(self.plan)) as j:
            self.assertEqual(j.records[-1]["step"],"ADMITTED")
            receipt=a.verify_expanded_witness_ack(ack,self.enroll,packet,self.plan,
                    witness_identity="c"*64,**self.witness_args())
            self.assertEqual(j.records[-1]["evidence"],sha(a.canonical(receipt)))
            admitted=j.records[-1]
            result=a.anchor_witness_record(j,admitted,**self.anchor_args())
            self.assertEqual(result["status"],"EXISTING_TIP_READBACK")
            fence={"schema":admitted["schema"],"index":1,"step":"FENCE_INTENT",
                   "plan":admitted["plan"],"previous":j.tip,"evidence":"d"*64}
            for change in ({"previous":"e"*64},{"step":"RESUME_ADMITTED"},
                           {"index":2},{"plan":"f"*64}):
                with self.subTest(change=change),self.assertRaises(owner.AuthorityHold):
                    a.anchor_witness_record(j,fence|change,**self.anchor_args())
            self.assertEqual(a.anchor_witness_record(j,fence,**self.anchor_args())["status"],
                             "NEW_TIP_ANCHORED")
            self.assertEqual(j.records[-1],fence)
            self.assertEqual(a.anchor_witness_record(j,fence,**self.anchor_args())["status"],
                             "EXISTING_TIP_READBACK")
            with self.assertRaises(owner.AuthorityHold):
                a.anchor_witness_record(j,admitted,**self.anchor_args())
        with Journal(self.root/"journal",a.validate_plan(self.plan)) as j:
            self.assertEqual(j.records[-1],fence)
        # A different genuine nonce cannot reopen capture for this plan.
        with self.assertRaises(owner.AuthorityHold):
            self.consume(self.packet(self.q|{"nonce":"3"*32}))

    def test_no_admission_by_raw_journal_record(self):
        path=self.root/"empty";path.mkdir(mode=0o700)
        with Journal(path,a.validate_plan(self.plan)) as j:
            raw={"schema":"wolo.c06.checkpoint-journal.v1","index":0,"step":"ADMITTED",
                 "plan":j.plan_sha,"previous":None,"evidence":"e"*64}
            with self.assertRaises(owner.AuthorityHold):
                a.anchor_witness_record(j,raw,**self.anchor_args())
            self.assertFalse(j.records)

if __name__=="__main__":unittest.main()

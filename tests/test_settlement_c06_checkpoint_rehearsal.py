import copy
import io
import os
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import settlement_c06_checkpoint_rehearsal as c

H = "a" * 64
DB = ["aoe2hd_db", "aoe2de_db", "other-shared"]
def observation():
    return {"domains": {x: "FENCED_AND_RECONNECT_DENIED" for x in c.DOMAINS},
            "quarantine": sorted(c.QUARANTINE), "shared_databases": DB[:],
            "pg": {"major":16,"system_id":"123","state":"shut down","prepared":0,
                   "client_processes":0,"restart_inhibited":True,
                   "external_tablespaces":[],"wal_present":True},
            "chain": {"chain_id":"wolo-1","block_height":10,"state_height":10,
                      "app_height":10,"state_app_hash":H,"app_commit_hash":H,
                      "closed":True,"restart_inhibited":True,"anchor_sha256":H},
            "lease":H,"checkpoint":H}

class ObservationTests(unittest.TestCase):
    def test_valid_structure_only(self):
        self.assertTrue(c.hash64(c.validate_observation(observation(),expected_databases=DB)))

    def test_missing_domains(self):
        for d in c.DOMAINS:
            with self.subTest(d=d):
                o=observation(); del o["domains"][d]
                with self.assertRaises(c.Hold): c.validate_observation(o,expected_databases=DB)

    def test_bad_pg(self):
        for k,v in {"major":15,"state":"in production","prepared":1,
                    "client_processes":1,"restart_inhibited":False,
                    "external_tablespaces":["extra"],"wal_present":False}.items():
            with self.subTest(k=k):
                o=observation();o["pg"][k]=v
                with self.assertRaises(c.Hold): c.validate_observation(o,expected_databases=DB)

    def test_bad_chain(self):
        for k,v in {"block_height":9,"state_height":11,"app_height":0,
                    "app_commit_hash":"b"*64,"closed":False,
                    "restart_inhibited":False,"anchor_sha256":"bad"}.items():
            with self.subTest(k=k):
                o=observation();o["chain"][k]=v
                with self.assertRaises(c.Hold): c.validate_observation(o,expected_databases=DB)

    def test_shared_cluster_scope(self):
        o=observation();o["shared_databases"].pop()
        with self.assertRaises(c.Hold): c.validate_observation(o,expected_databases=DB)

    def test_quarantine(self):
        o=observation();o["quarantine"].pop()
        with self.assertRaises(c.Hold): c.validate_observation(o,expected_databases=DB)

    def test_budget(self):
        kw=dict(cipher_max=3*c.GIB,data_free=5*c.GIB,data_reserve=c.GIB,
                receiver_free=8*c.GIB,receiver_reserve=c.GIB,restore_bytes=3*c.GIB)
        self.assertGreater(c.archive_budget(2*c.GIB,**kw),2*c.GIB)
        for k,v in [("cipher_max",c.GIB),("data_free",3*c.GIB),
                    ("receiver_free",6*c.GIB),("restore_bytes",True)]:
            with self.subTest(k=k):
                with self.assertRaises(c.Hold): c.archive_budget(2*c.GIB,**(kw|{k:v}))

@unittest.skipIf(os.geteuid()==0,"unprivileged fixture only")
class ArchiveTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name).resolve()/"fixture"
        self.root.mkdir(mode=0o700)
        (self.root/".c06-disposable-fixture").touch(mode=0o600)
        for x in c.ROOTS:
            p=self.root/x;p.mkdir(mode=0o700)
            (p/"test").write_bytes(x.encode())

    def tearDown(self): self.tmp.cleanup()

    def test_roundtrip(self):
        m=c.manifest(self.root,H);s=io.BytesIO()
        c.write_tar(self.root,m,s)
        self.assertEqual(len(s.getvalue()),c.tar_size(m))
        self.assertEqual(c.verify_tar(io.BytesIO(s.getvalue()),m,self.root.parent/"restored"),
                         c.digest(c.canonical(m)))

    def test_mutation(self):
        m=c.manifest(self.root,H)
        (self.root/"pgdata/test").write_bytes(b"changed")
        with self.assertRaises(c.Hold):c.write_tar(self.root,m,io.BytesIO())

    def test_link(self):
        (self.root/"chain-data/link").symlink_to(self.root/"pgdata/test")
        with self.assertRaises(c.Hold):c.inventory(self.root)

    def test_signer_key(self):
        (self.root/"chain-data/priv_validator_key.json").touch()
        with self.assertRaises(c.Hold):c.inventory(self.root)

    def test_tampered_member(self):
        m=c.manifest(self.root,H);s=io.BytesIO();c.write_tar(self.root,m,s)
        raw=s.getvalue().replace(b"pgdata"+b"\0"*100,b"pgdatX"+b"\0"*100)
        if raw==s.getvalue(): raw=s.getvalue().replace(b"primary-journal"+b"\0"*100,b"primary-journaX"+b"\0"*100)
        self.assertNotEqual(raw,s.getvalue())
        with self.assertRaises(c.Hold):c.verify_tar(io.BytesIO(raw),m,self.root.parent/"bad")

    def test_extra_component(self):
        (self.root/"extra").mkdir()
        with self.assertRaises(c.Hold):c.inventory(self.root)

class Adapter:
    is_disposable_fixture=True
    databases=DB
    def __init__(self,fail=None):self.fail=fail;self.calls=[];self.o=observation()
    def step(self,x):
        self.calls.append(x)
        if x==self.fail:raise RuntimeError(x)
    def admit_fixture(self):self.step("admit")
    def fence(self):self.step("fence")
    def observe(self):self.step("observe");return copy.deepcopy(self.o)
    def capture(self,h):self.step("capture");return H
    def verify_receiver(self,h):self.step("receiver")
    def restore(self,h):self.step("restore");return H
    def restart_nonfinancial_only(self):self.step("restart")
    def verify_quarantine(self):self.step("quarantine")

class PhaseTests(unittest.TestCase):
    def test_order(self):
        a=Adapter();j=[]
        self.assertEqual(c.run_phases(a,j.append),H)
        self.assertEqual(j,["PREPARE","FENCE_INTENT","FROZEN","CAPTURE_INTENT",
                            "CAPTURE_VERIFIED","RECOVERY_VERIFIED","RESTART_INTENT",
                            "REHEARSAL_COMPLETE"])

    def test_failure_never_restarts(self):
        for name in ("admit","fence","observe","capture","receiver","restore"):
            a=Adapter(name);j=[]
            with self.subTest(name=name),self.assertRaises(RuntimeError):
                c.run_phases(a,j.append)
            self.assertNotIn("restart",a.calls)
            self.assertEqual(j[-1],"HOLD_NO_AUTOMATIC_RETRY_OR_RESTART")

    def test_wrong_cipher(self):
        a=Adapter();a.restore=lambda h:"b"*64
        with self.assertRaises(c.Hold):c.run_phases(a,lambda x:None)
        self.assertNotIn("restart",a.calls)

    def test_live_adapter_refused(self):
        a=Adapter();a.is_disposable_fixture=False
        with self.assertRaises(c.Hold):c.run_phases(a,lambda x:None)
        self.assertEqual(a.calls,[])

if __name__=="__main__":unittest.main()

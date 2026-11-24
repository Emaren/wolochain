import copy
import io
import os
from pathlib import Path
import sys
import tempfile
import tarfile
import shutil
import subprocess
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
        with tarfile.open(fileobj=io.BytesIO(s.getvalue()),mode="r:") as t:
            offset=t.getmember("pgdata/test").offset_data
        raw=bytearray(s.getvalue());raw[offset]^=1
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

@unittest.skipUnless(os.geteuid()!=0 and os.environ.get("C06_PG_BIN")
                     and os.environ.get("C06_AGE") and os.environ.get("C06_AGE_KEYGEN"),
                     "explicit disposable PG16 and age tool paths required")
class PhysicalFixtureTests(unittest.TestCase):
    def test_pg16_age_restore(self):
        # Entirely synthetic rows and generated test-only encryption identity.
        pg=Path(os.environ["C06_PG_BIN"])
        age=os.environ["C06_AGE"]
        keygen=os.environ["C06_AGE_KEYGEN"]
        def run(argv,**kw):
            return subprocess.run([str(x) for x in argv],check=True,
                                  capture_output=True,timeout=90,**kw).stdout
        def psql(sock,db,sql):
            return run([pg/"psql","-X","-w","-At","-v","ON_ERROR_STOP=1",
                        "-h",sock,"-p","56498","-U","fixture_admin","-d",db,"-c",sql])
        def start(data,sock):
            run([pg/"pg_ctl","-D",data,"-l",sock/"server.log","-w","-o",
                 "-h '' -k "+str(sock)+" -p 56498","start"])
        def stop(data):
            run([pg/"pg_ctl","-D",data,"-w","-m","fast","stop"])
        with tempfile.TemporaryDirectory(prefix="c06fixture-") as tmp:
            root=Path(tmp).resolve()
            fixture=root/"fixture";fixture.mkdir(mode=0o700)
            (fixture/".c06-disposable-fixture").touch(mode=0o600)
            for n in c.ROOTS:(fixture/n).mkdir(mode=0o700)
            for n in c.ROOTS-{"pgdata"}:(fixture/n/"synthetic").write_text(n)
            data=fixture/"pgdata";sock=root/"s";sock.mkdir(mode=0o700)
            run([pg/"initdb","-D",data,"-U","fixture_admin",
                 "--auth-local=trust","--auth-host=reject","--no-locale"])
            active=False
            try:
                start(data,sock);active=True
                psql(sock,"postgres","CREATE ROLE fixture_reader NOLOGIN")
                for db in DB:
                    # The additional shared database name needs SQL quoting.
                    psql(sock,"postgres",'CREATE DATABASE "'+db+'"')
                    psql(sock,db,"CREATE TABLE t(id integer primary key); INSERT INTO t VALUES (42); GRANT SELECT ON t TO fixture_reader")
                before=psql(sock,"postgres","SELECT datname FROM pg_database ORDER BY datname")
                stop(data);active=False
                ctl=run([pg/"pg_controldata",data]).decode()
                self.assertRegex(ctl,r"Database cluster state:\s+shut down")
                self.assertTrue(any((data/"pg_wal").iterdir()))
                m=c.manifest(fixture,H)
                # Bounded plaintext tar exists ONLY in this temporary synthetic
                # test; production will require a separately reviewed stream.
                tar=root/"fixture.tar"
                with tar.open("wb") as out:c.write_tar(fixture,m,out)
                self.assertEqual(tar.stat().st_size,c.tar_size(m))
                identity=root/"test.agekey";run([keygen,"-o",identity])
                recipient=run([keygen,"-y",identity]).decode().strip()
                cipher=root/"fixture.age"
                run([age,"-r",recipient,"-o",cipher,tar])
                cipher_sha=c.sha_file(cipher)
                self.assertLessEqual(cipher.stat().st_size,
                    c.archive_budget(tar.stat().st_size,cipher_max=c.GIB,
                        data_free=3*c.GIB,data_reserve=c.GIB,
                        receiver_free=5*c.GIB,receiver_reserve=c.GIB,restore_bytes=c.GIB))
                # Verify the same ciphertext; no new capture is allowed.
                recovered=root/"recovered.tar"
                run([age,"-d","-i",identity,"-o",recovered,cipher])
                self.assertEqual(c.sha_file(cipher),cipher_sha)
                restored=root/"restored"
                with recovered.open("rb") as stream:c.verify_tar(stream,m,restored)
                restored_data=restored/"pgdata"
                self.assertEqual(run([pg/"pg_controldata",restored_data]),ctl.encode())
                start(restored_data,sock);active=True;data=restored_data
                self.assertEqual(psql(sock,"postgres","SELECT datname FROM pg_database ORDER BY datname"),before)
                for db in DB:
                    self.assertEqual(psql(sock,db,"SELECT id FROM t"),b"42\n")
                    self.assertEqual(psql(sock,db,"SELECT has_table_privilege('fixture_reader','t','SELECT')"),b"t\n")
                self.assertEqual(psql(sock,"postgres","SHOW listen_addresses"),b"\n")
                stop(data);active=False
                # Authentic age corruption detection; no restore from a partial stream.
                damaged=root/"bad.age";raw=bytearray(cipher.read_bytes());raw[-1]^=1
                damaged.write_bytes(raw)
                bad=subprocess.run([age,"-d","-i",str(identity),"-o",str(root/"bad.tar"),str(damaged)],
                                   capture_output=True,timeout=90)
                self.assertNotEqual(bad.returncode,0)
            finally:
                if active:stop(data)

@unittest.skipUnless(os.geteuid()!=0 and os.environ.get("C06_AGE")
                     and os.environ.get("C06_AGE_KEYGEN"),
                     "disposable age tools required")
class BoundedStreamTests(unittest.TestCase):
    def test_real_direct_dual_recipient_ciphertext_and_failure_evidence(self):
        age=Path(os.environ["C06_AGE"]).resolve()
        keygen=Path(os.environ["C06_AGE_KEYGEN"]).resolve()
        def run(argv):
            return subprocess.run([str(x) for x in argv],capture_output=True,
                                  check=True,timeout=15).stdout
        with tempfile.TemporaryDirectory(prefix="c06-stream-") as td:
            root=Path(td).resolve()
            dest=root/"cipher";dest.mkdir(mode=0o700)
            keys=[];recipients=[]
            for i in range(2):
                k=root/("fixture-key-"+str(i))
                run([keygen,"-o",k]);keys.append(k)
                recipients.append(run([keygen,"-y",k]).decode().strip())
            payload=(b"synthetic checkpoint only\n"*4096)
            args=dict(plain_bytes=len(payload),cipher_max=4<<20,
                      reserve_bytes=1<<20,age_path=age,
                      age_sha256=c.sha_file(age),recipients=tuple(recipients),
                      recipient_pin=c.digest(c.canonical(recipients)),
                      timeout_seconds=20)
            target=dest/"complete.age"
            from settlement_c06_image_stream import identity,stream_exact,verify_reconstruction
            source=root/"synthetic-image"
            source.write_bytes(payload);source.chmod(0o600)
            observation={}
            def writer(out):
                with source.open("rb") as f:
                    observation.update(stream_exact(f.fileno(),identity(f.fileno()),out,
                                       expected_sha=c.digest(payload)))
            receipt=c.stream_age_ciphertext(writer,target,**args)
            self.assertEqual(receipt["ciphertext_sha256"],c.sha_file(target))
            self.assertEqual(receipt["plaintext_sha256"],c.digest(payload))
            self.assertFalse(receipt["c06_closed"])
            phases=receipt["phase_telemetry"]
            for name in ("producer_wall_ns","pipeline_wall_ns","destination_write_ns",
                         "destination_fsync_ns","destination_verification_ns","wall_ns"):
                self.assertGreater(phases[name],0)
            self.assertIsNone(phases["source_read_ns"])
            self.assertIsNone(phases["encryption_cpu_ns"])
            self.assertIsNone(phases["transport_ns"])
            self.assertIsNone(phases["restore_ns"])
            self.assertEqual(phases["ciphertext_bytes"],receipt["ciphertext_bytes"])
            self.assertEqual(list(dest.iterdir()),[target])
            for k in keys:self.assertEqual(run([age,"-d","-i",k,target]),payload)
            import time,json
            reconstruction=root/"reconstructed"
            start=time.monotonic_ns()
            with reconstruction.open("xb") as out:
                reconstruction.chmod(0o600)
                subprocess.run([str(age),"-d","-i",str(keys[1]),str(target)],
                    stdout=out,stderr=subprocess.PIPE,check=True,timeout=15)
                out.flush();os.fsync(out.fileno())
            elapsed=time.monotonic_ns()-start
            with reconstruction.open("rb") as f:
                verified=verify_reconstruction(f.fileno(),c.digest(payload),len(payload))
            print("SYNTHETIC_ONLY_PHASE_TELEMETRY "+json.dumps({
                **phases,"source_read_ns":observation["source_read_ns"],
                "source_sink_write_ns":observation["sink_write_ns"],
                "restore_ns":elapsed,"restore_verification_ns":verified["verification_ns"],
                "scope":"single_host_synthetic_exact_image","independent":False},
                sort_keys=True),flush=True)
            with self.assertRaises(c.Hold):c.stream_age_ciphertext(writer,target,**args)
            with self.assertRaises(c.Hold):
                c.stream_age_ciphertext(writer,dest/"wrong-pin.age",**(args|{"recipient_pin":"f"*64}))
            self.assertFalse((dest/"wrong-pin.age.incomplete").exists())
            short=dest/"short.age"
            with self.assertRaises(c.Hold):
                c.stream_age_ciphertext(lambda w:w.write(b"short"),short,**args)
            self.assertFalse(short.exists())
            self.assertTrue((dest/"short.age.incomplete").is_file())
            long=dest/"long.age"
            with self.assertRaises(c.Hold):
                c.stream_age_ciphertext(lambda w:w.write(payload+b"x"),long,**args)
            self.assertFalse(long.exists())
            self.assertTrue((dest/"long.age.incomplete").is_file())
            self.assertFalse(list(dest.glob("*.tar")))
            print("PASS_DIRECT_DUAL_RECIPIENT_CIPHERTEXT_WITHOUT_PLAINTEXT_STAGE",flush=True)

if __name__=="__main__":unittest.main()


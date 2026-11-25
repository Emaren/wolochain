"""C06 preparatory unquiesced export: isolated nonfinancial contract tests."""
from __future__ import annotations
import base64,hashlib,importlib.util,json
from pathlib import Path
import struct,stat,tempfile,unittest
from unittest.mock import patch

SRC=Path(__file__).resolve().parents[1]/"scripts"/"settlement_c06_unquiesced_offhost_mvcc_precapture.py"
sp=importlib.util.spec_from_file_location("c06_pre",SRC)
m=importlib.util.module_from_spec(sp);sp.loader.exec_module(m)

class C06PreCaptureTests(unittest.TestCase):
    def test_fixed_databases_and_low_priority_pg16_dump(self):
        self.assertEqual(set(m.DUMP),{"aoe2hd_db","aoe2de_db"})
        self.assertEqual(m.DBS,("aoe2de_db","aoe2hd_db"))
        for db,cmd in m.DUMP.items():
            self.assertIn("/usr/lib/postgresql/16/bin/pg_dump",cmd)
            self.assertIn("-F c -Z 3",cmd)
            self.assertIn("--lock-wait-timeout=5000",cmd)
            self.assertIn("/usr/bin/ionice -c3",cmd)
            self.assertIn("/usr/bin/nice -n 15",cmd)
            self.assertIn(" -d "+db,cmd)
            for forbidden in ("pg_restore","DROP TABLE","psql -c","ALTER ROLE",
                              "pg_dumpall --globals-only"):
                self.assertNotIn(forbidden,cmd)
    def test_owner_signature_and_private_key_never_present(self):
        s=SRC.read_text()
        for forbidden in ("--identity","age -d","keychain","broadcast_tx",
                          "send-tx","systemctl stop","systemctl start",
                          "psql -c", "wal-g backup-push"):
            self.assertNotIn(forbidden,s)
        self.assertIn('"global_writer_fence_proven":False',s)
        self.assertIn('"c06_formal_backup_gate_closed":False',s)
        self.assertIn('"c07_formal_recovery_gate_closed":False',s)
        self.assertIn('"custody_financial_release_authorized":False',s)
        self.assertIn('"cross_database_atomic_snapshot":False',s)
    def test_exact_ed25519_fingerprint(self):
        blob=(struct.pack(">I",11)+b"ssh-ed25519"+
              struct.pack(">I",32)+bytes(range(32)))
        public=b"ssh-ed25519 "+base64.b64encode(blob)+b" owner\n"
        expected="SHA256:"+base64.b64encode(hashlib.sha256(blob).digest()).decode().rstrip("=")
        self.assertEqual(m.fingerprint(public),expected)
    def test_reject_invalid_recipient_keys(self):
        for b in (b"",b"ssh-rsa AAAA",b"ssh-ed25519 ????",b"ssh-ed25519 AAAA"):
            with self.subTest(key=b),self.assertRaises(m.Hold):
                m.fingerprint(b)
    def test_sha_line_verification(self):
        m.verify_sha_line(("f"*64+" 2048\n").encode(),"f"*64,2048)
    def test_sha_line_reject_hash_or_length_mismatch(self):
        for data in ("f"*64+" 2048","e"*64+" 2049"):
            with self.subTest(data=data),self.assertRaises(m.Hold):
                m.verify_sha_line(data.encode(),"e"*64,2048)
    def test_reject_duplicate_receiver_rows_or_control_characters(self):
        for text in ("", "f"*64+" 1\nf"*64+" 1", "f"*64+" 0",
                     "f"*64+" -3","notsha 1","f"*64+" 1\x00"):
            with self.subTest(text=text),self.assertRaises(m.Hold):
                m.verify_sha_line(text.encode(),"f"*64,1)
    def test_remote_atomic_exclusive_and_age_header(self):
        self.assertIn("O_EXCL",m.REMOTE_WRITE)
        self.assertIn("O_NOFOLLOW",m.REMOTE_WRITE)
        self.assertIn("stat.S_IMODE(s.st_mode)!=0o700",m.REMOTE_WRITE)
        self.assertIn('b"age-encryption.org/v1\\n"',m.REMOTE_WRITE)
        self.assertIn("REMOTE_CIPHER_DIGEST_DRIFT",m.REMOTE_WRITE)
        self.assertIn("tmp.rename(final)",m.REMOTE_WRITE)
        self.assertIn("if not accepted:",m.REMOTE_WRITE)
    def test_intel_readback_python38_hash_compatible(self):
        self.assertNotIn("hashlib.file_digest",m.REMOTE_READ)
        self.assertIn("h.update(b)",m.REMOTE_READ)
        self.assertIn("stat.S_IMODE(s.st_mode)!=0o600",m.REMOTE_READ)
    def test_actual_synthetic_offhost_encrypted_write_readback_and_replay(self):
        import os,subprocess,sys
        sample=b"age-encryption.org/v1\n-> X25519 SYNTHETIC TEST\n"+b"X"*512
        expected=hashlib.sha256(sample).hexdigest()
        with tempfile.TemporaryDirectory(prefix="c06-intel-synthetic-") as t:
            env={**os.environ,"HOME":t}
            code=[sys.executable,"-B","-c",m.REMOTE_WRITE,
                  "aoe2de_db",expected,str(len(sample))]
            first=subprocess.run(code,input=sample,capture_output=True,env=env,timeout=8)
            self.assertEqual(first.returncode,0,first.stderr[-140:])
            m.verify_sha_line(first.stdout,expected,len(sample))
            p=Path(t)/".wolo-owner-authority"/"c06-unquiesced-mvcc-precapture-20261108"/"unfenced-aoe2de_db.dump.age"
            self.assertTrue(p.is_file())
            self.assertEqual(stat.S_IMODE(p.stat().st_mode),0o600)
            self.assertEqual(p.read_bytes(),sample)
            read=subprocess.run([sys.executable,"-B","-c",m.REMOTE_READ,
                                 "aoe2de_db"],capture_output=True,env=env,timeout=8)
            self.assertEqual(read.returncode,0)
            m.verify_sha_line(read.stdout,expected,len(sample))
            again=subprocess.run(code,input=sample,capture_output=True,env=env,timeout=8)
            self.assertNotEqual(again.returncode,0)
            self.assertEqual(p.read_bytes(),sample)

    def test_offhost_wrong_ciphertext_digest_cleans_partial_file(self):
        import os,subprocess,sys
        sample=b"age-encryption.org/v1\n"+b"Q"*512
        with tempfile.TemporaryDirectory(prefix="c06-intel-tamper-") as t:
            env={**os.environ,"HOME":t}
            r=subprocess.run([sys.executable,"-B","-c",m.REMOTE_WRITE,
                 "aoe2hd_db","f"*64,str(len(sample))],input=sample,
                 capture_output=True,env=env,timeout=8)
            self.assertNotEqual(r.returncode,0)
            root=Path(t)/".wolo-owner-authority"/"c06-unquiesced-mvcc-precapture-20261108"
            self.assertFalse(any(root.iterdir()))

    def test_offhost_foreign_database_rejected_before_write(self):
        import os,subprocess,sys
        with tempfile.TemporaryDirectory(prefix="c06-intel-unknown-") as t:
            env={**os.environ,"HOME":t}
            r=subprocess.run([sys.executable,"-B","-c",m.REMOTE_WRITE,
                 "postgres","f"*64,"1000"],input=b"X"*1000,
                 capture_output=True,env=env,timeout=8)
            self.assertNotEqual(r.returncode,0)
            self.assertFalse((Path(t)/".wolo-owner-authority").exists())

    def test_default_mode_non_mutating_inspect(self):
        self.assertIn('default="inspect"',SRC.read_text())
        self.assertLessEqual(m.MAX_CIPHER,12*(1<<30))
        self.assertGreaterEqual(m.M1_FREE_FLOOR,16*(1<<30))
        self.assertGreaterEqual(m.INTEL_FREE_FLOOR,20*(1<<30))
    def test_private_receipt_exact_false_authority_and_idempotence(self):
        with tempfile.TemporaryDirectory(prefix="c06-test-private-") as t:
            home=Path(t)/"private"
            home.mkdir(mode=0o700)
            orig=m.BASE
            try:
                m.BASE=home/"precapture"
                out=m.persist_receipt("aoe2de_db","a"*64,{
                    "ciphertext_sha256":"b"*64,"ciphertext_bytes":31415,
                    "offhost_path":m.REMOTE_BASE+"/unfenced-aoe2de_db.dump.age"})
                self.assertEqual(len(out),64)
                path=m.BASE/"unfenced-aoe2de_db-capture-receipt.json"
                self.assertEqual(stat.S_IMODE(path.stat().st_mode),0o600)
                data=json.loads(path.read_bytes())
                self.assertEqual(data["status"],
                                 "PASS_UNQUIESCED_MVCC_OFFHOST_DUMP_HOLD_FINANCIAL_RELEASE")
                for k in ("global_writer_fence_proven",
                          "cross_database_atomic_snapshot",
                          "full_wal_and_settlement_journals_captured",
                          "decryption_restoration_verified",
                          "c06_formal_backup_gate_closed",
                          "c07_formal_recovery_gate_closed",
                          "custody_financial_release_authorized"):
                    self.assertIs(data[k],False)
                with self.assertRaisesRegex(m.Hold,"ALREADY_EXISTS"):
                    m.persist_receipt("aoe2de_db","a"*64,{})
            finally:m.BASE=orig
    def test_unallowlisted_db_cannot_create_a_receipt(self):
        with self.assertRaises(m.Hold):
            m.persist_receipt("postgres","f"*64,{})
    def test_exact_ssh_host_pinning_and_two_recipient_constants(self):
        self.assertTrue(m.HOST_FP.startswith("SHA256:"))
        self.assertNotEqual(m.M1_FP,m.INTEL_FP)
        self.assertNotEqual(m.INTEL_FP,m.HOST_FP)
        self.assertNotIn("StrictHostKeyChecking=no",SRC.read_text())
        self.assertIn("StrictHostKeyChecking=yes",SRC.read_text())

if __name__=="__main__":unittest.main()

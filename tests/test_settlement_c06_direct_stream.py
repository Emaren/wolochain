"""Pure isolated tests for physically exercised C06 public-key streaming source."""
import base64
import hashlib
import importlib.util
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest

SRC=Path(__file__).resolve().parents[1]/"scripts/settlement_c06_direct_unquiesced_offhost_stream.py"
spec=importlib.util.spec_from_file_location("c06_direct",SRC)
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class C06DirectNoFunds(unittest.TestCase):
    def test_literal_database_scope_and_nonmutating_dump(self):
        self.assertEqual(module.DBS,("aoe2de_db","aoe2hd_db"))
        for name,cmd in module.DUMP.items():
            self.assertIn("pg_dump -F c -Z 3",cmd)
            self.assertIn("ionice -c3",cmd)
            self.assertIn("nice -n 15",cmd)
            self.assertTrue(cmd.endswith("-d "+name))
        self.assertEqual(module.MAX_CIPHER,12*(1<<30))
    def test_public_key_format_and_fingerprint(self):
        pub=struct.pack(">I",11)+b"ssh-ed25519"+struct.pack(">I",32)+bytes(range(32))
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/"pub"
            path.write_text("ssh-ed25519 "+base64.b64encode(pub).decode()+"\n")
            expected="SHA256:"+base64.b64encode(hashlib.sha256(pub).digest()).decode().rstrip("=")
            self.assertEqual(module.pubfp(path),expected)
            path.write_text("ssh-rsa "+base64.b64encode(pub).decode()+"\n")
            with self.assertRaises(module.Hold):module.pubfp(path)
            path.write_text("ssh-ed25519 INVALID\n")
            with self.assertRaises((ValueError,module.Hold)):module.pubfp(path)
    def test_bad_remote_databases_refused_before_filesystem(self):
        for code,args in [(module.RECV,["legacy_8092"]),(module.VERIFY,["legacy_8092","0"*64,"128","stage"]),(module.VERIFY,["aoe2hd_db","0"*64,"128","unsafe_phase"])]:
            result=subprocess.run([sys.executable,"-c",code,*args],capture_output=True,timeout=12)
            self.assertNotEqual(result.returncode,0)
    def test_cipher_header_store_and_three_passes(self):
        with tempfile.TemporaryDirectory() as td:
            env={**os.environ,"HOME":td}
            content=b"age-encryption.org/v1\n"+b"TEST_ENCRYPTED_CIPHER_ONLY_NOT_A_REAL_BACKUP"*10
            digest=hashlib.sha256(content).hexdigest()
            db="aoe2de_db"
            cmd=[sys.executable,"-c",module.RECV,db]
            receiver=subprocess.run(cmd,input=content,capture_output=True,env=env,timeout=12)
            self.assertEqual(receiver.returncode,0,receiver.stderr.decode())
            self.assertEqual(receiver.stdout.strip().decode(),f"{digest} {len(content)}")
            for phase in ("stage","finalize","readback"):
                result=subprocess.run([sys.executable,"-c",module.VERIFY,db,digest,str(len(content)),phase],env=env,capture_output=True,timeout=12)
                self.assertEqual(result.returncode,0,(phase,result.stderr))
                self.assertIn(digest.encode(),result.stdout)
            duplicate=subprocess.run(cmd,input=content,capture_output=True,env=env,timeout=12)
            self.assertNotEqual(duplicate.returncode,0)
    def test_wrong_hash_cannot_finalize(self):
        with tempfile.TemporaryDirectory() as td:
            env={**os.environ,"HOME":td}
            content=b"age-encryption.org/v1\n"+b"A"*300
            db="aoe2hd_db"
            c=subprocess.run([sys.executable,"-c",module.RECV,db],input=content,env=env,capture_output=True,timeout=12)
            self.assertEqual(c.returncode,0)
            bad=subprocess.run([sys.executable,"-c",module.VERIFY,db,"0"*64,str(len(content)),"finalize"],env=env,capture_output=True,timeout=12)
            self.assertNotEqual(bad.returncode,0)
            self.assertFalse((Path(td)/module.REMOTE_ROOT/("unfenced-"+db+".dump.age")).exists())

if __name__=="__main__":unittest.main()

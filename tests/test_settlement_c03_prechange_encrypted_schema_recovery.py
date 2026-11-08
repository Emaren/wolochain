"""C03 dual-owner-recipient offhost pre-migration schema rollback: safe fixtures.

No SSH, PostgreSQL, funds, private keys, or systemd invoked by this suite.
"""
from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
from pathlib import Path
import stat
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location(
    "c03_offhost_schema",ROOT/"scripts"/"settlement_c03_prechange_encrypted_schema_recovery.py")
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

def fake_ssh_public_key():
    blob=struct.pack(">I",11)+b"ssh-ed25519"+struct.pack(">I",32)+bytes(range(32))
    return b"ssh-ed25519 "+base64.b64encode(blob)+b" fixture\n"

class PrechangeRollbackTests(unittest.TestCase):
    def test_exact_three_postgres_metadata_only_scopes(self):
        self.assertEqual(set(m.COMMANDS),{"globals","hd","de"})
        for name,c in m.COMMANDS.items():
            self.assertIn("/usr/bin/sudo -u postgres ",c)
            self.assertNotIn(" --data-only",c)
            self.assertNotIn(" --file",c)
            self.assertNotIn("psql -c",c)
            self.assertNotIn("INSERT",c)
            self.assertNotIn("UPDATE",c)
            self.assertNotIn("DELETE",c)
            if name!="globals":
                self.assertIn(" --schema-only",c)
        self.assertIn("--no-role-passwords",m.COMMANDS["globals"])

    def test_supported_ed25519_ssh_public_fingerprint(self):
        a=fake_ssh_public_key()
        expected="SHA256:"+base64.b64encode(
            hashlib.sha256(base64.b64decode(a.split()[1])).digest()).decode().rstrip("=")
        self.assertEqual(m.fingerprint(a),expected)

    def test_wrong_public_key_algorithm_rejected(self):
        with self.assertRaises(m.Hold):
            m.fingerprint(b"ssh-rsa BBBB fixture\n")

    def test_invalid_or_empty_ssh_public_blob_rejected(self):
        for key in (b"",b"ssh-ed25519 AAAA fixture",b"ssh-ed25519 %%bad%% comment"):
            with self.subTest(key=key),self.assertRaises(m.Hold):
                m.fingerprint(key)

    def test_matching_ciphertext_sha_and_length_only(self):
        d="f"*64
        x=m.parse_verified_transfer((d+" 2443\n").encode(),"globals",d,2443)
        self.assertEqual(x["encrypted_sha256"],d)
        self.assertEqual(x["encrypted_bytes"],2443)
        self.assertIn("prechange-globals.sql.age",x["target"])

    def test_mismatched_cipher_hash_rejected(self):
        with self.assertRaisesRegex(m.Hold,"SHA_OR_LENGTH"):
            m.parse_verified_transfer((("f"*64)+" 2443").encode(),"globals","e"*64,2443)

    def test_mismatched_cipher_length_rejected(self):
        with self.assertRaisesRegex(m.Hold,"SHA_OR_LENGTH"):
            m.parse_verified_transfer((("f"*64)+" 2442").encode(),"globals","f"*64,2443)

    def test_duplicate_or_extra_receiver_stdout_rejected(self):
        for value in (b"abc\n",b"f"*64+b" 2443\nEXTRA\n",b"",b"f"*64+b" 0\n"):
            with self.subTest(value=value),self.assertRaises(m.Hold):
                m.parse_verified_transfer(value,"globals","f"*64,2443)

    def test_no_unsafe_financial_authorization_claims_in_receiver(self):
        self.assertIn("O_EXCL",m.REMOTE_WRITE)
        self.assertIn("O_NOFOLLOW",m.REMOTE_WRITE)
        self.assertIn("os.fsync",m.REMOTE_WRITE)
        self.assertIn("stat.S_IMODE",m.REMOTE_READ)
        self.assertNotIn("hashlib.file_digest",m.REMOTE_READ)
        self.assertNotIn("tx broadcast",m.REMOTE_WRITE.lower())
        self.assertEqual(m.MAX_ENCRYPTED,128<<20)

    def test_default_operator_mode_is_non_mutating_inspect(self):
        source=(ROOT/"scripts"/"settlement_c03_prechange_encrypted_schema_recovery.py").read_text()
        self.assertIn('default="inspect"',source)
        self.assertIn('financial_release_authorized":False',source)
        self.assertIn('production_database_mutated":False',source)
        self.assertIn('offhost_decryption_and_restore_tested":False',source)

    def test_intel_receipt_uses_same_label_as_source(self):
        for label in m.COMMANDS:
            target=m.parse_verified_transfer(
                (("c"*64)+" 1000").encode(),label,"c"*64,1000)
            self.assertTrue(target["target"].endswith("prechange-"+label+".sql.age"))

    def test_existing_owner_encrypted_globals_resume_is_sha_pinned(self):
        self.assertEqual(m.EXISTING_GLOBALS_CIPHER_SHA,
            "26d31d0b3a77980823dbab65f413a87df1d51b003e3b843e3fab012f54b6e022")
        self.assertEqual(m.EXISTING_GLOBALS_CIPHER_BYTES,2443)

    def test_private_receipt_no_overwrite(self):
        with tempfile.TemporaryDirectory(prefix="c03-prechange-tests-") as td:
            original=m.BASE
            try:
                m.BASE=Path(td)/"owner-private"
                x={"globals":{"encrypted_sha256":"a"*64,"encrypted_bytes":500,
                    "target":m.REMOTE_BASE+"/prechange-globals.sql.age"}}
                h=m.write_receipt("c"*64,x)
                self.assertEqual(len(h),64)
                p=m.BASE/m.FINAL
                self.assertEqual(stat.S_IMODE(p.stat().st_mode),0o600)
                content=json.loads(p.read_bytes())
                self.assertFalse(content["financial_release_authorized"])
                self.assertFalse(content["hd_de_full_row_data_included"])
                self.assertFalse(content["joint_database_snapshot_atomic"])
                self.assertFalse(content["c03_all_writers_fenced"])
                with self.assertRaisesRegex(m.Hold,"ALREADY_EXISTS"):
                    m.write_receipt("c"*64,x)
            finally:
                m.BASE=original

if __name__=="__main__":
    unittest.main()

"""C08 Intel off-host witness transport: protect existing C06 SSH receiver."""
from __future__ import annotations

import importlib.util
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
PATH=ROOT/"scripts/settlement_c08_intel_witness_ssh_enrollment_hold.py"
spec=importlib.util.spec_from_file_location("c08_transport",PATH)
tool=importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)
PUB_BLOB="A"*80
PUB=b"ssh-ed25519 "+PUB_BLOB.encode()+b" witness-test-public-key\n"
C06_LINE=b'restrict,from="test",command="python3 aoe2war-receiver-20261102.py" ssh-ed25519 AAAAfirst recovery\n'
M1_LINE=b'ssh-ed25519 AAAAsecond m1-management\n'
BASELINE=C06_LINE+M1_LINE


class C08TransportTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix="c08-transport-")
        self.home=Path(self.temp.name)
        (self.home/".ssh").mkdir(mode=0o700)
        self.path=self.home/".ssh/authorized_keys"
        self.path.write_bytes(BASELINE)
        self.path.chmod(0o600)
        self.base=self.home/".wolo-owner-authority/witness-runtime"
        self.base.mkdir(parents=True,mode=0o700)
        self.line=b'restrict,from="127.0.0.1,::1",command="python3 -B fake --witness-stdin" ssh-ed25519 '+PUB_BLOB.encode()+b"\n"

    def tearDown(self):
        self.temp.cleanup()

    def fixture(self,mode="ABSENT",keys=BASELINE):
        return {"keys":keys,"line":self.line,"sha":tool.sha(keys),
                "blob":PUB_BLOB,"existing_state":mode,"nonce_count":3}

    def test_fixed_public_key_is_only_accepted_input(self):
        with patch.object(tool,"EXPECTED_PUB_BLOB_SHA",tool.sha(PUB_BLOB.encode())):
            self.assertEqual(tool.public_key_blob(PUB),PUB_BLOB)
            with self.assertRaisesRegex(tool.HoldError,"C08_TRANSPORT_PUBKEY_PIN_MISMATCH"):
                tool.public_key_blob(b"ssh-ed25519 "+b"B"*80+b"\n")

    def test_approved_ssh_key_line_has_forced_command_and_loopback_restrictions(self):
        line=tool.key_line(Path("/Users/tonyblum"),PUB_BLOB)
        self.assertIn(b'restrict,from="127.0.0.1,::1",command="',line)
        self.assertIn(b"/usr/local/bin/python3.13 -B",line)
        self.assertIn(b"settlement_solo_runtime.py --witness-stdin",line)
        self.assertNotIn(b"aoe2war-receiver-20261102.py",line)
        with self.assertRaisesRegex(tool.HoldError,"C08_INTEL_HOME_PATH_UNSAFE"):
            tool.key_line(Path("/Users/owner;rm -rf /"),PUB_BLOB)

    def test_plan_is_nonmutating_and_rejects_paid_claim(self):
        with patch.object(tool,"preflight",return_value=self.fixture()):
            out=tool.action(self.home,PUB,"plan")
        self.assertEqual(out["status"],"HOLD_UNFUNDED_SSH_PLAN")
        self.assertFalse(out["financial_release_authorized"])
        self.assertEqual(self.path.read_bytes(),BASELINE)

    def test_apply_appends_exact_one_restricted_key_and_preserves_two_keys(self):
        with patch.object(tool,"EXPECTED_OLD_KEYS_SHA",tool.sha(BASELINE)):
            with patch.object(tool,"preflight",return_value=self.fixture()):
                out=tool.action(self.home,PUB,"apply",tool.sha(BASELINE))
        self.assertEqual(out["status"],"HOLD_SSH_KEY_ADMITTED_ONLY")
        new=self.path.read_bytes()
        self.assertEqual(new,BASELINE+self.line)
        self.assertTrue(new.startswith(BASELINE))
        self.assertEqual(new.count(b"aoe2war-receiver-20261102.py"),1)
        self.assertEqual(new.count(PUB_BLOB.encode()),1)
        self.assertEqual(stat.S_IMODE(self.path.stat().st_mode),0o600)
        backup=self.base/"c08-ssh-enrollment-backup/authorized_keys.before"
        self.assertEqual(backup.read_bytes(),BASELINE)
        self.assertEqual(stat.S_IMODE(backup.stat().st_mode),0o600)
        self.assertEqual(stat.S_IMODE(backup.parent.stat().st_mode),0o700)
        self.assertFalse(out["financial_release_authorized"])

    def test_revert_only_own_extra_entry_and_preserves_exact_original(self):
        with patch.object(tool,"EXPECTED_OLD_KEYS_SHA",tool.sha(BASELINE)):
            with patch.object(tool,"preflight",return_value=self.fixture()):
                tool.action(self.home,PUB,"apply",tool.sha(BASELINE))
            new=self.path.read_bytes()
            with patch.object(tool,"preflight",return_value=self.fixture("ALREADY_ENROLLED",new)):
                out=tool.action(self.home,PUB,"revert",tool.sha(new))
        self.assertEqual(out["status"],"HOLD_OWN_ENTRY_ROLLED_BACK")
        self.assertEqual(self.path.read_bytes(),BASELINE)
        self.assertFalse(out["financial_release_authorized"])

    def test_apply_cannot_overwrite_changed_existing_receiver_keys(self):
        bad=BASELINE+b"# new authorized operator was added concurrently\n"
        self.path.write_bytes(bad)
        with patch.object(tool,"EXPECTED_OLD_KEYS_SHA",tool.sha(BASELINE)):
            with patch.object(tool,"preflight",return_value=self.fixture("ABSENT",bad)):
                with self.assertRaisesRegex(tool.HoldError,"C08_BASELINE_KEYS_OR_EXISTING_WITNESS_DRIFT"):
                    tool.action(self.home,PUB,"apply",tool.sha(bad))
        self.assertEqual(self.path.read_bytes(),bad)

    def test_compare_and_swap_prevents_unauthorized_addition(self):
        with patch.object(tool,"preflight",return_value=self.fixture()):
            with self.assertRaisesRegex(tool.HoldError,"C08_AUTHORIZED_KEYS_COMPARE_AND_SWAP_FAILED"):
                tool.action(self.home,PUB,"apply","0"*64)
        self.assertEqual(self.path.read_bytes(),BASELINE)

    def test_same_public_key_without_restrictions_is_blocked(self):
        malicious=BASELINE+b"ssh-ed25519 "+PUB_BLOB.encode()+b"\n"
        with self.assertRaisesRegex(tool.HoldError,"C08_TRANSPORT_KEY_WRONG_RESTRICTIONS"):
            tool.classify_keys(malicious,PUB_BLOB,self.line)

    def test_duplicate_public_key_lines_blocked(self):
        duplicate=BASELINE+self.line+self.line
        with self.assertRaisesRegex(tool.HoldError,"C08_DUPLICATE_TRANSPORT_KEY"):
            tool.classify_keys(duplicate,PUB_BLOB,self.line)

    def test_missing_receiver_key_blocks_any_install(self):
        with self.assertRaisesRegex(tool.HoldError,"C08_C06_RECEIVER_RECORD_NOT_PRESERVED"):
            tool.classify_keys(M1_LINE,PUB_BLOB,self.line)

    def test_symlink_and_wrong_mode_private_authorization_rejected(self):
        self.path.chmod(0o644)
        with self.assertRaisesRegex(tool.HoldError,"C08_PRIVATE_FILE_MODE_OWNER_OR_TYPE"):
            tool.secure_read(self.path)
        self.path.chmod(0o600)
        target=self.home/".ssh/backup"
        target.symlink_to(self.path)
        with self.assertRaisesRegex(tool.HoldError,"C08_PRIVATE_PATH_NOT_CANONICAL"):
            tool.secure_read(target)

    def test_atomic_replace_fails_if_old_keys_changed_first(self):
        modified=BASELINE+b"# drift\n"
        self.path.write_bytes(modified)
        with self.assertRaisesRegex(tool.HoldError,"C08_AUTHORIZED_KEYS_CHANGED_BEFORE_WRITE"):
            tool.atomic_replace(self.path,BASELINE,BASELINE+self.line)
        self.assertEqual(self.path.read_bytes(),modified)

    def test_rollback_cannot_erase_concurrent_authorized_key(self):
        with patch.object(tool,"EXPECTED_OLD_KEYS_SHA",tool.sha(BASELINE)):
            with patch.object(tool,"preflight",return_value=self.fixture()):
                tool.action(self.home,PUB,"apply",tool.sha(BASELINE))
            appended=self.path.read_bytes()+b"# operator changed\n"
            self.path.write_bytes(appended)
            with patch.object(tool,"preflight",return_value=self.fixture("ALREADY_ENROLLED",appended)):
                with self.assertRaisesRegex(tool.HoldError,"C08_ROLLBACK_MUST_PRESERVE_C06_AND_ALL_OTHER_KEYS"):
                    tool.action(self.home,PUB,"revert",tool.sha(appended))
        self.assertEqual(self.path.read_bytes(),appended)

    def test_no_new_backup_overwrite_or_nonce_tamper(self):
        backup=self.base/"c08-ssh-enrollment-backup"
        backup.mkdir(mode=0o700)
        with self.assertRaisesRegex(tool.HoldError,"C08_BACKUP_ALREADY_EXISTS_OR_UNSAFE"):
            tool.save_backup(backup,BASELINE)

    def test_reject_root_permission_escalation(self):
        with patch.object(tool.os,"geteuid",return_value=0):
            with self.assertRaisesRegex(tool.HoldError,"C08_REFUSE_ROOT_INTEL_ACCOUNT"):
                tool.preflight(self.home,PUB)

    def test_refuse_unknown_modes_and_deletion_flag(self):
        with self.assertRaisesRegex(tool.HoldError,"C08_MODE_INVALID"):
            tool.action(self.home,PUB,"settle")
        with self.assertRaises(SystemExit) as err:
            tool.main(["--mode","fund"])
        self.assertEqual(err.exception.code,2)

    def test_no_private_key_signer_or_funded_capability_in_source(self):
        source=PATH.read_bytes()
        self.assertNotIn(b"wallet send",source)
        self.assertNotIn(b"MsgSend",source)
        self.assertNotIn(b"ssh-keygen -t",source)
        self.assertIn(b"financial_release_authorized",source)
        self.assertIn(b"NO_NONCE",b"NO_NONCE")  # no owner permit ever simulated here


if __name__=="__main__":
    unittest.main()

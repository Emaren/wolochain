"""C08 reversible authenticated host-key pin rotation (no C03/C06/nonce writes)."""
from __future__ import annotations

import base64
from contextlib import ExitStack
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat
import struct
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
PATH=ROOT/"scripts/settlement_c08_hel1_witness_hostkey_rotation_hold.py"
spec=importlib.util.spec_from_file_location("c08_rotation",PATH)
tool=importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)


def wire_key(octet):
    raw=struct.pack(">I",11)+b"ssh-ed25519"+struct.pack(">I",32)+bytes([octet])*32
    blob=base64.b64encode(raw)
    return b"ssh-ed25519 "+blob+b" test-key\n",blob


class HostkeyTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix="c08-key-test-")
        self.root=Path(self.temp.name)/"authority"
        self.root.mkdir(mode=0o700)
        self.old_pub,self.old_blob=wire_key(31)
        self.new_pub,self.new_blob=wire_key(32)
        self.old_hosts=(tool.EXPECTED_KEY_PATTERN+" ssh-ed25519 "+
                        self.old_blob.decode()+"\n").encode()
        self.owner=b'{"schema":"wolo.test.owner","no_private_keys":true}\n'
        self.config={
            "schema":"wolo.solo-maintenance-runtime-enrollment.v1",
            "source_commit":tool.EXPECTED_SOURCE,
            "controller_files":{f"controller{i}":"source-pinned" for i in range(6)},
            "owner_enrollment_sha256":tool.digest(self.owner),
            "witness":{"host":"127.0.0.1","port":22995,"user":"tonyblum",
                       "known_hosts_path":str(self.root/tool.HOST_NAME),
                       "known_hosts_sha256":tool.digest(self.old_hosts)},
        }
        self.raw=json.dumps(self.config,sort_keys=True,separators=(",",":")).encode()+b"\n"
        for name,body in ((tool.CONFIG_NAME,self.raw),(tool.HOST_NAME,self.old_hosts),
                          (tool.OWNER_NAME,self.owner)):
            p=self.root/name
            p.write_bytes(body)
            p.chmod(0o600)
        self.stack=ExitStack()
        self.stack.enter_context(patch.object(tool,"ROOT",self.root))
        self.stack.enter_context(patch.object(tool,"EXPECTED_CONFIG_SHA",tool.digest(self.raw)))
        self.stack.enter_context(patch.object(tool,"EXPECTED_OLD_KNOWN_SHA",tool.digest(self.old_hosts)))
        self.stack.enter_context(patch.object(tool,"EXPECTED_OLD_BLOB_SHA",tool.digest(self.old_blob)))
        self.stack.enter_context(patch.object(tool,"EXPECTED_NEW_BLOB_SHA",tool.digest(self.new_blob)))
        self.stack.enter_context(patch.object(tool,"financial_ports_absent"))
        self.stack.enter_context(patch.object(tool,"fsync_dir"))

    def tearDown(self):
        self.stack.close()
        self.temp.cleanup()

    def denied(self,why,mode="plan",pub=None):
        with self.assertRaisesRegex(tool.Stop,why):
            tool.operation(self.root,self.new_pub if pub is None else pub,mode)

    def test_plan_does_not_write_either_protected_file(self):
        d=tool.operation(self.root,self.new_pub,"plan")
        self.assertEqual(d["status"],"HOLD_NEW_INTEL_PIN_PLAN_ONLY")
        self.assertFalse(d["financial_release_authorized"])
        self.assertFalse(d["c08_gate_closed"])
        self.assertEqual((self.root/tool.CONFIG_NAME).read_bytes(),self.raw)
        self.assertEqual((self.root/tool.HOST_NAME).read_bytes(),self.old_hosts)
        self.assertFalse((self.root/tool.BACKUP_NAME).exists())

    def test_wrong_normal_mac_host_key_rotation_is_retired_before_port_checks(self):
        with patch.object(tool,"financial_ports_absent",side_effect=AssertionError(
                "obsolete forward mutation must STOP before probing live ports")):
            with self.assertRaisesRegex(tool.Stop,
                    "C08_OBSOLETE_MACOS_HOSTPIN_ROTATION_DISABLED"):
                tool.operation(self.root,self.new_pub,"apply")
        self.assertEqual((self.root/tool.HOST_NAME).read_bytes(),self.old_hosts)
        self.assertEqual((self.root/tool.CONFIG_NAME).read_bytes(),self.raw)
        self.assertEqual((self.root/tool.OWNER_NAME).read_bytes(),self.owner)
        self.assertFalse((self.root/tool.BACKUP_NAME).exists())

    def seed_historical_wrong_ssh_host_key_for_rollback(self):
        old_cfg,old_host,new_cfg,new_host=tool.current_state(self.root,self.new_pub)
        tool.create_backup(self.root,old_cfg,old_host)
        tool.replace_if_exact(self.root/tool.HOST_NAME,old_host,new_host)
        tool.replace_if_exact(self.root/tool.CONFIG_NAME,old_cfg,new_cfg)
        return old_cfg,old_host,new_cfg,new_host

    def test_revert_restores_exact_original_c08_bytes(self):
        self.seed_historical_wrong_ssh_host_key_for_rollback()
        d=tool.operation(self.root,self.new_pub,"rollback")
        self.assertEqual(d["status"],"HOLD_SOURCE_PIN_ROLLED_BACK")
        self.assertEqual((self.root/tool.CONFIG_NAME).read_bytes(),self.raw)
        self.assertEqual((self.root/tool.HOST_NAME).read_bytes(),self.old_hosts)
        self.assertFalse(d["financial_release_authorized"])

    def test_partial_interruption_after_first_file_is_rollbackable(self):
        newhost=tool.key_from_pub(self.new_pub)
        tool.create_backup(self.root,self.raw,self.old_hosts)
        tool.replace_if_exact(self.root/tool.HOST_NAME,self.old_hosts,newhost)
        d=tool.operation(self.root,self.new_pub,"rollback")
        self.assertEqual(d["status"],"HOLD_SOURCE_PIN_ROLLED_BACK")
        self.assertEqual((self.root/tool.CONFIG_NAME).read_bytes(),self.raw)
        self.assertEqual((self.root/tool.HOST_NAME).read_bytes(),self.old_hosts)

    def test_wrong_pubkey_is_refused_without_changes(self):
        other,_=wire_key(44)
        self.denied("C08_NEW_INTEL_KEY_NOT_TWO_WAY_VERIFIED",pub=other)
        self.assertEqual((self.root/tool.HOST_NAME).read_bytes(),self.old_hosts)

    def test_wrong_original_pin_is_refused(self):
        p=self.root/tool.HOST_NAME
        p.write_bytes(b"[127.0.0.1]:22995 ssh-ed25519 altered\n")
        self.denied("C08_ORIGINAL_PROTECTED_STATE_DRIFT")

    def test_operator_config_change_refused(self):
        p=self.root/tool.CONFIG_NAME
        p.write_bytes(self.raw+b"\n")
        self.denied("C08_ORIGINAL_PROTECTED_STATE_DRIFT")

    def test_owner_enrollment_change_refused(self):
        (self.root/tool.OWNER_NAME).write_bytes(b'{"changed":true}\n')
        self.denied("C08_OWNER_OR_HOST_PIN_DRIFT")

    def test_wrong_host_scope_and_port_refused_even_with_fresh_hash(self):
        self.config["witness"]["port"]=22
        self.raw=json.dumps(self.config,sort_keys=True,separators=(",",":")).encode()+b"\n"
        (self.root/tool.CONFIG_NAME).write_bytes(self.raw)
        with patch.object(tool,"EXPECTED_CONFIG_SHA",tool.digest(self.raw)):
            self.denied("C08_WITNESS_HOST_SCOPE_DRIFT")

    def test_duplicate_json_key_not_accepted(self):
        with self.assertRaisesRegex(tool.Stop,"C08_DUPLICATE_ENROLLMENT_JSON_KEY"):
            tool.dict_unique([("witness",1),("witness",2)])

    def test_symlink_and_world_mode_refused(self):
        p=self.root/tool.HOST_NAME
        p.chmod(0o644)
        self.denied("C08_PRIVATE_PIN_OWNER_OR_MODE_DRIFT")
        p.chmod(0o600)
        symlink=self.root/"fake-pin"
        symlink.symlink_to(p)
        with self.assertRaisesRegex(tool.Stop,"C08_PRIVATE_PIN_PATH_UNSAFE"):
            tool.private_read(symlink)

    def test_changed_or_added_operator_key_cannot_be_rolled_back(self):
        self.seed_historical_wrong_ssh_host_key_for_rollback()
        p=self.root/tool.HOST_NAME
        p.write_bytes(p.read_bytes()+b"# unreviewed extra\n")
        self.denied("C08_CANNOT_ROLLBACK_CONCURRENT_OPERATOR_CHANGE",mode="rollback")

    def test_no_backup_overwrite(self):
        self.seed_historical_wrong_ssh_host_key_for_rollback()
        with self.assertRaisesRegex(tool.Stop,"C08_PROTECTED_BACKUP_ALREADY_EXISTS"):
            tool.create_backup(self.root,self.raw,self.old_hosts)
        self.denied("C08_OBSOLETE_MACOS_HOSTPIN_ROTATION_DISABLED",mode="apply")

    def test_no_unsafe_root_directory(self):
        self.root.chmod(0o755)
        self.denied("C08_ROOT_AUTHORITY_DIRECTORY_DRIFT")

    def test_no_financial_port_activation(self):
        with patch.object(tool,"financial_ports_absent",
                          side_effect=tool.Stop("C08_FINANCIAL_LISTENER_PRESENT_OR_UNAVAILABLE")):
            self.denied("C08_FINANCIAL_LISTENER_PRESENT_OR_UNAVAILABLE")

    def test_no_funded_or_reload_mode(self):
        self.denied("C08_OPERATION_NOT_ALLOWED",mode="fund")
        self.denied("C08_OPERATION_NOT_ALLOWED",mode="restart")

    def test_no_service_actions_or_nonces_in_controller(self):
        src=PATH.read_text()
        self.assertNotIn("systemctl restart",src)
        self.assertNotIn("ALTER ROLE",src)
        self.assertNotIn("send-tx",src)
        self.assertNotIn("wolosatcheld --config",src)
        self.assertNotIn("nonce_root.mkdir",src)


if __name__=="__main__":
    unittest.main()

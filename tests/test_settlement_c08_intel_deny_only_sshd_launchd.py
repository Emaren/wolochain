"""C08 Intel deny-only loopback SSHD launchd source contract (hermetic fixtures)."""
from __future__ import annotations

import hashlib
import importlib.util
import plistlib
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location(
 "c08_deny_sshd",ROOT/"scripts"/"settlement_c08_intel_deny_only_sshd_launchd.py")
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

class Proc:
    def __init__(self,rc=0,stdout="",stderr=""):
        self.returncode=rc
        self.stdout=stdout
        self.stderr=stderr

class DenyOnlyLaunchD(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix="c08-owner-intel-deny-")
        self.home=Path(self.temp.name)/"Users"/"tonyblum"
        self.root=self.home/".wolo-owner-authority"
        self.base=self.root/"witness-sshd"
        self.agents=self.home/"Library"/"LaunchAgents"
        for p in (self.home,self.root,self.base):
            p.mkdir(mode=0o700,parents=True,exist_ok=True)
            p.chmod(0o700)
        self.agents.mkdir(mode=0o755,parents=True,exist_ok=True)
        self.agents.chmod(0o755)
        self.config=(b"Port 22996\nListenAddress 127.0.0.1\n"
                     b"PasswordAuthentication no\nAllowTcpForwarding no\n"
                     b"ForceCommand /usr/bin/false\n")
        self.auth=b'restrict,command="/usr/bin/false" ssh-ed25519 AAAATESTPUBKEY\n'
        self.pub=b"ssh-ed25519 AAAATESTHOSTKEY test\n"
        for name,raw in (("sshd_config",self.config),("authorized_keys",self.auth),
                         ("ssh_host_ed25519_key.pub",self.pub),
                         ("ssh_host_ed25519_key",b"fixture-key-material-not-a-real-private-key")):
            p=self.base/name
            p.write_bytes(raw);p.chmod(0o600)
        self.patchers=[
            patch.object(m,"USER_HOME",self.home),
            patch.object(m,"DEDICATED",self.base),
            patch.object(m,"CONFIG",self.base/"sshd_config"),
            patch.object(m,"AUTH",self.base/"authorized_keys"),
            patch.object(m,"HOST_PUB",self.base/"ssh_host_ed25519_key.pub"),
            patch.object(m,"HOST_PRIVATE",self.base/"ssh_host_ed25519_key"),
            patch.object(m,"PLIST",self.agents/(m.LABEL+".plist")),
            patch.object(m,"CONFIG_SHA256",hashlib.sha256(self.config).hexdigest()),
            patch.object(m,"AUTHORIZED_SHA256",hashlib.sha256(self.auth).hexdigest()),
            patch.object(m,"HOST_BLOB_SHA256",hashlib.sha256(b"AAAATESTHOSTKEY").hexdigest()),
            patch.object(m,"assert_owner_host",return_value=None),
            patch.object(m,"SSHD",Path("/usr/bin/false")),
        ]
        for p in self.patchers:p.start()
        self.p2=patch.object(m.subprocess,"run",side_effect=self.fake_run)
        self.p2.start()
        self.live=False
    def tearDown(self):
        self.p2.stop()
        for p in reversed(self.patchers):p.stop()
        self.temp.cleanup()
    def fake_run(self,cmd,**kwargs):
        if "-T" in cmd:
            return Proc(stdout="forcecommand /usr/bin/false\n")
        if "-t" in cmd:return Proc()
        if "print" in cmd:return Proc(rc=113)
        if "bootstrap" in cmd:
            self.live=True
            return Proc()
        if "bootout" in cmd:
            self.live=False
            return Proc()
        return Proc()
    def test_plist_exact_binary_no_shell_and_immutable_private_paths(self):
        p=plistlib.loads(m.plist())
        self.assertEqual(p["Label"],m.LABEL)
        self.assertEqual(p["ProgramArguments"][:4],
            [str(m.SSHD),"-D","-e","-f"])
        self.assertEqual(p["ProgramArguments"][4],str(m.CONFIG))
        self.assertNotIn("EnvironmentVariables",p)
        self.assertNotIn("/bin/sh",str(p["ProgramArguments"]))
        self.assertEqual(p["Umask"],63)
        self.assertTrue(p["RunAtLoad"])
        self.assertTrue(p["KeepAlive"])
    def test_valid_deny_profile_is_nonfinanced_hold(self):
        x=m.preflight()
        self.assertEqual(x["status"],"HOLD_DENY_ONLY_SSHD_PRECHECK")
        self.assertTrue(x["force_command_is_usr_bin_false"])
        self.assertFalse(x["source_admits_real_witness_executable"])
        self.assertFalse(x["funded_financial_release_authorized"])
    def test_modified_config_refused(self):
        (self.base/"sshd_config").write_bytes(self.config+b"PermitTTY yes\n")
        with self.assertRaisesRegex(m.Hold,"EXACT_DENY_ONLY_SSHD_CONFIG_CHANGED"):
            m.preflight()
    def test_changed_authorized_command_refused(self):
        (self.base/"authorized_keys").write_bytes(
             self.auth.replace(b"/usr/bin/false",b"/usr/bin/true"))
        with self.assertRaisesRegex(m.Hold,"EXACT_DENY_ONLY_SSH_KEY_COMMAND_CHANGED"):
            m.preflight()
    def test_hostkey_pub_substitution_refused(self):
        (self.base/"ssh_host_ed25519_key.pub").write_bytes(b"ssh-ed25519 BADHOSTKEY\n")
        with self.assertRaisesRegex(m.Hold,"DEDICATED_HOST_IDENTITY_CHANGED"):
            m.preflight()
    def test_world_readable_private_hostkey_refused(self):
        (self.base/"ssh_host_ed25519_key").chmod(0o644)
        with self.assertRaisesRegex(m.Hold,"WITNESS_FILE_MODE_OWNER_DRIFT"):
            m.preflight()
    def test_negative_user_owner_directory_mode(self):
        self.root.chmod(0o755)
        with self.assertRaisesRegex(m.Hold,"UNSAFE_OWNER_DIRECTORY"):
            m.preflight()
    def test_active_denied_process_starts_via_exact_launchd_only(self):
        checks=iter([False,True])
        with patch.object(m,"listen_active",side_effect=lambda:next(checks)):
            r=m.install()
        self.assertEqual(r["status"],"HOLD_DENY_ONLY_SSHD_STARTED_NO_WITNESS")
        self.assertFalse(r["financial_release_authorized"] if "financial_release_authorized" in r else r["funded_financial_release_authorized"])
        self.assertTrue(self.live)
        self.assertEqual(stat.S_IMODE(m.PLIST.stat().st_mode),0o600)
        self.assertEqual(m.PLIST.read_bytes(),m.plist())
    def test_apply_refuses_existing_unapproved_listener(self):
        with patch.object(m,"listen_active",return_value=True):
            with self.assertRaisesRegex(m.Hold,"WITNESS_SSHD_PREEXISTING"):
                m.install()
        self.assertFalse(m.PLIST.exists())
    def test_exact_rollback_preserves_authority_files(self):
        desired=m.plist()
        m.PLIST.write_bytes(desired);m.PLIST.chmod(0o600)
        before=(self.base/"authorized_keys").read_bytes()
        with patch.object(m,"state",return_value=True):
            r=m.rollback()
        self.assertEqual(r["status"],"HOLD_C08_DENY_ONLY_LAUNCHAGENT_REMOVED")
        self.assertFalse(m.PLIST.exists())
        self.assertEqual((self.base/"authorized_keys").read_bytes(),before)
    def test_changed_launchd_plist_denied_rollback(self):
        m.PLIST.write_bytes(b"operator_modified_launch_config")
        m.PLIST.chmod(0o600)
        with self.assertRaisesRegex(m.Hold,"C08_ROLLBACK_NOT_EXACT"):
            m.rollback()
        self.assertTrue(m.PLIST.exists())
    def test_no_wallet_chain_or_db_network_operations(self):
        text=(ROOT/"scripts"/"settlement_c08_intel_deny_only_sshd_launchd.py").read_text()
        self.assertNotIn("broadcast_tx",text)
        self.assertNotIn("ALTER TABLE",text)
        self.assertNotIn("systemctl",text)
        self.assertNotIn("send-tx",text)
        self.assertIn("ForceCommand /usr/bin/false",text)

if __name__=="__main__":
    unittest.main()

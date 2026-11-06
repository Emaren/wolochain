"""C06 Intel recovery tunnel supervisor must never widen SSH or self-authorize funds."""
import importlib.util
import os
from pathlib import Path
import plistlib
import stat
import tempfile
import unittest
from unittest.mock import patch

SOURCE=Path(__file__).resolve().parents[1]/"scripts/c06_intel_reverse_tunnel_supervisor.py"
spec=importlib.util.spec_from_file_location("c06tunnel",SOURCE)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class SupervisorTests(unittest.TestCase):
    def test_fixed_loopback_only_and_host_key_pinning(self):
        args=m.ssh_command(Path("/Users/tester"))
        s=" ".join(args)
        self.assertIn("127.0.0.1:22995:127.0.0.1:22",s)
        self.assertIn("StrictHostKeyChecking=yes",s)
        self.assertIn("HostKeyAlias=hel1-c06-intel",s)
        self.assertNotIn("root@hel1",s)
        self.assertIn("BatchMode=yes",s)
        self.assertIn("ExitOnForwardFailure=yes",s)
        self.assertIn("IdentitiesOnly=yes",s)
        self.assertIn("ServerAliveInterval=30",s)
        self.assertIn("-N",args)
        self.assertIn("-T",args)
        self.assertNotIn("0.0.0.0:22995",s)
        self.assertNotIn("StrictHostKeyChecking=no",s)
        self.assertNotIn("UserKnownHostsFile=/dev/null",s)

    def test_plist_relaunches_without_running_commands(self):
        p=plistlib.loads(m.render_plist(Path("/tmp/test/receiver.sh")))
        self.assertEqual(p["Label"],m.LABEL)
        self.assertEqual(p["ProgramArguments"],["/bin/sh","/tmp/test/receiver.sh"])
        self.assertIs(p["RunAtLoad"],True)
        self.assertIs(p["KeepAlive"],True)
        self.assertGreaterEqual(p["ThrottleInterval"],30)
        script=m.render_shell(Path("/Users/tester"))
        self.assertIn(b"exec /usr/bin/ssh",script)
        self.assertNotIn(b"curl ",script)

    def test_plan_never_claims_offhost_ready(self):
        result=m.public_plan(Path("/tmp"))
        self.assertEqual(result["state"],"HOLD_UNENROLLED")
        self.assertIs(result["financialReleaseAuthorized"],False)
        self.assertIs(result["offhostDecryptionOrBackupProven"],False)

    def test_install_refuses_arm64_or_root(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(m.platform,"machine",return_value="arm64"):
                with self.assertRaisesRegex(m.Hold,"INTEL_MAC"):
                    m.check_local_enrollment(Path(folder))
            with patch.object(m.platform,"machine",return_value="x86_64"),\
                 patch.object(m.os,"geteuid",return_value=0):
                with self.assertRaisesRegex(m.Hold,"INTEL_MAC"):
                    m.check_local_enrollment(Path(folder))

    def test_key_permissions_and_symlink_fail(self):
        with tempfile.TemporaryDirectory() as folder:
            key=Path(folder)/"key"
            key.write_bytes(b"not-a-real-key")
            key.chmod(0o600)
            m.secure_user_file(key,private=True)
            key.chmod(0o644)
            with self.assertRaises(m.Hold):
                m.secure_user_file(key,private=True)
            ref=Path(folder)/"link"
            ref.symlink_to(key)
            with self.assertRaises(m.Hold):
                m.secure_user_file(ref,private=True)

    def test_exclusive_non_overwrite_and_install_staged(self):
        with tempfile.TemporaryDirectory() as folder:
            home=Path(folder)
            (home/"Library").mkdir()
            with patch.object(m,"check_local_enrollment",return_value=True):
                x=m.install(home)
                self.assertEqual(x["state"],"STAGED_NOT_STARTED")
                self.assertFalse(x["financialReleaseAuthorized"])
                p=Path(x["launchAgent"])
                s=Path(x["script"])
                self.assertEqual(stat.S_IMODE(p.stat().st_mode),0o600)
                self.assertEqual(stat.S_IMODE(s.stat().st_mode),0o600)
                with self.assertRaises(m.Hold):
                    m.install(home)
                self.assertIn("StrictHostKeyChecking=yes",s.read_text())

    def test_dedicated_account_and_host_pin(self):
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as folder:
            home=Path(folder)
            ssh=home/".ssh"
            ssh.mkdir(mode=0o700)
            (ssh/m.KEY_NAME).write_bytes(b"mock-key-not-a-real-key")
            (ssh/m.KEY_NAME).chmod(0o600)
            (ssh/"known_hosts").write_text("placeholder known host")
            (ssh/"known_hosts").chmod(0o600)
            def fake(args,**kwargs):
                if args[0]=="/usr/bin/ssh-keygen":
                    return SimpleNamespace(returncode=0,stdout=b"pinned-host")
                return SimpleNamespace(returncode=0,stdout="user aoe2war-c06-reverse\nport 22\n")
            with patch.object(m.platform,"machine",return_value="x86_64"),\
                 patch.object(m.subprocess,"run",side_effect=fake):
                self.assertTrue(m.check_local_enrollment(home))
            def wrong(args,**kwargs):
                if args[0]=="/usr/bin/ssh-keygen":
                    return SimpleNamespace(returncode=0,stdout=b"pinned-host")
                return SimpleNamespace(returncode=0,stdout="user root\nport 22\n")
            with patch.object(m.platform,"machine",return_value="x86_64"),\
                 patch.object(m.subprocess,"run",side_effect=wrong):
                with self.assertRaisesRegex(m.Hold,"DEDICATED_NONROOT"):
                    m.check_local_enrollment(home)

if __name__=="__main__":
    unittest.main()

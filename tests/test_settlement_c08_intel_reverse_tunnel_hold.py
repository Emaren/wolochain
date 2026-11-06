"""C08 real Intel tunnel: force-port/key restrictions and rollback tests."""
from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
import plistlib
import stat
import tempfile
import unittest
from unittest.mock import patch
import sys

ROOT=Path(__file__).resolve().parents[1]
SCRIPT=ROOT/"scripts/settlement_c08_intel_reverse_tunnel_hold.py"
spec=importlib.util.spec_from_file_location("c08_intel_tunnel",SCRIPT)
c08=importlib.util.module_from_spec(spec)
spec.loader.exec_module(c08)


class FakeCompleted:
    def __init__(self,code=0):
        self.returncode=code
        self.stdout=b""
        self.stderr=b""


class TunnelTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix="c08-tunnel-")
        self.home=Path(self.tmp.name)/"Users"/"tester"
        self.home.mkdir(parents=True,mode=0o700)
        authority=self.home/".wolo-owner-authority"
        authority.mkdir(mode=0o700)
        tunnel=authority/"tunnel"
        tunnel.mkdir(mode=0o700)
        witness=authority/"witness-runtime"/"authority"
        witness.mkdir(parents=True,mode=0o700)
        agents=self.home/"Library"/"LaunchAgents"
        agents.mkdir(parents=True,mode=0o755)
        self.paths=c08.tunnel_paths(self.home)
        self.pub=b"ssh-ed25519 "+"B".encode()*60+b" test-tunnel\n"
        self.known=b"157.180.114.124 ssh-ed25519 "+"A".encode()*60+b"\n"
        self.witness=b'{"schema":"wolo.test-c08-enrollment"}\n'
        blobs=[
            ("private",b"placeholder-private-test-not-a-key",0o600),
            ("pub",self.pub,0o644),
            ("known",self.known,0o600),
            ("witness",self.witness,0o600),
        ]
        for name,raw,mode in blobs:
            p=self.paths[name]
            p.write_bytes(raw)
            p.chmod(mode)
        self.patchers=[
            patch.object(c08,"EXPECTED_HOME",self.home),
            patch.object(c08,"EXPECTED_PUB_BLOB_SHA",c08.digest(self.pub.split()[1])),
            patch.object(c08,"EXPECTED_KNOWN_SHA",c08.digest(self.known)),
            patch.object(c08,"EXPECTED_HEL1_HOST_BLOB_SHA",c08.digest(self.known.split()[2])),
            patch.object(c08,"EXPECTED_WITNESS_CONFIG_SHA",c08.digest(self.witness)),
            patch.object(c08,"PYTHON",Path(sys.executable)),
            patch.object(c08.Path,"home",return_value=self.home),
        ]
        for x in self.patchers:x.start()

    def tearDown(self):
        for x in reversed(self.patchers):x.stop()
        self.tmp.cleanup()

    def preflight(self):
        return c08.account_preflight(self.paths)

    def fake_launch(self,exists=False):
        def fake_run(argv,*args,**kwargs):
            if "print" in argv:
                return FakeCompleted(0 if exists else 113)
            return FakeCompleted(0)
        return patch.object(c08.subprocess,"run",side_effect=fake_run)

    def test_valid_private_tunnel_identity_and_pin(self):
        o=self.preflight()
        self.assertEqual(o["status"],"HOLD_ONLY")
        self.assertTrue(o["intel_tunnel_identity_pinned"])
        self.assertTrue(o["HEL1_host_key_pinned"])
        self.assertFalse(o["financial_release_authorized"])

    def test_ssh_command_is_fixed_restricted_nonfinancial(self):
        a=c08.ssh_arguments(self.paths)
        joined=" ".join(a)
        self.assertEqual(a[0],"/usr/bin/ssh")
        self.assertIn("localhost:22995:127.0.0.1:22",a)
        self.assertIn("wolo-witness-tunnel@157.180.114.124",a)
        self.assertIn("StrictHostKeyChecking=yes",a)
        self.assertIn("HostKeyAlgorithms=ssh-ed25519",a)
        self.assertIn("ExitOnForwardFailure=yes",a)
        self.assertIn("IdentitiesOnly=yes",a)
        self.assertIn("BatchMode=yes",a)
        self.assertIn("ProxyCommand=none",a)
        self.assertNotIn("22996",joined)
        self.assertNotIn("8092",joined)
        self.assertNotIn("8094",joined)
        self.assertNotIn("8095",joined)
        self.assertNotIn("sudo ",joined)
        self.assertNotIn("root@",joined)

    def test_plist_is_exact_source_hash_bound_background_keepalive(self):
        s=c08.digest(b"test-one-purpose-source")
        data=c08.launch_plist(self.paths,s)
        p=plistlib.loads(data)
        self.assertEqual(p["Label"],c08.LABEL)
        self.assertEqual(p["ProgramArguments"][5],"--source-sha256")
        self.assertEqual(p["ProgramArguments"][6],s)
        self.assertTrue(p["RunAtLoad"])
        self.assertTrue(p["KeepAlive"])
        self.assertEqual(p["ThrottleInterval"],30)
        self.assertNotIn("EnvironmentVariables",p)
        self.assertNotIn("Program",p)

    def test_plan_is_read_only(self):
        with self.fake_launch():
            x=c08.plan(self.paths,b"some reviewed test source")
        self.assertEqual(x["status"],"HOLD_SOURCE_PINNED_TUNNEL_INSTALL_PLAN")
        self.assertFalse(self.paths["installed"].exists())
        self.assertFalse(self.paths["plist"].exists())
        self.assertFalse(x["launchd_loaded"])
        self.assertFalse(x["financial_release_authorized"])

    def test_plan_refuses_preexisting_unreviewed_service(self):
        with self.fake_launch(exists=True):
            with self.assertRaisesRegex(c08.Hold,"C08_EXISTING_LAUNCHD_OR_SOURCE_NOT_PRISTINE"):
                c08.plan(self.paths,b"reviewed")

    def test_apply_installs_only_two_exact_private_files(self):
        src=b"reviewed source bytes for unit test"
        with self.fake_launch():
            x=c08.install(self.paths,src,c08.digest(src))
        self.assertEqual(x["status"],"HOLD_SOURCE_INSTALLED_SSH_ONLY")
        self.assertFalse(x["financial_release_authorized"])
        self.assertEqual(self.paths["installed"].read_bytes(),src)
        self.assertEqual(stat.S_IMODE(self.paths["installed"].stat().st_mode),0o500)
        self.assertEqual(stat.S_IMODE(self.paths["plist"].stat().st_mode),0o600)
        self.assertEqual(self.paths["plist"].read_bytes(),
                         c08.launch_plist(self.paths,c08.digest(src)))
        self.assertEqual(self.paths["known"].read_bytes(),self.known)
        self.assertEqual(self.paths["witness"].read_bytes(),self.witness)

    def test_apply_requires_exact_source_digest(self):
        with self.fake_launch():
            with self.assertRaisesRegex(c08.Hold,"C08_UNREVIEWED_TUNNEL_SOURCE"):
                c08.install(self.paths,b"reviewed","0"*64)

    def test_exact_rollback_removes_our_agent_only(self):
        src=b"reviewed source bytes for unit test"
        with self.fake_launch():
            c08.install(self.paths,src,c08.digest(src))
            r=c08.rollback(self.paths,c08.digest(src))
        self.assertEqual(r["status"],"HOLD_C08_OWN_TUNNEL_SERVICE_REMOVED")
        self.assertFalse(self.paths["installed"].exists())
        self.assertFalse(self.paths["plist"].exists())
        self.assertEqual(self.paths["private"].read_bytes(),
                         b"placeholder-private-test-not-a-key")

    def test_rollback_cannot_delete_modified_agent(self):
        src=b"reviewed source bytes for unit test"
        with self.fake_launch():
            c08.install(self.paths,src,c08.digest(src))
        self.paths["plist"].write_bytes(b"operator changed launch service")
        with self.fake_launch():
            with self.assertRaises(c08.Hold):
                c08.rollback(self.paths,c08.digest(src))
        self.assertTrue(self.paths["installed"].exists())
        self.assertTrue(self.paths["plist"].exists())

    def test_private_tunnel_key_not_read_by_preflight(self):
        reader=c08.secure_regular
        def observing_reader(path,mode,*,read=False):
            if path==self.paths["private"]:
                self.assertFalse(read,"must not read private SSH key")
            return reader(path,mode,read=read)
        with patch.object(c08,"secure_regular",side_effect=observing_reader):
            self.preflight()

    def test_private_tunnel_key_wrong_mode_rejected(self):
        self.paths["private"].chmod(0o644)
        with self.assertRaisesRegex(c08.Hold,"C08_FILE_OWNER_MODE_TYPE_OR_SIZE_DRIFT"):
            self.preflight()

    def test_upstream_ssh_key_mismatch_rejected(self):
        self.paths["known"].write_bytes(b"157.180.114.124 ssh-ed25519 REPLACED\n")
        with self.assertRaisesRegex(c08.Hold,"C08_TUNNEL_HEL1_TRUST_DRIFT"):
            self.preflight()

    def test_altered_witness_enrollment_rejected(self):
        self.paths["witness"].write_bytes(b'{"altered":true}\n')
        with self.assertRaisesRegex(c08.Hold,"C08_INTEL_WITNESS_ENROLLMENT_CHANGED"):
            self.preflight()

    def test_unexpected_public_tunnel_key_rejected(self):
        self.paths["pub"].write_bytes(b"ssh-ed25519 "+"C".encode()*60+b"\n")
        with self.assertRaisesRegex(c08.Hold,"C08_TUNNEL_SSH_IDENTITY_DRIFT"):
            self.preflight()

    def test_no_financial_function_or_owner_permit_in_source(self):
        raw=SCRIPT.read_text()
        self.assertNotIn("send-tx",raw)
        self.assertNotIn("MsgSend",raw)
        self.assertNotIn("PAYOUT_AUTHORIZED",raw)
        self.assertNotIn("systemctl restart",raw)
        self.assertNotIn("ssh-keygen -t",raw)
        self.assertIn("financial_release_authorized",raw)


if __name__=="__main__":
    unittest.main()

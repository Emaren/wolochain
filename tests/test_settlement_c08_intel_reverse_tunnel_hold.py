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
        dedicated=authority/"witness-sshd"
        dedicated.mkdir(mode=0o700)
        agents=self.home/"Library"/"LaunchAgents"
        agents.mkdir(parents=True,mode=0o755)
        self.paths=c08.tunnel_paths(self.home)
        self.pub=b"ssh-ed25519 "+"B".encode()*60+b" test-tunnel\n"
        self.known=b"157.180.114.124 ssh-ed25519 "+"A".encode()*60+b"\n"
        self.witness=b'{"schema":"wolo.test-c08-enrollment"}\n'
        self.dedicated_pub=b"ssh-ed25519 "+b"D"*60+b" witness-test-host\n"
        self.dedicated_auth=b'restrict,command="/usr/bin/false" ssh-ed25519 '+b"E"*60+b"\n"
        dedicated_root=str(dedicated).encode("ascii")
        self.dedicated_config=(b"Port 22996\nListenAddress 127.0.0.1\n"
                               b"HostKey "+dedicated_root+b"/ssh_host_ed25519_key\n"
                               b"PidFile "+dedicated_root+b"/sshd.pid\n"
                               b"AuthorizedKeysFile "+dedicated_root+b"/authorized_keys\n"
                               b"AllowUsers tonyblum\n"
                               b"PubkeyAuthentication yes\nPasswordAuthentication no\n"
                               b"UsePAM no\nStrictModes yes\nPermitTTY no\n"
                               b"AllowTcpForwarding no\nForceCommand /usr/bin/false\n")
        blobs=[
            ("private",b"placeholder-private-test-not-a-key",0o600),
            ("pub",self.pub,0o644),
            ("known",self.known,0o600),
            ("witness",self.witness,0o600),
            ("dedicated_config",self.dedicated_config,0o600),
            ("dedicated_authorized",self.dedicated_auth,0o600),
            ("dedicated_host_pub",self.dedicated_pub,0o600),
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
            patch.object(c08,"EXPECTED_DEDICATED_SSHD_HOST_BLOB_SHA",c08.digest(self.dedicated_pub.split()[1])),
            patch.object(c08,"EXPECTED_DEDICATED_C08_CLIENT_BLOB_SHA",c08.digest(self.dedicated_auth.split()[2])),
            patch.object(c08,"PYTHON",Path(sys.executable)),
            patch.object(c08.Path,"home",return_value=self.home),
        ]
        for x in self.patchers:x.start()

    def tearDown(self):
        for x in reversed(self.patchers):x.stop()
        self.tmp.cleanup()

    def preflight(self):
        return c08.account_preflight(self.paths)

    def admitted(self):
        outcome=self.preflight()
        outcome["dedicated_backend_admitted"]=True
        outcome["dedicated_witness_deny_profile_active"]=False
        outcome["dedicated_witness_protocol_forced"]=True
        outcome["dedicated_witness_sshd_listening"]=True
        return patch.object(c08,"account_preflight",return_value=outcome)

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
        self.assertIn("localhost:22995:127.0.0.1:22996",a)
        self.assertIn("wolo-witness-tunnel@157.180.114.124",a)
        self.assertIn("StrictHostKeyChecking=yes",a)
        self.assertIn("HostKeyAlgorithms=ssh-ed25519",a)
        self.assertIn("ExitOnForwardFailure=yes",a)
        self.assertIn("IdentitiesOnly=yes",a)
        self.assertIn("BatchMode=yes",a)
        self.assertIn("ProxyCommand=none",a)
        self.assertNotIn("localhost:22996:",joined)
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
        self.assertEqual(x["status"],"HOLD_DEDICATED_WITNESS_SSHD_NOT_ADMITTED")
        self.assertFalse(x["dedicated_backend_admitted"])
        self.assertTrue(x["dedicated_witness_deny_profile_active"])
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
        with self.fake_launch(),self.admitted():
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
        with self.fake_launch(),self.admitted():
            with self.assertRaisesRegex(c08.Hold,"C08_UNREVIEWED_TUNNEL_SOURCE"):
                c08.install(self.paths,b"reviewed","0"*64)

    def test_exact_rollback_removes_our_agent_only(self):
        src=b"reviewed source bytes for unit test"
        with self.fake_launch(),self.admitted():
            c08.install(self.paths,src,c08.digest(src))
            r=c08.rollback(self.paths,c08.digest(src))
        self.assertEqual(r["status"],"HOLD_C08_OWN_TUNNEL_SERVICE_REMOVED")
        self.assertFalse(self.paths["installed"].exists())
        self.assertFalse(self.paths["plist"].exists())
        self.assertEqual(self.paths["private"].read_bytes(),
                         b"placeholder-private-test-not-a-key")

    def test_rollback_cannot_delete_modified_agent(self):
        src=b"reviewed source bytes for unit test"
        with self.fake_launch(),self.admitted():
            c08.install(self.paths,src,c08.digest(src))
        self.paths["plist"].write_bytes(b"operator changed launch service")
        with self.fake_launch(),self.admitted():
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

    def test_dedicated_realistic_deny_profile_blocks_install_without_writes(self):
        with self.fake_launch():
            with self.assertRaisesRegex(c08.Hold,"C08_DEDICATED_WITNESS_SSHD_NOT_ADMITTED"):
                c08.install(self.paths,b"safe-source",c08.digest(b"safe-source"))
        self.assertFalse(self.paths["installed"].exists())
        self.assertFalse(self.paths["plist"].exists())

    def test_dedicated_rejects_substituted_host_key(self):
        self.paths["dedicated_host_pub"].write_bytes(b"ssh-ed25519 "+b"X"*60+b"\n")
        with self.assertRaisesRegex(c08.Hold,"C08_DEDICATED_WITNESS_HOST_KEY_MISMATCH"):
            self.preflight()

    def test_dedicated_rejects_port_22_substitution(self):
        cfg=self.paths["dedicated_config"]
        cfg.write_bytes(self.dedicated_config.replace(b"Port 22996",b"Port 22"))
        with self.assertRaisesRegex(c08.Hold,"C08_DEDICATED_WITNESS_SSHD_CONFIG_DRIFT"):
            self.preflight()

    def test_dedicated_rejects_system_hostkey_substitution(self):
        cfg=self.paths["dedicated_config"]
        cfg.write_bytes(self.dedicated_config.replace(
            str(self.paths["dedicated"]).encode()+b"/ssh_host_ed25519_key",
            b"/etc/ssh/ssh_host_ed25519_key"))
        with self.assertRaisesRegex(c08.Hold,"C08_DEDICATED_WITNESS_SSHD_CONFIG_DRIFT"):
            self.preflight()

    def test_dedicated_rejects_broad_forwarding(self):
        cfg=self.paths["dedicated_config"]
        cfg.write_bytes(self.dedicated_config.replace(
            b"AllowTcpForwarding no",b"AllowTcpForwarding yes"))
        with self.assertRaisesRegex(c08.Hold,"C08_DEDICATED_WITNESS_SSHD_CONFIG_DRIFT"):
            self.preflight()

    def test_dedicated_rejects_wrong_ssh_authorized_key(self):
        auth=self.paths["dedicated_authorized"]
        auth.write_bytes(self.dedicated_auth.replace(b"E"*60,b"F"*60))
        with self.assertRaisesRegex(c08.Hold,"C08_DEDICATED_ROOT_WITNESS_KEY_NOT_PINNED"):
            self.preflight()

    def test_dedicated_ignores_unadmitted_listener(self):
        cfg=self.paths["dedicated_config"]
        cfg.write_bytes(self.dedicated_config.replace(
            b"ForceCommand /usr/bin/false\n",b""))
        # Key is still bound to a deliberate false command, even though
        # the server's deny-only ForceCommand directive was removed.
        self.assertTrue(self.preflight()["dedicated_witness_deny_profile_active"])
        self.assertFalse(self.preflight()["dedicated_backend_admitted"])

    def test_rollback_remains_available_after_dedicated_backend_loss(self):
        src=b"safe-reviewed-c08-source"
        with self.fake_launch(),self.admitted():
            c08.install(self.paths,src,c08.digest(src))
        self.paths["dedicated_config"].unlink()
        with self.fake_launch():
            result=c08.rollback(self.paths,c08.digest(src))
        self.assertEqual(result["status"],"HOLD_C08_OWN_TUNNEL_SERVICE_REMOVED")
        self.assertFalse(result["financial_release_authorized"])
        self.assertFalse(self.paths["installed"].exists())
        self.assertFalse(self.paths["plist"].exists())


    def test_additional_contradictory_sshd_directives_are_denied(self):
        path=self.paths["dedicated_config"]
        for extra in (b"PasswordAuthentication yes\n",
                      b"ListenAddress 0.0.0.0\n",
                      b"AllowTcpForwarding yes\n",
                      b"AllowUsers unreviewed\n",
                      b"PermitTTY yes\n",
                      b"PubkeyAuthentication no\n",
                      b"Include /tmp/unchecked.conf\n",
                      b"passwordauthentication yes\n"):
            with self.subTest(extra=extra):
                path.write_bytes(extra+self.dedicated_config)
                with self.assertRaisesRegex(
                        c08.Hold,"C08_DEDICATED_WITNESS_SSHD_CONFIG_DRIFT"):
                    self.preflight()
        path.write_bytes(self.dedicated_config)

    def test_duplicate_directive_and_additive_allowlist_rejected(self):
        p=self.paths["dedicated_config"]
        for extra in (b"AllowUsers second-user\n",
                      b"Port 22996\n",
                      b"ListenAddress 127.0.0.1\n",
                      b"HostKey /tmp/unreviewed-hostkey\n"):
            with self.subTest(extra=extra):
                p.write_bytes(self.dedicated_config+extra)
                with self.assertRaisesRegex(
                        c08.Hold,"C08_DEDICATED_WITNESS_SSHD_CONFIG_DRIFT"):
                    self.preflight()
        p.write_bytes(self.dedicated_config)

    def test_active_witness_substrings_are_not_forced_command_authority(self):
        cfg=self.paths["dedicated_config"]
        auth=self.paths["dedicated_authorized"]
        cfg.write_bytes(self.dedicated_config.replace(
            b"ForceCommand /usr/bin/false\n",b""))
        for command in (
            b"/bin/echo settlement_solo_runtime.py --witness-stdin",
            b"/bin/sh -c echo_settlement_solo_runtime.py--witness-stdin",
            b"settlement_solo_runtime.py --witness-stdin"):
            with self.subTest(command=command):
                auth.write_bytes(b'restrict,command="'+command+
                                 b'" ssh-ed25519 '+b"E"*60+b"\n")
                with self.assertRaisesRegex(
                        c08.Hold,"C08_DEDICATED_WITNESS_COMMAND_NOT_REVIEWED"):
                    self.preflight()

    def test_actual_intel_deny_only_hardened_config_remains_valid_hold(self):
        p=self.paths["dedicated_config"]
        optional=(b"AddressFamily inet\nPermitRootLogin no\n"
                  b"AuthenticationMethods publickey\n"
                  b"ChallengeResponseAuthentication no\n"
                  b"AllowAgentForwarding no\nX11Forwarding no\n"
                  b"PermitTunnel no\nPermitUserEnvironment no\n"
                  b"MaxSessions 1\n")
        p.write_bytes(self.dedicated_config+optional)
        pre=self.preflight()
        self.assertTrue(pre["dedicated_witness_deny_profile_active"])
        self.assertFalse(pre["dedicated_witness_protocol_forced"])
        self.assertFalse(pre["dedicated_backend_admitted"])



    def active_fixture(self):
        """Review-only synthetic active profile: no SSHD or tunnel is started."""
        runtime=self.paths["witness_runtime_source"]
        runtime.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        runtime.write_bytes(b"synthetic-reviewed-c08-nonce-witness-source")
        runtime.chmod(0o600)
        config={
            "schema":"wolo.solo-maintenance-runtime-enrollment.v1",
            "source_commit":c08.EXPECTED_WITNESS_RUNTIME_SOURCE_COMMIT,
            "controller_files":{"settlement_solo_runtime.py":c08.digest(runtime.read_bytes())},
        }
        raw=c08.json.dumps(config,sort_keys=True).encode()
        self.paths["witness"].write_bytes(raw)
        self.paths["dedicated_config"].write_bytes(
            self.dedicated_config.replace(b"ForceCommand /usr/bin/false\n",b""))
        self.paths["dedicated_authorized"].write_bytes(
            b'restrict,command="'+c08.REVIEWED_WITNESS_EXEC_COMMAND+
            b'" ssh-ed25519 '+b"E"*60+b"\n")
        return runtime, raw

    def active_source_review(self, raw, runtime):
        class LocalListeningStub:
            def __enter__(self): return self
            def __exit__(self,*args): return False
            def settimeout(self,seconds): assert seconds == 0.35
            def connect_ex(self,addr):
                assert addr==("127.0.0.1",22996)
                return 0
        return (
            patch.object(c08,"EXPECTED_WITNESS_CONFIG_SHA",c08.digest(raw)),
            patch.object(c08,"EXPECTED_WITNESS_RUNTIME_SOURCE_SHA",c08.digest(runtime.read_bytes())),
            patch.object(c08.socket,"socket",return_value=LocalListeningStub()),
        )

    def test_exact_forced_witness_command_requires_byte_pinned_source(self):
        runtime,raw=self.active_fixture()
        from contextlib import ExitStack
        with ExitStack() as stack:
            for p in self.active_source_review(raw,runtime):stack.enter_context(p)
            result=self.preflight()
        self.assertTrue(result["dedicated_witness_protocol_forced"])
        self.assertTrue(result["dedicated_backend_admitted"])
        self.assertFalse(result["dedicated_witness_deny_profile_active"])
        self.assertFalse(result["financial_release_authorized"])
        self.assertFalse(result["offhost_witness_nonce_consumed"])
        self.assertFalse(self.paths["installed"].exists())

    def test_changed_source_refused_even_with_exact_forced_command(self):
        runtime,raw=self.active_fixture()
        from contextlib import ExitStack
        with ExitStack() as stack:
            for p in self.active_source_review(raw,runtime):stack.enter_context(p)
            runtime.write_bytes(b"malicious-owner-path-substitution")
            with self.assertRaisesRegex(
                    c08.Hold,"C08_WITNESS_EXECUTABLE_SOURCE_DRIFT"):
                self.preflight()

    def test_witness_source_group_readable_refused(self):
        runtime,raw=self.active_fixture()
        from contextlib import ExitStack
        with ExitStack() as stack:
            for p in self.active_source_review(raw,runtime):stack.enter_context(p)
            runtime.chmod(0o644)
            with self.assertRaisesRegex(
                    c08.Hold,"C08_FILE_OWNER_MODE_TYPE_OR_SIZE_DRIFT"):
                self.preflight()

    def test_enrollment_source_commit_change_refused(self):
        runtime,raw=self.active_fixture()
        bad=c08.json.loads(raw)
        bad["source_commit"]="b"*40
        tampered=c08.json.dumps(bad,sort_keys=True).encode()
        self.paths["witness"].write_bytes(tampered)
        from contextlib import ExitStack
        with ExitStack() as stack:
            for p in self.active_source_review(tampered,runtime):stack.enter_context(p)
            with self.assertRaisesRegex(
                    c08.Hold,"C08_ACTIVE_WITNESS_ENROLLMENT_SOURCE_MISMATCH"):
                self.preflight()

    def test_existing_deny_force_stays_deny_even_with_reviewed_key(self):
        runtime,raw=self.active_fixture()
        self.paths["dedicated_config"].write_bytes(self.dedicated_config)
        from contextlib import ExitStack
        with ExitStack() as stack:
            for p in self.active_source_review(raw,runtime):stack.enter_context(p)
            result=self.preflight()
        self.assertTrue(result["dedicated_witness_deny_profile_active"])
        self.assertFalse(result["dedicated_backend_admitted"])
        self.assertFalse(result["financial_release_authorized"])

if __name__=="__main__":
    unittest.main()

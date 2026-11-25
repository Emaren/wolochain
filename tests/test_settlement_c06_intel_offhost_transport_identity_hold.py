import base64
import hashlib
import io
import json
import struct
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch
from pathlib import Path
from scripts import settlement_c06_intel_offhost_transport_identity_hold as c

def public_key():
    name=b"ssh-ed25519"
    wire=struct.pack("!I",len(name))+name+struct.pack("!I",32)+b"X"*32
    fingerprint="SHA256:"+base64.b64encode(hashlib.sha256(wire).digest()).decode().rstrip("=")
    output="[127.0.0.1]:22996 ssh-ed25519 "+base64.b64encode(wire).decode()+"\n"
    return fingerprint,output

def fixture():
    fp,scan=public_key()
    enrollment={
        "schema":"aoe2war.c06.intel-transport-live.v1",
        "status":"PASS_C06_ONLY_TRANSPORT_PHYSICALLY_VERIFIED",
        "remote_listen":"127.0.0.1:22996",
        "scope":"transport-only: dedicated Intel SSH reverse path",
        "intel_ssh_host_fingerprint":fp,
        "intel_launchd_reconnect_observed":True,
        "financial_release_authorized":False,
        "formal_c06_gate_accepted":False,"formal_c07_gate_accepted":False,
        "global_c03_gate_accepted":False,
        "quiesced_joint_financial_backup_captured":False,
    }
    raw=(json.dumps(enrollment,sort_keys=True)+"\n").encode()
    return raw,scan

class IntelTransportTests(unittest.TestCase):
    def setUp(self):
        self.raw,self.scan=fixture()
        self.sha_patch=patch.object(c,"ENROLLMENT_SHA256",hashlib.sha256(self.raw).hexdigest())
        self.sha_patch.start()
        self.addCleanup(self.sha_patch.stop)

    def reject(self,raw=None,banner=b"SSH-2.0-OpenSSH_test\r\n",scan=None):
        with self.assertRaises(c.Hold):
            c.verify(self.raw if raw is None else raw,
                     banner,self.scan if scan is None else scan)

    def test_matching_ssh_identity_never_accepts_financial_backup(self):
        d=c.verify(self.raw,b"SSH-2.0-OpenSSH_test\r\n",self.scan)
        self.assertEqual(d["status"],
            "HOLD_C06_TRANSPORT_HOST_IDENTITY_MATCHED_BACKUP_NOT_CAPTURED")
        self.assertTrue(d["live_ed25519_host_identity_matches_previously_enrolled"])
        self.assertFalse(d["encrypted_financial_backup_captured"])
        self.assertFalse(d["global_financial_writer_quiescence_proved"])
        self.assertFalse(d["formal_c06_gate_accepted"])
        self.assertFalse(d["formal_c07_gate_accepted"])
        self.assertFalse(d["financial_release_authorized"])

    def test_unauthenticated_ssh_banner_only_rejected(self):
        self.reject(banner=b"HTTP/1.1 200 OK\r\n")
        self.reject(banner=b"SSH-1.5-test\r\n")
        self.reject(banner=b"SSH-2.0-NoLineTerminator")

    def test_host_key_fingerprint_rotation_rejected(self):
        good=self.scan.split()
        good[2]=good[2][:-3]+"AAA"
        self.reject(scan=" ".join(good)+"\n")

    def test_wrong_listen_port_or_host_rejected(self):
        self.reject(scan=self.scan.replace(":22996",":22995"))
        self.reject(scan=self.scan.replace("127.0.0.1","0.0.0.0"))

    def test_duplicate_remote_host_key_rejected(self):
        self.reject(scan=self.scan+self.scan)

    def test_non_ed25519_algorithm_rejected(self):
        self.reject(scan=self.scan.replace("ssh-ed25519","ssh-rsa"))

    def test_empty_or_broken_public_key_rejected(self):
        self.reject(scan="")
        self.reject(scan="[127.0.0.1]:22996 ssh-ed25519 !!!\n")

    def test_public_key_parser_accepts_ssh_keyscan_comment_lines(self):
        fp=c.parse_live_public_key("# 127.0.0.1:22996 SSH-2.0-test\n"+self.scan)
        self.assertEqual(fp,c.parse_enrollment(self.raw))

    def test_enrollment_sha_change_rejected(self):
        with patch.object(c,"ENROLLMENT_SHA256","0"*64):
            self.reject()

    def test_enrollment_fake_gate_acceptance_rejected(self):
        d=json.loads(self.raw)
        d["formal_c06_gate_accepted"]=True
        raw=(json.dumps(d,sort_keys=True)+"\n").encode()
        with patch.object(c,"ENROLLMENT_SHA256",hashlib.sha256(raw).hexdigest()):
            self.reject(raw=raw)

    def test_scope_upgrade_rejected(self):
        d=json.loads(self.raw)
        d["scope"]="backup-captured"
        raw=(json.dumps(d,sort_keys=True)+"\n").encode()
        with patch.object(c,"ENROLLMENT_SHA256",hashlib.sha256(raw).hexdigest()):
            self.reject(raw=raw)

    def test_remote_port_substitution_rejected(self):
        d=json.loads(self.raw)
        d["remote_listen"]="127.0.0.1:22995"
        raw=(json.dumps(d,sort_keys=True)+"\n").encode()
        with patch.object(c,"ENROLLMENT_SHA256",hashlib.sha256(raw).hexdigest()):
            self.reject(raw=raw)

    def test_prior_receiver_reconnect_must_be_enrolled(self):
        d=json.loads(self.raw)
        d["intel_launchd_reconnect_observed"]=False
        raw=(json.dumps(d,sort_keys=True)+"\n").encode()
        with patch.object(c,"ENROLLMENT_SHA256",hashlib.sha256(raw).hexdigest()):
            self.reject(raw=raw)

    def test_readonly_observer_has_no_mutating_commands(self):
        s=Path(c.__file__).read_text()
        for forbidden in ("systemctl restart","pg_terminate_backend","scp ",
                          "rsync ","ssh -N ","ALTER ROLE","setfacl ","pg_dump ",
                          "authorized_keys.append","git push "):
            self.assertNotIn(forbidden,s)

    def test_probe_error_emits_stop_not_fake_pass(self):
        with patch.object(c,"probe",side_effect=c.Hold("C06_OFFHOST_SSH_IDENTITY_DRIFT")):
            out=io.StringIO()
            with redirect_stdout(out):
                code=c.main()
            self.assertEqual(code,2)
            d=json.loads(out.getvalue())
            self.assertEqual(d["status"],"STOP")
            self.assertFalse(d["financial_release_authorized"])

    def test_probe_success_is_exit_three(self):
        fake=c.verify(self.raw,b"SSH-2.0-OpenSSH_test\r\n",self.scan)
        with patch.object(c,"probe",return_value=fake):
            out=io.StringIO()
            with redirect_stdout(out):
                code=c.main()
            self.assertEqual(code,3)
            self.assertFalse(json.loads(out.getvalue())["formal_c06_gate_accepted"])

if __name__=="__main__":
    unittest.main()

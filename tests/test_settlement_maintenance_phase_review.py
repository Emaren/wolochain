"""Real five-key Ed25519 synthetic phase lineage tests; never production authority."""
from __future__ import annotations

from copy import deepcopy
from datetime import timedelta
from pathlib import Path
import json
import sys
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE / "scripts"))
sys.path.insert(0, str(HERE / "tests"))
import settlement_human_authority_verify as a
import settlement_maintenance_phase_review as gate
import test_settlement_human_authority_verify as fixture


class PhaseReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture.HumanSignatureTests.setUpClass.__func__(cls)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def sign(self, packet):
        return fixture.HumanSignatureTests.sign(self, packet)

    def packet(self, phase):
        return fixture.HumanSignatureTests.packet(self, phase)

    def phase_evidence(self, phase, *, capture=None, fence=None, restore=None,
                 previous=None, approval_flags=False):
        value = {
            "schema": gate.EVIDENCE_SCHEMA,
            "phase": phase, "state": gate.STATES[phase],
            "source_commit": self.expected["source_commit"],
            "scope_sha256": self.expected["scope"],
            "host_identity_sha256": self.expected["host"],
            "capture_manifest_sha256": gate.expected_sha(capture),
            "fence_receipt_sha256": gate.expected_sha(fence),
            "restore_receipt_sha256": gate.expected_sha(restore),
            "previous_review_sha256": gate.expected_sha(previous),
            "writers_and_external_signers_independently_checked": approval_flags,
            "complete_hd_de_census_independently_checked": approval_flags,
            "bank_solvent_independently_checked": approval_flags,
            "automatic_resume_authorized": False,
            "financial_release_authorized": False,
        }
        return a.canonical(value)

    def do_review(self, phase, *, capture=None, fence=None, restore=None,
                  previous=None, approval_flags=False, packet=None, evidence=None,
                  ledger=None, expected=None, now=None):
        evidence = evidence if evidence is not None else self.phase_evidence(
            phase, capture=capture, fence=fence, restore=restore,
            previous=previous, approval_flags=approval_flags)
        packet = deepcopy(packet) if packet is not None else self.packet(phase)
        packet["request"]["evidence_sha256"] = a.sha(evidence)
        # Signing a new evidence digest requires all five actual TEST signatures.
        packet = self.sign(packet) if packet is not None else packet
        return gate.review(
            packet, self.registry, self.regraw,
            ledger or {"schema": a.LEDGER_SCHEMA, "consumed": []},
            expected or self.expected, evidence, self.procedure,
            capture=capture, fence=fence, restore=restore,
            previous=previous, now=now or fixture.NOW)

    def sequence(self):
        capture = self.capture
        fence = self.fence
        live = self.do_review("live_capture")
        prior = a.canonical(live)
        offline = self.do_review("offline_verify", capture=capture, fence=fence,
                                 previous=prior)
        return capture, fence, prior, a.canonical(offline)

    def test_full_three_phase_reviews_cannot_authorize_operations(self):
        c, f, live, offline = self.sequence()
        result = self.do_review("resume", capture=c, fence=f,
                                restore=b'{"synthetic":"restored"}',
                                previous=offline, approval_flags=True)
        self.assertEqual(result["phase"], "resume")
        for flag in ("human_enrollment_independently_proven",
                     "nonce_atomically_consumed", "production_action_authorized",
                     "automatic_resume_authorized", "financial_release_authorized"):
            self.assertIs(result[flag], False)

    def test_capture_will_not_preapprove_recovery(self):
        with self.assertRaisesRegex(a.Refusal, "LIVE_CAPTURE_MAY_NOT_PRECERTIFY_RECOVERY"):
            self.do_review("live_capture", approval_flags=True)

    def test_offline_requires_real_distinct_parent_bytes(self):
        with self.assertRaises(a.Refusal):
            self.do_review("offline_verify", capture=self.capture, fence=self.fence)
        c,f,live,_ = self.sequence()
        with self.assertRaises(a.Refusal):
            self.do_review("offline_verify", capture=c, fence=f, previous=live+b" ")
        with self.assertRaises(a.Refusal):
            self.do_review("offline_verify", capture=b"mutated", fence=f, previous=live,
                           packet=self.packet("offline_verify"))

    def test_resume_refuses_missing_restore_or_signer_finance_evidence(self):
        c,f,_,offline = self.sequence()
        with self.assertRaises(a.Refusal):
            self.do_review("resume", capture=c, fence=f, previous=offline,
                           approval_flags=True)
        with self.assertRaisesRegex(a.Refusal, "RESUME_REVIEW_EVIDENCE_INCOMPLETE"):
            self.do_review("resume", capture=c, fence=f,
                           restore=b"sealed", previous=offline,
                           approval_flags=False)

    def test_resume_must_follow_separately_reviewed_offline_phase(self):
        c,f,live,_ = self.sequence()
        with self.assertRaisesRegex(a.Refusal, "PRIOR_PHASE_NOT_TRUSTED"):
            self.do_review("resume", capture=c, fence=f, restore=b"sealed",
                           previous=live, approval_flags=True)

    def test_tampered_parent_scope_or_capture_refused(self):
        c,f,_,offline = self.sequence()
        tampered = json.loads(offline)
        tampered["scope_sha256"] = "f"*64
        with self.assertRaisesRegex(a.Refusal, "PRIOR_PHASE_NOT_TRUSTED"):
            self.do_review("resume", capture=c, fence=f, restore=b"sealed",
                           previous=a.canonical(tampered), approval_flags=True)
        with self.assertRaises(a.Refusal):
            self.do_review("resume", capture=c+b"corrupt", fence=f,
                           restore=b"sealed", previous=offline, approval_flags=True)

    def test_evidence_cannot_claim_automatic_resume_or_financial_release(self):
        for key in ("automatic_resume_authorized", "financial_release_authorized"):
            value = json.loads(self.phase_evidence("live_capture"))
            value[key] = True
            with self.subTest(key=key), self.assertRaisesRegex(
                    a.Refusal, "FORBIDDEN_IMPLICIT_AUTHORITY"):
                self.do_review("live_capture", evidence=a.canonical(value))

    def test_ledger_replay_and_wrong_source_fail_at_crypto_boundary(self):
        with self.assertRaisesRegex(a.Refusal, "NONCE_REUSED_OR_INVALID"):
            self.do_review("live_capture",
                           ledger={"schema": a.LEDGER_SCHEMA, "consumed": ["1"*32]})
        with self.assertRaises(a.Refusal):
            self.do_review("live_capture", expected={**self.expected, "source": "e"*64})
        with self.assertRaises(a.Refusal):
            self.do_review("live_capture", now=fixture.NOW+timedelta(hours=1))

    def test_bad_human_signatures_never_reach_state_transition(self):
        ev=self.phase_evidence("live_capture")
        pkt=self.packet("live_capture")
        pkt["request"]["evidence_sha256"]=a.sha(ev)
        pkt=self.sign(pkt)
        pkt["approvals"][0]["signature_b64"]="X"*88
        with self.assertRaises(a.Refusal):
            gate.review(pkt,self.registry,self.regraw,
                        {"schema":a.LEDGER_SCHEMA,"consumed":[]},
                        self.expected,ev,self.procedure,now=fixture.NOW)

    def test_fail_closed_cli_does_not_call_financial_controller(self):
        with patch("settlement_maintenance_phase_review.human.read_file",
                   side_effect=OSError("private unavailable")):
            args=[]
            for key in ("registry","packet","nonce-ledger","evidence","procedure"):
                args += ["--"+key, "/tmp/absent"]
            for key in ("registry","source","scope","host"):
                args += ["--expected-"+key+"-sha256", self.expected[key]]
            args += ["--expected-source-commit", self.expected["source_commit"]]
            self.assertEqual(gate.main(args),2)


class ProductionCLIFailClosedTests(unittest.TestCase):
    def test_legacy_hash_only_cli_is_refused_before_lock_or_mutation(self):
        import test_settlement_financial_maintenance as existing
        controller = existing.MOD
        with patch.object(controller.os, "geteuid", return_value=0), \
             patch.object(controller, "fence", side_effect=AssertionError("fence called")) as f, \
             patch.object(controller, "backup", side_effect=AssertionError("backup called")) as b, \
             patch.object(controller, "restore_isolated", side_effect=AssertionError("restore called")) as rr, \
             patch.object(controller.os, "open", side_effect=AssertionError("lock opened")) as opened, \
             patch("builtins.print") as printed:
            for mode in ("fence", "backup", "restore-isolated"):
                code = controller.main(["--mode", mode,
                    "--permit", "/root/forged-hash-ref-v1.json",
                    "--fence-receipt", "/root/forged-fence.json",
                    "--output", "/root/not-a-real-backup"])
                self.assertEqual(code, 2, mode)
                self.assertEqual(json.loads(printed.call_args.args[0])["reason"],
                                 "FIVE_HUMAN_CONTROLLER_NOT_INTEGRATED")
            for call in (f,b,rr,opened):
                call.assert_not_called()


if __name__ == "__main__":
    unittest.main()

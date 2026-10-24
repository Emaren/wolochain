"""Actual finance maintenance CLI admission tests; synthetic keys, no VPS access."""
from __future__ import annotations

import base64
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
sys.path.insert(0,str(ROOT/"tests"))

import settlement_financial_maintenance as controller
import settlement_financial_controller_binding as binding
import settlement_maintenance_phase_review as phase
import settlement_human_authority_verify as human
import test_settlement_human_authority_verify as fixture


class SignedControllerAdmissionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture.HumanSignatureTests.setUpClass.__func__(cls)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def sign(self,packet):
        return fixture.HumanSignatureTests.sign(self,packet)

    def make(self,*,writer_incomplete=False):
        host=b"CI-only independently assigned host identity"
        drift=b"CI-only signed source drift disposition"
        inventory={"schema":"wolo.financial-writer-independent-coverage.v1","writers":{}}
        keys={"hd_web_api","de_web_api","seven_timer_service_pairs","postgres_dba",
              "manual_sql_and_ssh","cron_and_user_systemd","ci_and_deployment",
              "settlement_8092_8093_bearers","offhost_wallet_and_chain_signers",
              "auxiliary_settlement_and_indexers","hasura_secondary_targets",
              "legacy_and_de_manual_executors"}
        for k in keys:
            inventory["writers"][k]={"owner_id":"independent_owner_"+k,
                "independent_reviewer_id":"separate_reviewer_"+k,
                "excluded_during_window":not(writer_incomplete and k=="postgres_dba"),
                "evidence_sha256":"9"*64}
        inventory_raw=human.canonical(inventory)
        output=controller.BACKUPS/"synthetic-CI-only"
        fence=Path("/etc/wolochain-financial-maintenance/authority/fence.json")
        procedure={
            "schema":binding.PROCEDURE_SCHEMA,"mode":"capture",
            "fence_receipt_path":str(fence),"output_path":str(output),
            "legacy_permit_core_sha256":None,
            "source_drift_disposition_sha256":human.sha(drift),
            "writer_inventory_sha256":human.sha(inventory_raw),
        }
        pkt=fixture.HumanSignatureTests.packet(self)
        req=pkt["request"]
        req["tool_sha256"]=self.expected["source"]
        req["scope_sha256"]=self.expected["scope"]
        req["host_identity_sha256"]=human.sha(host)
        req["source_commit"]=self.expected["source_commit"]
        req["max_total_bytes"]=4<<30
        evidence={
            "schema":phase.EVIDENCE_SCHEMA,
            "phase":"live_capture","state":phase.STATES["live_capture"],
            "source_commit":req["source_commit"],
            "scope_sha256":req["scope_sha256"],
            "host_identity_sha256":req["host_identity_sha256"],
            "capture_manifest_sha256":None,"fence_receipt_sha256":None,
            "restore_receipt_sha256":None,"previous_review_sha256":None,
            "writers_and_external_signers_independently_checked":True,
            "complete_hd_de_census_independently_checked":False,
            "bank_solvent_independently_checked":False,
            "automatic_resume_authorized":False,
            "financial_release_authorized":False,
        }
        evidence_raw=human.canonical(evidence)
        permit={
            "schema":controller.SCHEMA,
            "action":"fence-backup-isolated-restore",
            "scope_sha256":req["scope_sha256"],
            "tool_sha256":req["tool_sha256"],
            "packet_sha256":"0"*64,
            "procedure_sha256":"0"*64,
            "not_before":req["not_before"],
            "expires_at":req["expires_at"],
            "approval_refs":{},
            "attestations":dict.fromkeys(controller.ATTESTATIONS,True),
            "max_total_bytes":req["max_total_bytes"],
            "databases":{
               "hd":{"env_path":"/etc/test-hd","env_sha256":"a"*64,
                     "database_sha256":"b"*64,"financial_tables":["test"],
                     "postgres_major":16},
               "de":{"env_path":"/etc/test-de","env_sha256":"c"*64,
                     "database_sha256":"d"*64,"financial_tables":["test"],
                     "postgres_major":16},
            },
            "restore_image":"postgres@sha256:"+"e"*64,
        }
        procedure["legacy_permit_core_sha256"]=human.sha(human.canonical(binding.signed_core(permit)))
        procedure_raw=human.canonical(procedure)
        req["procedure_sha256"]=human.sha(procedure_raw)
        req["evidence_sha256"]=human.sha(evidence_raw)
        pkt=self.sign(pkt)
        permit["packet_sha256"]=human.sha(human.canonical(pkt))
        permit["procedure_sha256"]=human.sha(procedure_raw)
        permit["approval_refs"]={
            a["role"]:{"identity":a["person_id"],
                "approval_sha256":human.sha(base64.b64decode(a["signature_b64"]))}
            for a in pkt["approvals"]}
        ledger=human.canonical({"schema":human.LEDGER_SCHEMA,"consumed":[]})
        files={
            "registry":self.regraw,"packet":human.canonical(pkt),
            "nonce-ledger":ledger,"evidence":evidence_raw,
            "procedure":procedure_raw,"host-identity":host,
            "source-drift-disposition":drift,
            "independent-writer-coverage.json":inventory_raw,
        }
        args=SimpleNamespace(
            registry=Path("/root/authority/registry"),
            packet=Path("/root/authority/packet"),
            nonce_ledger=Path("/root/authority/nonce-ledger"),
            evidence=Path("/root/authority/evidence"),
            procedure=Path("/root/authority/procedure"),
            host_identity=Path("/root/authority/host-identity"),
            source_drift_disposition=Path("/root/authority/source-drift-disposition"),
            permit=Path("/root/authority/permit"),
            fence_receipt=fence, output=output, capture_manifest=None,
            previous_review=None,restore_receipt=None)
        anchors={"registry_sha256":human.sha(self.regraw),
            "host_identity_sha256":human.sha(host),
            "source_commit":self.expected["source_commit"],
            "source_drift_disposition_sha256":human.sha(drift),
            "revoked_key_ids":()}
        return args,anchors,files,permit,pkt

    def admit(self,*,broken=None,writer_incomplete=False,change=None,witness=None,now=None):
        args,anchors,files,permit,pkt=self.make(writer_incomplete=writer_incomplete)
        if change:change(args,anchors,files,permit,pkt)
        with tempfile.TemporaryDirectory() as root:
            nonce_dir=Path(root)/"nonces"
            nonce_dir.mkdir(mode=0o700)
            witness_calls=[]
            def fake_witness(nonce,sha,mode,source,scope):
                witness_calls.append(mode)
                return {"fresh_consumption_confirmed":True,"nonce":nonce,
                        "signed_packet_sha256":sha}
            def read(path,root):
                return files[Path(path).name]
            def private_json(path):
                self.assertEqual(path,args.permit)
                return permit,human.sha(human.canonical(permit))
            with patch.object(binding,"exact_private",side_effect=read), \
                 patch.object(controller,"private_json",side_effect=private_json), \
                 patch.object(controller,"validate_permit",return_value=permit):
                func=witness if witness is not None else fake_witness
                result=binding.authenticate_and_reserve(
                   args,mode="capture",source_tool_sha256=self.expected["source"],
                   scope_sha256=self.expected["scope"],anchors=anchors,
                   root=Path("/root/authority"),nonce_root=nonce_dir,
                   independent_consumer=func,now=now or fixture.NOW)
                return result,len(list(nonce_dir.glob("nonce-*"))),witness_calls

    def test_valid_synthetic_five_signatures_burns_nonce_before_controller(self):
        request,n,calls=self.admit()
        self.assertEqual(request["phase"],"live_capture")
        self.assertEqual(n,1)
        self.assertEqual(calls,["capture"])

    def test_missing_enrollment_fails_before_disk_or_signature_checks(self):
        args,anchors,files,permit,pkt=self.make()
        anchors["registry_sha256"]=None
        with patch.object(binding,"exact_private",side_effect=AssertionError("files read")):
            with self.assertRaisesRegex(human.Refusal,"INDEPENDENT_TRUST"):
                binding.authenticate_and_reserve(args,mode="capture",
                    source_tool_sha256=self.expected["source"],
                    scope_sha256=self.expected["scope"],anchors=anchors,
                    root=Path("/root/authority"),nonce_root=Path("/tmp/uncreated"))

    def test_revoked_key_fails_even_if_signature_would_verify(self):
        def change(args,anchors,files,permit,pkt):
            anchors["revoked_key_ids"]=(self.registry["principals"][0]["key_id"],)
        with self.assertRaisesRegex(human.Refusal,"REVOKED_HUMAN_APPROVER"):
            self.admit(change=change)

    def test_incomplete_dba_coverage_blocks_before_remote_witness(self):
        with self.assertRaisesRegex(human.Refusal,"FINANCIAL_WRITER_OWNER_UNATTESTED"):
            self.admit(writer_incomplete=True)

    def test_forged_signature_blocks_before_remote_witness(self):
        def change(args,anchors,files,permit,pkt):
            p=human.parse_json(files["packet"])
            p["approvals"][0]["signature_b64"]="A"*88
            files["packet"]=human.canonical(p)
        with self.assertRaises(human.Refusal):
            self.admit(change=change)

    def test_stale_window_blocks_before_remote_witness(self):
        with self.assertRaisesRegex(human.Refusal,"EXPIRED"):
            self.admit(now=fixture.NOW+__import__("datetime").timedelta(hours=1))

    def test_source_drift_disposition_anchor_mismatch_blocks(self):
        def change(args,anchors,files,permit,pkt):
            anchors["source_drift_disposition_sha256"]="f"*64
        with self.assertRaisesRegex(human.Refusal,"SOURCE_HOST_TRUST"):
            self.admit(change=change)

    def test_default_remote_witness_refuses_without_local_nonce_burn(self):
        with self.assertRaisesRegex(human.Refusal,"INDEPENDENT_MONOTONIC_NONCE"):
            self.admit(witness=binding.independently_consume_remote_nonce)

    def test_old_v1_modes_and_unauthorized_resume_stay_blocked(self):
        with tempfile.TemporaryDirectory() as temp, \
             patch.object(controller,"LOCK",Path(temp)/"lock"), \
             patch.object(controller.os,"geteuid",return_value=0), \
             patch.object(controller,"fence",side_effect=AssertionError("fence ran")) as f, \
             patch.object(controller,"backup",side_effect=AssertionError("backup ran")) as b, \
             patch.object(controller,"restore_isolated",
                          side_effect=AssertionError("restore ran")) as rr, \
             patch.object(binding,"independently_consume_remote_nonce",
                          side_effect=AssertionError("remote invoked")):
            for mode in ("fence","backup","restore-isolated","capture","offline-restore","resume"):
                with patch("builtins.print") as printed:
                    result=controller.main(["--mode",mode,
                       "--fence-receipt","/root/unavailable-receipt",
                       "--output","/root/unavailable-output"])
                self.assertEqual(result,2,mode)
            f.assert_not_called();b.assert_not_called();rr.assert_not_called()


if __name__=="__main__":
    unittest.main()

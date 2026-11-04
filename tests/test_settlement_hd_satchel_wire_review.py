"""Adversarial HD-only/Wolo isolated 8094 source-wire admission tests.

Synthetic fixture text is a deliberate *shape* test, not custody evidence.
"""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
SCRIPT=ROOT/"scripts"/"settlement_hd_satchel_wire_review.py"
spec=importlib.util.spec_from_file_location("wire_review",SCRIPT)
wire=importlib.util.module_from_spec(spec)
spec.loader.exec_module(wire)
HEAD="a"*40
HD="b"*40

def source_fixture():
    return {
        name: ("\n".join(needles.values())+"\n").encode()
        for name,needles in wire.SURFACES.items()
    }

class HDWireReviewTests(unittest.TestCase):
    def setUp(self):
        self.files=source_fixture()
    def result(self):
        return wire.inspect(HEAD,HD,self.files)
    def hold(self,why):
        with self.assertRaisesRegex(wire.ReviewHold,"^"+why+"$"):
            self.result()

    def test_match_is_only_source_shape_never_runtime_money_authority(self):
        r=self.result()
        self.assertEqual(r["status"],"HOLD")
        self.assertTrue(r["static_wire_surface_matches"])
        self.assertFalse(r["financial_release_authorized"])
        self.assertFalse(r["dedicated_8094_runtime_custody_proven"])
        self.assertFalse(r["historical_consensus_trust_authenticated"])
        self.assertFalse(r["same_height_solvency_certified"])
        self.assertFalse(r["hd_funded_bridge_enabled"])
        self.assertFalse(r["legacy_money_mutated"])
        self.assertEqual(len(r["source_file_sha256"]),5)
        self.assertNotIn("private_key",json.dumps(r).lower())

    def test_health_endpoint_requires_actual_available_grant(self):
        self.files["wolo_http"]=self.files["wolo_http"].replace(
            b'if i.Accepting && capability.grant != nil', b'if i.Accepting')
        r=self.result()
        self.assertFalse(r["static_wire_surface_matches"])
        self.assertIn("wolo_http.available_requires_grant",r["source_shape_gaps"])

    def test_disabled_financial_bridge_must_not_be_flipped_by_env(self):
        self.files["hd_bridge"]=self.files["hd_bridge"].replace(
            b'SATCHEL_FINANCIAL_BRIDGE_READY = false as const',
            b'SATCHEL_FINANCIAL_BRIDGE_READY = true as const')
        r=self.result()
        self.assertFalse(r["static_wire_surface_matches"])
        self.assertIn("hd_bridge.money_fail_closed",r["source_shape_gaps"])

    def test_signer_on_wrong_port_never_passes(self):
        self.files["wolo_signer"]=self.files["wolo_signer"].replace(b"8094",b"8092")
        r=self.result()
        self.assertIn("wolo_signer.isolated_custody_service",r["source_shape_gaps"])

    def test_mismatched_protocol_version_detected(self):
        self.files["hd_client"]=self.files["hd_client"].replace(b"/satchel/v2/one-shot",b"/satchel/v1/one-shot")
        r=self.result()
        self.assertIn("hd_client.reserved_signed_one_shot",r["source_shape_gaps"])
        self.files=source_fixture()
        self.files["wolo_http"]=self.files["wolo_http"].replace(b'"execution_protocol": 2',b'"execution_protocol": 1')
        self.assertIn("wolo_http.protocol_v2",self.result()["source_shape_gaps"])

    def test_missing_complete_global_hd_liabilities_cannot_be_hidden(self):
        self.files["hd_admission"]=self.files["hd_admission"].replace(
            b"aggregateLiabilityUwolo",b"ownerOnlyLiabilityUwolo")
        self.assertIn("hd_admission.all_owner_liabilities",self.result()["source_shape_gaps"])

    def test_nonce_or_credential_input_cannot_be_part_of_source_contract(self):
        self.files["hd_client"]=b""
        self.hold("SOURCE_BYTES_UNAVAILABLE")
        self.files=source_fixture()
        self.files["hd_client"]=b"\xff\xfe"
        self.hold("SOURCE_BYTES_NOT_UTF8")

    def test_exact_five_source_surfaces_required(self):
        del self.files["hd_client"]
        self.hold("MISSING_SOURCE_SURFACE")
        self.files=source_fixture()
        self.files["hidden_de_sources"]=b"not part of HD-only mission"
        self.hold("MISSING_SOURCE_SURFACE")

    def test_git_sha_strict_and_does_not_accept_alternative_chain(self):
        with self.assertRaisesRegex(wire.ReviewHold,"^EXACT_SOURCE_SHA_REQUIRED$"):
            wire.inspect("not a Wolo SHA",HD,self.files)
        with self.assertRaisesRegex(wire.ReviewHold,"^EXACT_SOURCE_SHA_REQUIRED$"):
            wire.inspect(HEAD,"",self.files)

    def test_read_bounded_does_not_follow_source_symlinks(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            p=root/"lib"/"readonly.ts"
            p.parent.mkdir()
            p.write_text("fixture")
            self.assertEqual(wire.read_bounded(root,"lib/readonly.ts"),b"fixture")
            p.unlink()
            p.symlink_to("/etc/passwd")
            self.assertRaisesRegex(wire.ReviewHold,"^SOURCE_PATH_SYMLINK$",
                                   wire.read_bounded,root,"lib/readonly.ts")

    def test_cli_with_nonexistent_exact_source_exits_stop_not_go(self):
        with tempfile.TemporaryDirectory() as d:
            with patch.object(wire,"print",create=True) as printer:
                code=wire.main(["--hd-root",d,"--wolo-root",d,
                                "--expect-wolo-sha",HEAD,"--expect-hd-sha",HD])
            self.assertEqual(code,2)
            result=json.loads(printer.call_args.args[0])
            self.assertFalse(result["financial_release_authorized"])

if __name__=="__main__":
    unittest.main()

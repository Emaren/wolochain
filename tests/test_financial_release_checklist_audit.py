"""Offline adversarial integrity checks. Never inspect running signers or mainnet."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "financial_release_checklist_audit.py"
spec = importlib.util.spec_from_file_location("financial_release_checklist_audit", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class FinancialChecklistAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.folder = self.root / module.EVIDENCE_DIR
        self.folder.mkdir(parents=True)
        self.name = "observed.json"
        self.raw = b'{"observation":"not-independent"}\n'
        (self.folder / self.name).write_bytes(self.raw)
        self.checklist = {
            "schema": module.SCHEMA, "overall_status": "HOLD",
            "exact_historical_candidate": {"revision": "b" * 40, "binary_sha256": "c" * 64},
            "live_settlement_revision": "a" * 40,
            "controls": {name: {"status": "BLOCKED", "unknowns": ["unverified"],
                                 "evidence": [self.name]} for name in module.CONTROLS},
            "evidence": {self.name: {"path": module.EVIDENCE_DIR + "/" + self.name,
                                    "sha256": hashlib.sha256(self.raw).hexdigest()}},
            "global_liability_upper_bound_uwolo": None,
            "global_liability_bound": "UNBOUNDED_NOT_PROVEN",
            "custody_capability": "UNAVAILABLE", "chain_evidence": "NONCREDITING",
            "website": {"status": "CERTIFIED_INDEPENDENT_APP_RELEASE"},
        }
        for flag in module.FALSE_FLAGS:
            self.checklist[flag] = False
        self.save()

    def save(self):
        target = self.root / module.INDEX
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(self.checklist), encoding="utf-8")

    def assert_stop(self, reason, expected=None):
        with self.assertRaisesRegex(module.AuditFailure, "^" + reason + "$"):
            module.audit(self.root, expected)

    def test_validated_hold_still_denies_all_authority(self):
        result = module.audit(self.root, "b" * 40)
        self.assertEqual(result["result"], "VALIDATED_HOLD_ONLY")
        self.assertFalse(result["deployment_permitted"])
        self.assertFalse(result["live_attestation_performed"])
        self.assertFalse(result["financial_release_authorized"])
        self.assertIsNone(result["global_liability_bound"])

    def test_current_federated_target_rejects_historical_candidate(self):
        self.assert_stop("HISTORICAL_CANDIDATE_NOT_FEDERATED_BASELINE", "3" * 40)

    def test_removed_hold_refused(self):
        self.checklist["overall_status"] = "READY"
        self.save()
        self.assert_stop("RELEASE_HOLD_REMOVED")

    def test_claimed_live_authority_refused(self):
        self.checklist["financial_release_authorized"] = True
        self.save()
        self.assert_stop("RELEASE_AUTHORITY_NOT_FALSE")

    def test_erased_uncertainty_refused(self):
        self.checklist["controls"]["bank_solvent_and_independently_checked"]["unknowns"] = []
        self.save()
        self.assert_stop("CONTROL_UNCERTAINTY_ERASED")

    def test_early_control_promotion_refused(self):
        self.checklist["controls"]["hd_de_producers_isolated"]["status"] = "PASS"
        self.save()
        self.assert_stop("UNATTESTED_CONTROL_PROMOTED")

    def test_extra_or_missing_control_refused(self):
        del self.checklist["controls"]["claim_889_liability_preserved_and_release_reviewed"]
        self.save()
        self.assert_stop("SIX_CONTROL_SET_MISMATCH")

    def test_tampered_evidence_refused(self):
        (self.folder / self.name).write_bytes(b"changed")
        self.assert_stop("EVIDENCE_DIGEST_MISMATCH")

    def test_evidence_symlink_refused(self):
        (self.folder / self.name).unlink()
        (self.folder / self.name).symlink_to("/etc/hosts")
        self.assert_stop("SYMLINK_EVIDENCE")

    def test_path_traversal_refused(self):
        self.checklist["evidence"][self.name]["path"] = "../outside"
        self.save()
        self.assert_stop("EVIDENCE_PATH_MISMATCH")

    def test_duplicate_json_keys_refused(self):
        target = self.root / module.INDEX
        target.write_bytes(b'{"schema":"a","schema":"b"}')
        self.assert_stop("DUPLICATE_JSON_KEY")

    def test_global_liability_not_fabricated(self):
        self.checklist["global_liability_upper_bound_uwolo"] = "1"
        self.save()
        self.assert_stop("GLOBAL_LIABILITY_UNPROVEN")

    def test_repository_fixture_is_current_held_evidence(self):
        repo_root = Path(__file__).resolve().parents[1]
        result = module.audit(repo_root)
        self.assertEqual(result["result"], "VALIDATED_HOLD_ONLY")
        self.assertEqual(result["control_count"], 6)
        self.assertFalse(result["deployment_permitted"])


if __name__ == "__main__":
    unittest.main()

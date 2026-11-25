"""Synthetic, NONAUTHORIZING website evidence references, never live attestations.

JSON Schema checks structure only. Authentication, freshness, equalities and
durable replay prevention belong to the future app controller.
"""
from copy import deepcopy
import json
from pathlib import Path
import unittest

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "docs/settlement-contracts/wolo-website-hold-evidence-v1.schema.json"


def fixture():
    attempt = {
        "repository": "Emaren/app-prodn", "attempt_id": "fixture-attempt-1",
        "challenge": "1" * 64, "deployed_commit": "2" * 40,
        "candidate_commit": "3" * 40, "candidate_artifact_sha256": "4" * 64,
        "app_controller_commit": "5" * 40,
        "issued_at_utc": "2026-10-18T14:30:00Z", "expires_at_utc": "2026-10-18T14:35:00Z",
    }
    process = {
        "pid": 1012, "executable_path": "/usr/local/bin/wolochaind-mainnet",
        "binary_sha256": "040126a2884946caf1651a50b7d8115c5a6fb2d5aa94fcbbe150694602d451a5",
        "vcs_revision": "78c25985420ee41a6678c42fab8ea8d6c3b1b519", "vcs_modified": False,
    }
    observation = {
        "attempt_id": attempt["attempt_id"], "challenge": attempt["challenge"],
        "candidate_commit": attempt["candidate_commit"],
        "started_at_utc": "2026-10-18T14:30:01Z", "finished_at_utc": "2026-10-18T14:30:02Z",
        "source_authority_receipt_sha256": "6" * 64,
        "source_authority_status": "BLOCKED",
        "source_authority_blockers": ["PROTECTED_TWO_SERVICE_CODE_CUTOVER_REQUIRED",
                                      "SOURCE_TRANSITION_REQUIRED_AFTER_VERIFIED_CODE_CUTOVER"],
        "checkout_revision": process["vcs_revision"], "source_tree_index_sha256": "7" * 64,
        "runtime_configuration_sha256": "8" * 64, "hold_record_sha256": "9" * 64,
        "primary": process, "founder": {**process, "pid": 1010},
        "consensus": {**process, "pid": 1009,
                      "executable_path": "/usr/local/bin/wolochaind-mainnet-node-prewartrophy",
                      "binary_sha256": "4b77f622191db7550cb87cafb8f1886a0aadebee3eb6565f9f90036f809e61d3",
                      "vcs_revision": "d3bd62414a047a492a3814b7d3baa2717d64db2e", "vcs_modified": True},
        "source_runtime_aligned": False, "custody_capability": "UNAVAILABLE",
        "chain_evidence": "NONCREDITING", "financial_reconciliation_proven": False,
        "financial_release_authorized": False, "custody_authorized": False,
        "claim_889_resolved": False, "production_mutated": False,
    }
    return {
        "schema": "aoe2war.wolo.website-hold-evidence.v1", "release_attempt": attempt,
        "external_authority": {
            "reviewed_baseline_sha256": "a" * 64, "review_receipt_sha256": "b" * 64,
            "observer_source_commit": "c" * 40, "observer_sha256": "d" * 64,
            "host_identity": "fixture-host", "channel_anchor_sha256": "e" * 64,
            "channel_receipt_sha256": "f" * 64, "verification_required": "EXTERNAL_APP_CONTROLLER",
        },
        "before": deepcopy(observation), "after": deepcopy(observation),
        "app_scope_admission": {
            **{k: attempt[k] for k in ("repository", "attempt_id", "challenge", "deployed_commit",
                                       "candidate_commit", "candidate_artifact_sha256")},
            "policy_sha256": "a" * 64, "receipt_sha256": "b" * 64,
            "verification_required": "EXTERNAL_APP_CONTROLLER",
        },
        "source_authority_status": "BLOCKED", "financial_hold": "HOLD",
        "app_deployment_authorized": False, "financial_release_authorized": False,
        "custody_authorized": False, "claim_889_resolved": False, "production_mutated": False,
    }


class WebsiteHoldEvidenceContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = json.loads(SCHEMA.read_text())
        Draft202012Validator.check_schema(cls.schema)
        cls.validator = Draft202012Validator(cls.schema, format_checker=FormatChecker())

    def rejected(self, document):
        self.assertFalse(self.validator.is_valid(document))

    def test_unchanged_old_runtime_remains_structurally_blocked_and_nonauthorizing(self):
        document = fixture()
        self.validator.validate(document)
        self.assertEqual(document["source_authority_status"], "BLOCKED")
        self.assertFalse(document["app_deployment_authorized"])

    def test_cannot_elevate_any_false_authority_or_use_integer_zero(self):
        for section in (None, "before", "after"):
            for key, value in (fixture() if section is None else fixture()[section]).items():
                if value is False:
                    for forged in (True, 0, "false", None):
                        with self.subTest(section=section, key=key, forged=forged):
                            doc = fixture()
                            (doc if section is None else doc[section])[key] = forged
                            self.rejected(doc)

    def test_missing_identity_scope_baseline_or_channel_reference_refuses(self):
        for section in (None, "release_attempt", "external_authority", "before", "after", "app_scope_admission"):
            keys = list(fixture() if section is None else fixture()[section])
            for key in keys:
                with self.subTest(section=section, key=key):
                    doc = fixture()
                    del (doc if section is None else doc[section])[key]
                    self.rejected(doc)

    def test_unknown_fields_and_caller_certification_refuse_at_every_level(self):
        for path in ((), ("external_authority",), ("release_attempt",), ("app_scope_admission",),
                     ("before",), ("after",), ("before", "primary"), ("after", "consensus")):
            with self.subTest(path=path):
                doc = fixture(); target = doc
                for name in path:
                    target = target[name]
                target["certified_by_environment"] = True
                self.rejected(doc)

    def test_removed_hold_or_claimed_parity_credit_and_custody_refuse(self):
        for path, value in ((("financial_hold",), "CLEAR"), (("source_authority_status",), "PASS"),
                            (("before", "source_authority_blockers"), []),
                            (("after", "custody_capability"), "AVAILABLE"),
                            (("after", "chain_evidence"), "CREDITING")):
            doc = fixture(); target = doc
            for name in path[:-1]:
                target = target[name]
            target[path[-1]] = value
            self.rejected(doc)

    def test_invalid_hashes_process_identities_and_utc_refuse(self):
        for invalid in ("0" * 64, "f" * 63, "F" * 64, "f" * 64 + "\n"):
            doc = fixture(); doc["external_authority"]["reviewed_baseline_sha256"] = invalid
            self.rejected(doc)
        for invalid in (True, 0, -1, "1012"):
            doc = fixture(); doc["after"]["primary"]["pid"] = invalid
            self.rejected(doc)
        for invalid in ("2026-99-18T14:30:00Z", "2026-10-18T14:30:00+00:00", "not-a-dateZ"):
            doc = fixture(); doc["release_attempt"]["issued_at_utc"] = invalid
            self.rejected(doc)

    def test_schema_validity_does_not_claim_freshness_authentication_or_equality(self):
        # Deliberately structurally valid, semantically inadmissible references.
        # The app controller MUST reject them with independently trusted inputs.
        doc = fixture()
        doc["after"]["candidate_commit"] = "f" * 40
        doc["after"]["primary"]["pid"] += 1
        doc["release_attempt"]["expires_at_utc"] = "2000-01-01T00:00:00Z"
        self.validator.validate(doc)
        self.assertFalse(doc["app_deployment_authorized"])


if __name__ == "__main__":
    unittest.main()

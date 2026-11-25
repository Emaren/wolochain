#!/usr/bin/env python3
"""Regression contracts: a maintenance-planning report can never grant spending authority."""
from __future__ import annotations

from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
MODULE = SCRIPTS / "settlement_maintenance_board.py"
SPEC = importlib.util.spec_from_file_location("settlement_maintenance_board", MODULE)
assert SPEC is not None and SPEC.loader is not None
BOARD = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = BOARD
SPEC.loader.exec_module(BOARD)

NOW = datetime(2026, 10, 20, 3, 0, tzinfo=timezone.utc)
SHA = "a" * 64


def packet():
    return {
        "schema": BOARD.SCHEMA,
        "overall_status": "HOLD",
        "financial_release_authorized": False,
        "global_liability_upper_bound_uwolo": None,
        "exact_historical_candidate": {"revision": "b" * 40},
        "live_settlement_revision": "7" * 40,
        "controls": {
            key: {"status": "UNKNOWN" if key == "bank_solvent_and_independently_checked" else "BLOCKED",
                  "unknowns": ["independent live attestation missing"]}
            for key in BOARD.CONTROLS
        },
    }


def triage():
    return {
        "schema": BOARD.TRIAGE_SCHEMA,
        "mode": "READ_ONLY_NONAUTHORIZING", "status": "HOLD",
        "producerIsolationProven": False, "financialReleaseAuthorized": False,
        "productionMutated": False, "runtimeFresh": True,
        "counts": {"unitsObserved": 2, "activeObserved": 1, "unknownOwnerUnits": 1},
        "unitOwnerReview": [
            {"unit": "aoe2hdbets-web.service", "owner": "HD_OR_SHARED",
             "reviewStatus": "OWNER_REVIEW_REQUIRED", "runtimeSignerProof": "UNKNOWN",
             "activeObserved": True, "configuredFinancialKeyNames": ["SECRET_PASSWORD", "WOLO_MNEMONIC"]},
            {"unit": "undocumented-signer.timer", "owner": "UNKNOWN_OWNER",
             "reviewStatus": "OWNER_REVIEW_REQUIRED", "runtimeSignerProof": "UNKNOWN",
             "activeObserved": False},
        ],
    }


class FinancialMaintenanceBoardTests(unittest.TestCase):
    def summarize(self, source=None, triage_packet=None):
        return BOARD.summarize(source if source is not None else packet(), triage_packet,
                               observed_at=NOW, checklist_sha256=SHA)

    def test_historical_packet_remains_fully_held_even_with_empty_player_activity(self):
        report = self.summarize()
        self.assertEqual(report["finance"]["state"], "HOLD")
        self.assertEqual(len(report["finance"]["controls"]), 6)
        self.assertFalse(report["finance"]["globalLiabilityKnown"])
        self.assertFalse(report["canIssueFinancialCutoverPermit"])
        self.assertFalse(report["financialReleaseAuthorized"])
        self.assertFalse(report["satchelCustodyAuthorized"])
        self.assertFalse(report["websiteReleaseAuthorized"])
        self.assertIsNone(report["producers"]["unitsObserved"])

    def test_producer_triage_reports_only_public_unit_names_and_review_categories(self):
        report = self.summarize(triage_packet=triage())
        self.assertEqual(report["producers"]["unitsObserved"], 2)
        self.assertEqual(report["producers"]["activeObserved"], 1)
        self.assertEqual(report["producers"]["unknownOwnerUnits"], 1)
        self.assertFalse(report["producers"]["fresh"])
        self.assertTrue(report["producers"]["triageReportedFreshAtCreation"])
        self.assertFalse(report["financialProducersFenced"])
        self.assertFalse(report["canIssueFinancialCutoverPermit"])
        text = json.dumps(report)
        for secret in ("SECRET_PASSWORD", "WOLO_MNEMONIC", "configuredFinancialKeyNames"):
            self.assertNotIn(secret, text)

    def test_forged_claim_of_solvency_or_absent_controls_never_passes(self):
        for field, replacement in (("overall_status", "READY"),
                                   ("financial_release_authorized", True),
                                   ("global_liability_upper_bound_uwolo", 0)):
            c = packet()
            c[field] = replacement
            with self.subTest(field=field), self.assertRaises(BOARD.BoardFailure):
                self.summarize(c)
        c = packet()
        del c["controls"]["bank_solvent_and_independently_checked"]
        with self.assertRaises(BOARD.BoardFailure):
            self.summarize(c)
        c = packet()
        c["controls"]["bank_solvent_and_independently_checked"]["status"] = "PASS"
        with self.assertRaises(BOARD.BoardFailure):
            self.summarize(c)
        c = packet()
        c["controls"]["hd_de_producers_isolated"]["unknowns"] = []
        with self.assertRaises(BOARD.BoardFailure):
            self.summarize(c)

    def test_missing_false_flags_and_role_impersonation_denied(self):
        for field in ("producerIsolationProven", "financialReleaseAuthorized", "productionMutated"):
            p = triage()
            del p[field]
            with self.assertRaises(BOARD.BoardFailure):
                self.summarize(triage_packet=p)
            p = triage()
            p[field] = True
            with self.assertRaises(BOARD.BoardFailure):
                self.summarize(triage_packet=p)
        p = triage()
        p["unitOwnerReview"][0]["reviewStatus"] = "OWNER_APPROVED"
        with self.assertRaises(BOARD.BoardFailure):
            self.summarize(triage_packet=p)

    def test_inventory_duplicates_traversal_and_inaccurate_counts_denied(self):
        for change in ("duplicate", "traversal", "inaccurate", "fakebool"):
            p = triage()
            if change == "duplicate":
                p["unitOwnerReview"][1]["unit"] = "aoe2hdbets-web.service"
            if change == "traversal":
                p["unitOwnerReview"][1]["unit"] = "../../etc/passwd"
            if change == "inaccurate":
                p["counts"]["activeObserved"] = 0
            if change == "fakebool":
                p["counts"]["unitsObserved"] = True
            with self.subTest(change=change), self.assertRaises(BOARD.BoardFailure):
                self.summarize(triage_packet=p)

    def test_untrusted_packet_must_not_become_a_reconciliation_receipt(self):
        p = triage()
        del p["unitOwnerReview"][0]["activeObserved"]
        with self.assertRaises(BOARD.BoardFailure):
            self.summarize(triage_packet=p)
        p = triage()
        p["unitOwnerReview"][0]["runtimeSignerProof"] = "CERTIFIED"
        with self.assertRaises(BOARD.BoardFailure):
            self.summarize(triage_packet=p)
        for candidate in ("NOHOLD", "UNTRUSTED"):
            p = triage()
            p["status"] = candidate
            with self.assertRaises(BOARD.BoardFailure):
                self.summarize(triage_packet=p)

    def test_cli_incomplete_path_exits_stop_without_filesystem_mutation(self):
        with tempfile.TemporaryDirectory() as td:
            code = BOARD.main(["--root", td])
        self.assertEqual(code, 2)

    def test_provenance_digest_and_timestamp_required(self):
        with self.assertRaises(BOARD.BoardFailure):
            BOARD.summarize(packet(), None, checklist_sha256="f" * 40)
        with self.assertRaises(BOARD.BoardFailure):
            BOARD.summarize(packet(), None, observed_at=datetime(2026,10,20),
                            checklist_sha256=SHA)


if __name__ == "__main__":
    unittest.main()

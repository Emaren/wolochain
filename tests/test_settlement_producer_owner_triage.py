from __future__ import annotations

from datetime import datetime, timezone, timedelta
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts/settlement_producer_owner_triage.py"
SPEC = importlib.util.spec_from_file_location("settlement_producer_owner_triage", MODULE_PATH)
assert SPEC and SPEC.loader
TRIAGE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = TRIAGE
SPEC.loader.exec_module(TRIAGE)
NOW = datetime(2026, 10, 19, 23, 30, tzinfo=timezone.utc)


def source_packets():
    hd = {
        "schema": TRIAGE.HD_SCHEMA, "classification": "SOURCE_OBSERVATION_ONLY",
        "known_source_edges_intact": True,
        "observations": [{"status": "SOURCE_OBSERVED", "line": 11}],
        "all_financial_producers_isolated": False, "safe_to_deploy": False,
    }
    de = {
        "schema": TRIAGE.DE_SCHEMA, "mode": "READ_ONLY_NONAUTHORIZING",
        "known_de_source_edges_intact": True,
        "local_source": {"state": "LOCAL_CLEAN_GIT_ONLY", "head": "a" * 40},
        "observations": [{"status": "SOURCE_OBSERVED", "line": 5}],
        "financial_producers_fenced": False,
    }
    return hd, de


def runtime(at=NOW):
    return {
        "mode": TRIAGE.EXPECTED_RUNTIME_MODE,
        "observedAtUtc": at.isoformat(),
        "inventoryCompleteForDiscoveredUnits": True,
        "unitsWithIncompleteInspection": [],
        "appUnits": [
            {"unit": "aoe2hdbets-web.service", "active": True, "mainPidPresent": True,
             "configuredFinancialKeyNames": ["WOLO_BET_PAYOUT_MNEMONIC"]},
            {"unit": "aoe2dewarwagers-web.service", "active": True, "mainPidPresent": True},
            {"unit": "aoe2war-prewarm.timer", "active": True, "mainPidPresent": False},
            {"unit": "aoe2dewarwagers-api.service", "active": False, "mainPidPresent": False},
        ],
    }


class ProducerOwnerTriageTests(unittest.TestCase):
    def test_fresh_runtime_and_source_evidence_are_not_release_or_fence(self):
        hd, de = source_packets()
        result = TRIAGE.report(runtime(), hd, de, NOW)
        self.assertTrue(result["runtimeFresh"])
        self.assertTrue(result["hdSourceObserved"])
        self.assertTrue(result["deSourceObserved"])
        self.assertEqual(result["counts"], {
            "unitsObserved": 4, "activeObserved": 3, "hdOrSharedUnits": 2,
            "deUnits": 2, "unknownOwnerUnits": 0,
        })
        self.assertEqual(result["status"], "HOLD")
        self.assertTrue(all(x["reviewStatus"] == "OWNER_REVIEW_REQUIRED"
                            for x in result["unitOwnerReview"]))
        for flag in ("sourceRuntimeParityProven", "producerIsolationProven",
                     "allTransfersReconciled", "financialReleaseAuthorized",
                     "websiteReleaseAuthorized", "productionMutated"):
            self.assertIs(result[flag], False)
        self.assertNotIn("WOLO_BET_PAYOUT_MNEMONIC", json.dumps(result))
        self.assertIn("NAMED_FINANCIAL_FENCE_APPROVAL_MISSING", result["unresolved"])

    def test_stale_future_and_missing_inventory_never_become_verified(self):
        hd, de = source_packets()
        for when in (NOW - timedelta(hours=4), NOW + timedelta(seconds=1)):
            result = TRIAGE.report(runtime(when), hd, de, NOW)
            self.assertFalse(result["runtimeFresh"])
            self.assertIn("RUNTIME_INVENTORY_STALE_OR_UNDATED", result["unresolved"])
        r = TRIAGE.report(None, hd, de, NOW)
        self.assertEqual(r["counts"]["unitsObserved"], 0)
        self.assertIn("RUNTIME_INVENTORY_MISSING_OR_INVALID", r["unresolved"])
        self.assertFalse(r["producerIsolationProven"])

    def test_source_drift_and_dirty_de_identity_are_unverified(self):
        hd, de = source_packets()
        hd["observations"][0]["status"] = "SOURCE_DRIFT"
        de["local_source"]["state"] = "SOURCE_IDENTITY_UNVERIFIED"
        result = TRIAGE.report(runtime(), hd, de, NOW)
        self.assertFalse(result["hdSourceObserved"])
        self.assertFalse(result["deSourceObserved"])
        self.assertIn("HD_SOURCE_EDGE_PROOF_MISSING_OR_DRIFTED", result["unresolved"])
        self.assertIn("DE_SOURCE_EDGE_PROOF_MISSING_OR_DRIFTED", result["unresolved"])

    def test_duplicate_and_malformed_units_never_silently_prove_complete_coverage(self):
        hd, de = source_packets()
        r = runtime()
        r["appUnits"].append(r["appUnits"][0])
        r["appUnits"].append({"unit": "../../private.env", "active": True})
        r["appUnits"].append({"unit": "some-other-wallet.service", "active": False})
        got = TRIAGE.report(r, hd, de, NOW)
        self.assertEqual(got["counts"]["unitsObserved"], 5)
        self.assertEqual(got["counts"]["unknownOwnerUnits"], 1)
        self.assertIn("RUNTIME_UNIT_INVALID_OR_DUPLICATE", got["unresolved"])
        self.assertFalse(got["producerIsolationProven"])

    def test_packets_require_bounded_regular_files_with_no_duplicate_json_keys(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            f = root / "source.json"
            f.write_text('{"x":1,"x":2}')
            with self.assertRaisesRegex(ValueError, "DUPLICATE_JSON_KEY"):
                TRIAGE.read_packet(f)
            f.write_text('{"mode":"evidence"}')
            self.assertEqual(TRIAGE.read_packet(f)["mode"], "evidence")
            link = root / "link"
            link.symlink_to(f)
            with self.assertRaises(ValueError):
                TRIAGE.read_packet(link)
            f.write_bytes(b"A" * (TRIAGE.MAX_BYTES + 1))
            with self.assertRaises(ValueError):
                TRIAGE.read_packet(f)

    def test_cli_is_always_nonauthorizing_even_with_good_input(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            hd, de = source_packets()
            for filename, data in [("runtime.json", runtime()), ("hd.json", hd), ("de.json", de)]:
                (root / filename).write_text(json.dumps(data))
            from unittest.mock import patch
            from io import StringIO
            with patch("sys.stdout", new_callable=StringIO) as capture:
                code = TRIAGE.main(["--runtime", str(root / "runtime.json"),
                                   "--hd-source", str(root / "hd.json"),
                                   "--de-source", str(root / "de.json")])
            self.assertEqual(code, 3)
            payload = json.loads(capture.getvalue())
            self.assertFalse(payload["financialReleaseAuthorized"])
            self.assertEqual(payload["status"], "HOLD")


if __name__ == "__main__":
    unittest.main()

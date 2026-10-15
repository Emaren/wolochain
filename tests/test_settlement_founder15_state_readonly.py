"""Bounded original-settlement state forensics; entirely synthetic local fixtures."""
import importlib.util
import json
import pathlib
import tempfile
import unittest

SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "settlement-founder15-state-readonly.py"
spec = importlib.util.spec_from_file_location("founder_state_readonly", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class FounderStateReadOnlyTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = pathlib.Path(self.tmp.name)
        self.roots = (root / "primary", root / "founder")
        for folder in self.roots:
            (folder / "requests").mkdir(parents=True)

    def write(self, lane, request_id, *, memo="AoE2 Founder payout · bonus 15 · founders-win · winner-left", tx=None):
        path = self.roots[lane] / "requests" / (request_id + ".json")
        path.write_text(json.dumps({
            "request": {"request_id": request_id, "memo": memo,
                        "to_address": "wolo1PRIVATE", "amount_uwolo": "190000000"},
            "response": {"status": "confirmed" if tx else "failed",
                         "failure_code": "X" if not tx else "",
                         "tx_hash": tx or ""},
            "fingerprint": "SECRET_VALUE",
        }), encoding="utf8")
        return path

    def test_founder_candidate_never_certifies_claim_or_releases_services(self):
        self.write(1, "aoe2-founder-15-winner-left", tx="A" * 64)
        result = module.read_records(self.roots)
        self.assertEqual(result["requestRecordsFound"], 1)
        self.assertEqual(result["records"][0]["lane"], "founder_rewards")
        self.assertTrue(result["records"][0]["hasReportedTxHash"])
        self.assertEqual(result["records"][0]["reportedPublicTxHash"], "A" * 64)
        self.assertTrue(result["records"][0]["isFounderBonus15Memo"])
        self.assertFalse(result["claim889Reconciled"])
        self.assertFalse(result["allHistoricalPayoutPathsCovered"])
        self.assertFalse(result["productionPromotionAuthorized"])
        self.assertFalse(result["payoutOrRetryAuthorized"])
        self.assertNotIn("PRIVATE", json.dumps(result))
        self.assertNotIn("SECRET_VALUE", json.dumps(result))

    def test_empty_directories_are_inconclusive(self):
        result = module.read_records(self.roots)
        self.assertEqual(result["requestRecordsFound"], 0)
        self.assertFalse(result["claim889Reconciled"])
        self.assertFalse(result["financialDrained"])

    def test_unrelated_bonus_ignored_and_duplicate_identity_caught(self):
        self.write(0, "aoe2-founder-16-winner-left")
        self.assertEqual(module.read_records(self.roots)["requestRecordsFound"], 0)
        p = self.write(1, "aoe2-founder-15-winner-left")
        raw = json.loads(p.read_text())
        raw["request"]["request_id"] = "aoe2-founder-15-wrong-id"
        p.write_text(json.dumps(raw))
        with self.assertRaises(ValueError):
            module.read_records(self.roots)

    def test_rejects_symlinks_and_oversized_or_malformed_records(self):
        p = self.write(0, "aoe2-founder-15-winner-right")
        p.write_text("{invalid")
        with self.assertRaises(json.JSONDecodeError):
            module.read_records(self.roots)
        p.write_bytes(b"x" * (module.MAX_BYTES + 1))
        with self.assertRaises(ValueError):
            module.read_records(self.roots)
        p.unlink()
        p.symlink_to(self.roots[1] / "requests")
        with self.assertRaises(ValueError):
            module.read_records(self.roots)

    def test_bounded_files_and_no_writes(self):
        source = SCRIPT.read_text()
        self.assertIn("os.O_RDONLY", source)
        self.assertIn("O_NOFOLLOW", source)
        self.assertIn("MAX_RECORDS = 128", source)
        self.assertIn("MAX_BYTES = 1024 * 1024", source)
        self.assertIn("return 3", source)
        self.assertNotIn("subprocess", source)
        self.assertNotIn("requests.get", source)
        self.assertNotIn("urllib.request", source)


if __name__ == "__main__":
    unittest.main()

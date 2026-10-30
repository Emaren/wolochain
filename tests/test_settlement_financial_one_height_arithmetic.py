"""Synthetic, side-effect-free one-height solvency arithmetic regression tests."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "scripts" / "settlement_financial_one_height_arithmetic.py"
spec = importlib.util.spec_from_file_location("financial_one_height", TOOL)
finance = importlib.util.module_from_spec(spec)
spec.loader.exec_module(finance)
SHA = lambda ch: ch * 64
HEAD = "a" * 40
HEIGHT = 1078913


def fixture():
    return {
        "schema": finance.SCHEMA,
        "chain_id": "wolo-1",
        "source_commit": HEAD,
        "height": HEIGHT,
        "block_sha256": SHA("1"),
        "accounts": [
            {"identity_sha256": SHA("2"), "role": "payout", "balance_uwolo": "400",
             "source_sha256": SHA("3"), "height": HEIGHT, "block_sha256": SHA("1")},
            {"identity_sha256": SHA("4"), "role": "escrow", "balance_uwolo": "250",
             "source_sha256": SHA("5"), "height": HEIGHT, "block_sha256": SHA("1")},
            # Same custody account observed in a second service lane, not new assets.
            {"identity_sha256": SHA("4"), "role": "escrow", "balance_uwolo": "250",
             "source_sha256": SHA("6"), "height": HEIGHT, "block_sha256": SHA("1")},
        ],
        "obligations": [
            {"economic_id_sha256": SHA("7"), "source": "hd",
             "requested_unpaid_uwolo": "300", "source_sha256": SHA("8"),
             "height": HEIGHT, "block_sha256": SHA("1")},
            {"economic_id_sha256": SHA("7"), "source": "founder_journal",
             "requested_unpaid_uwolo": "300", "source_sha256": SHA("9"),
             "height": HEIGHT, "block_sha256": SHA("1")},
            {"economic_id_sha256": SHA("a"), "source": "de",
             "requested_unpaid_uwolo": "100", "source_sha256": SHA("b"),
             "height": HEIGHT, "block_sha256": SHA("1")},
        ],
        "uncertain_effects": [
            {"physical_effect_id_sha256": SHA("c"), "source": "primary_journal",
             "upper_exposure_uwolo": "100", "source_sha256": SHA("d"),
             "height": HEIGHT, "block_sha256": SHA("1")},
        ],
        "scope_coverage": {
            k: {"complete": True, "source_sha256": SHA("e")}
            for k in finance.COVERAGE
        },
    }


class OneHeightArithmeticTests(unittest.TestCase):
    def setUp(self):
        self.packet = fixture()

    def report(self):
        return finance.arithmetic(self.packet, SHA("f"))

    def held(self, message):
        with self.assertRaisesRegex(finance.InvalidEvidence, "^" + message + "$"):
            self.report()

    def test_claimed_same_height_arithmetic_never_authorizes_bank(self):
        r = self.report()
        self.assertEqual(r["bank_accounts_unique"], 2)
        self.assertEqual(r["bank_assets_claimed_uwolo"], "650")
        self.assertEqual(r["recorded_unpaid_requested_uwolo"], "400")
        self.assertEqual(r["obligations_unique"], 2)
        self.assertEqual(r["cross_source_obligation_identifiers"], 1)
        self.assertEqual(r["bounded_effect_additional_reserve_uwolo"], "100")
        self.assertEqual(r["unverified_cross_source_obligation_overlaps"], 1)
        self.assertFalse(r["arithmetic_complete_for_claimed_scope"])
        self.assertIsNone(r["conditional_recorded_reserve_uwolo"])
        self.assertIsNone(r["conditional_margin_uwolo"])
        self.assertEqual(r["solvency_verdict"], "UNKNOWN_INDEPENDENT_EVIDENCE_REQUIRED")
        self.assertIsNone(r["global_liability_upper_bound_uwolo"])
        self.assertIsNone(r["bank_assets_authenticated_uwolo"])
        self.assertFalse(r["financial_release_authorized"])
        self.assertFalse(r["chain_finality_authenticated"])

    def test_unambiguous_per_source_claims_have_conditional_math_only(self):
        # The physical HD obligation is not separately reasserted by a founder
        # source. These are still caller claims, NOT an authenticated reserve.
        self.packet["obligations"].pop(1)
        r = self.report()
        self.assertEqual(r["cross_source_obligation_identifiers"], 0)
        self.assertEqual(r["unverified_cross_source_obligation_overlaps"], 0)
        self.assertTrue(r["arithmetic_complete_for_claimed_scope"])
        self.assertEqual(r["conditional_recorded_reserve_uwolo"], "500")
        self.assertEqual(r["conditional_margin_uwolo"], "150")
        self.assertEqual(r["status"], "HOLD")
        self.assertFalse(r["financial_release_authorized"])

    def test_identical_cross_source_claims_require_independent_overlap_proof(self):
        # HD and founder journal can each hold a distinct 300 uWOLO claim.
        # A repeated economic_id_sha256, equal amount and complete=true
        # alone cannot justify a positive available-reserve margin.
        r = self.report()
        self.assertEqual(r["cross_source_obligation_identifiers"], 1)
        self.assertEqual(r["unverified_cross_source_obligation_overlaps"], 1)
        self.assertIsNone(r["conditional_margin_uwolo"])
        self.assertFalse(r["arithmetic_complete_for_claimed_scope"])
        self.assertEqual(r["solvency_verdict"], "UNKNOWN_INDEPENDENT_EVIDENCE_REQUIRED")

    def test_underwater_math_is_reported_but_not_certified(self):
        self.packet["obligations"].pop(1)
        self.packet["accounts"][0]["balance_uwolo"] = "10"
        self.packet["accounts"][1]["balance_uwolo"] = "10"
        self.packet["accounts"][2]["balance_uwolo"] = "10"
        r = self.report()
        self.assertEqual(r["conditional_margin_uwolo"], "-480")
        self.assertEqual(r["status"], "HOLD")

    def test_unbounded_ambiguous_transfer_never_gets_spurious_zero(self):
        self.packet["uncertain_effects"][0]["upper_exposure_uwolo"] = None
        r = self.report()
        self.assertEqual(r["unbounded_effects"], 1)
        self.assertIsNone(r["conditional_recorded_reserve_uwolo"])
        self.assertIsNone(r["conditional_margin_uwolo"])
        self.assertIsNone(r["global_liability_upper_bound_uwolo"])

    def test_missing_product_or_external_writer_scope_invalidates_bound(self):
        self.packet["scope_coverage"]["offhost_signers"]["complete"] = False
        self.packet["scope_coverage"]["de_claims"]["source_sha256"] = None
        r = self.report()
        self.assertEqual(r["coverage_gaps"], ["de_claims", "offhost_signers"])
        self.assertIsNone(r["conditional_margin_uwolo"])

    def test_duplicate_account_with_conflicting_balance_rejected(self):
        self.packet["accounts"][2]["balance_uwolo"] = "251"
        self.held("SHARED_ACCOUNT_CONFLICT")

    def test_duplicate_bank_identity_with_different_role_rejected(self):
        self.packet["accounts"][2]["role"] = "payout"
        self.held("SHARED_ACCOUNT_CONFLICT")

    def test_two_sources_same_debt_with_conflicting_amount_stop(self):
        self.packet["obligations"][1]["requested_unpaid_uwolo"] = "301"
        self.held("SAME_OBLIGATION_CONFLICT")

    def test_uncertain_effects_are_never_offset_against_pending_debt(self):
        self.packet["uncertain_effects"].append(copy.deepcopy(self.packet["uncertain_effects"][0]))
        self.assertEqual(self.report()["bounded_effect_additional_reserve_uwolo"], "100")
        self.packet["uncertain_effects"][-1]["upper_exposure_uwolo"] = "99"
        self.held("SAME_EFFECT_BOUND_CONFLICT")

    def test_same_id_pending_gas_in_two_sources_never_becomes_free_reserve(self):
        # Claimed HD/founder debt collision is removed so this regression
        # isolates the independent prepared-send/fee fingerprint failure.
        self.packet["obligations"].pop(1)
        duplicate = copy.deepcopy(self.packet["uncertain_effects"][0])
        duplicate["source"] = "external"
        duplicate["source_sha256"] = SHA("9")
        self.packet["uncertain_effects"].append(duplicate)
        r = self.report()
        self.assertEqual(r["unverified_cross_source_obligation_overlaps"], 0)
        self.assertEqual(r["unverified_cross_source_uncertain_effect_overlaps"], 1)
        self.assertEqual(r["unresolved_effects_unique"], 1)
        # Two source-specific 100-uWOLO pending preparations can both execute.
        # A matching claimant ID does not justify counting only one 100.
        self.assertEqual(r["bounded_effect_additional_reserve_uwolo"], "200")
        self.assertFalse(r["arithmetic_complete_for_claimed_scope"])
        self.assertIsNone(r["conditional_recorded_reserve_uwolo"])
        self.assertIsNone(r["conditional_margin_uwolo"])
        self.assertFalse(r["financial_release_authorized"])

    def test_simultaneous_pending_withdrawal_and_fee_are_additive(self):
        self.packet["obligations"].pop(1)
        # A distinct pending Satchel withdrawal is still an unpaid liability;
        # prepared offhost gas is a separate unresolved physical exposure.
        self.packet["obligations"].append({
            "economic_id_sha256": SHA("e"), "source": "war_satchel",
            "requested_unpaid_uwolo": "120", "source_sha256": SHA("8"),
            "height": HEIGHT, "block_sha256": SHA("1"),
        })
        self.packet["uncertain_effects"].append({
            "physical_effect_id_sha256": SHA("8"), "source": "external",
            "upper_exposure_uwolo": "40", "source_sha256": SHA("9"),
            "height": HEIGHT, "block_sha256": SHA("1"),
        })
        r = self.report()
        self.assertEqual(r["unverified_cross_source_uncertain_effect_overlaps"], 0)
        self.assertEqual(r["bounded_effect_additional_reserve_uwolo"], "140")
        self.assertEqual(r["conditional_recorded_reserve_uwolo"], "660")
        self.assertEqual(r["conditional_margin_uwolo"], "-10")
        self.assertEqual(r["status"], "HOLD")
        self.assertFalse(r["financial_release_authorized"])

    def test_same_source_repeated_prepared_effect_is_not_double_counted(self):
        self.packet["obligations"].pop(1)
        self.packet["uncertain_effects"].append(
            copy.deepcopy(self.packet["uncertain_effects"][0]))
        r = self.report()
        self.assertEqual(r["unverified_cross_source_uncertain_effect_overlaps"], 0)
        self.assertEqual(r["bounded_effect_additional_reserve_uwolo"], "100")
        self.assertEqual(r["conditional_margin_uwolo"], "150")
        self.assertFalse(r["financial_release_authorized"])

    def test_forged_solvency_or_approval_fields_rejected(self):
        for name, value in (
            ("financial_release_authorized", True),
            ("solvency_certified", True),
            ("bank_assets_authenticated_uwolo", "650"),
        ):
            self.packet[name] = value
            self.held("INPUT_SCHEMA_INVALID")
            del self.packet[name]

    def test_height_and_commit_provenance_mismatch_stop(self):
        self.packet["obligations"][1]["height"] -= 1
        self.held("STALE_OR_MIXED_HEIGHT_EVIDENCE")
        self.packet = fixture()
        self.packet["accounts"][1]["block_sha256"] = SHA("d")
        self.held("STALE_OR_MIXED_HEIGHT_EVIDENCE")
        self.packet = fixture()
        self.packet["source_commit"] = "b" * 39
        self.held("UNBOUND_SOURCE_OR_CHAIN")

    def test_noncanonical_money_no_float_bool_scientific_or_overflow(self):
        for value in ("01", "1.0", "1e4", -1, True, str(1 << 128)):
            self.packet["obligations"][0]["requested_unpaid_uwolo"] = value
            with self.assertRaises(finance.InvalidEvidence):
                self.report()
        self.packet = fixture()
        self.packet["height"] = True
        self.held("INVALID_HEIGHT_OR_BLOCK")

    def test_oversized_inventory_refused(self):
        self.packet["uncertain_effects"] *= 2001
        self.held("INVENTORY_SIZE_INVALID")

    def test_read_no_follow_duplicate_keys_and_missing_files(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "candidate.json"
            p.write_text('{"a":1,"a":2}')
            with self.assertRaisesRegex(finance.InvalidEvidence, "^DUPLICATE_JSON_KEY$"):
                finance.read_input(p)
            p.unlink()
            p.symlink_to("/etc/hosts")
            with self.assertRaises(finance.InvalidEvidence):
                finance.read_input(p)

    def test_actual_cli_has_held_exit_and_no_private_identity(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "packet.json"
            p.write_text(json.dumps(self.packet), encoding="utf8")
            with patch.object(finance, "print", create=True) as printer:
                self.assertEqual(finance.main(["--input", str(p)]), 3)
            result = json.loads(printer.call_args.args[0])
            self.assertFalse(result["financial_release_authorized"])
            self.assertNotIn("wallet", json.dumps(result).lower())
            self.assertNotIn("wolo1", json.dumps(result).lower())
            self.assertNotIn("/etc/", json.dumps(result))


if __name__ == "__main__":
    unittest.main()

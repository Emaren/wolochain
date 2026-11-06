"""C04 exact claim 9645 legacy prebroadcast refusal — offline, no permission."""
from __future__ import annotations
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/settlement_c04_legacy_prebroadcast_refusal_hold.py"


def load():
    spec = importlib.util.spec_from_file_location("c04_prebroadcast_refusal_hold", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class C04PrebroadcastRefusalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = load()

    def setUp(self):
        self.address = "wolo1" + "a" * 40
        self.obs = {
            "schema": self.m.OBSERVATION_SCHEMA,
            "legacy_binary_vcs": self.m.EXPECTED_VCS,
            "legacy_binary_sha256": self.m.EXPECTED_BINARY_SHA,
            "wallet_material_exported": False,
            "production_mutated": False,
            "recipient_wallet_sha256": self.m.wallet_digest(self.address),
            "claim": {
                "id": 9645, "source_market_id": 946520,
                "amount_wolo": 100, "claim_kind": "bet_refund",
                "status": "pending", "payout_attempted_at_present": True,
                "payout_tx_hash_present": False,
            },
            "wager": {
                "id": 1483, "market_id": 946520,
                "amount_wolo": 100, "status": "void",
                "stake_tx_hash_present": True,
                "payout_tx_hash_present": False,
            },
        }
        self.journal = {
            "fingerprint": "synthetic-fingerprint",
            "request": {
                "settlement_run_id": "aoe2-bet-market-946520",
                "source_app": "aoe2hdbets",
                "source_event_id": "bet-market-946520",
                "signer_role": "escrow",
                "payouts": [{
                    "request_id": "aoe2-bet-946520-bet_refund-424105",
                    "to_address": self.address,
                    "amount_uwolo": "100000000",
                }],
            },
            "response": {
                "settlement_run_id": "aoe2-bet-market-946520",
                "signer_role": "escrow",
                "status": "failed", "ok": False,
                "retryable": False,
                "failure_code": "ESCROW_SIGNER_UNAVAILABLE",
                "detail": 'could not resolve escrow signer "mainnet-escrow":',
                "executed_payout_count": 0,
                "confirmed_payout_count": 0,
                "requested_payout_count": 1,
                "requested_total_uwolo": "100000000",
                "idempotent_replay": False,
                "payouts": [{
                    "request_id": "aoe2-bet-946520-bet_refund-424105",
                    "amount_uwolo": "100000000",
                    "status": "failed",
                    "failure_code": "ESCROW_SIGNER_UNAVAILABLE",
                    "ok": False, "retryable": False, "tx_hash": None,
                }],
            },
        }
        self.hashes = {"observation": "a" * 64, "journal": "b" * 64}

    def classify(self):
        return self.m.classify(self.obs, self.journal, self.hashes)

    def denied(self, expected):
        with self.assertRaisesRegex(self.m.Refusal, expected):
            self.classify()

    def test_exact_case_is_held_and_cannot_authorize_or_establish_global_unpaid(self):
        r = self.classify()
        self.assertEqual(r["status"], "HOLD")
        self.assertTrue(r["local_legacy_journal_prebroadcast_refusal"])
        self.assertTrue(r["recipient_amount_and_wager_matched"])
        for flag in ("financial_release_authorized", "retry_authorized",
                     "claim_paid_or_unpaid_proved",
                     "independent_canonical_chain_finality_proved",
                     "any_other_signer_or_journal_absence_proved", "production_mutated"):
            self.assertIs(r[flag], False, flag)

    def test_claim_fate_cannot_be_rewritten(self):
        self.obs["claim"]["status"] = "claimed"
        self.denied("CLAIM_IDENTITY")
        self.obs["claim"]["status"] = "pending"
        self.obs["claim"]["payout_attempted_at_present"] = False
        self.denied("CLAIM_IDENTITY")

    def test_claim_market_and_amount_are_exact(self):
        self.obs["claim"]["source_market_id"] = 123
        self.denied("CLAIM_IDENTITY")
        self.obs["claim"]["source_market_id"] = 946520
        self.obs["claim"]["amount_wolo"] = 101
        self.denied("CLAIM_IDENTITY")

    def test_stake_wager_must_still_be_void_and_unpaid(self):
        self.obs["wager"]["status"] = "won"
        self.denied("ORIGINAL_WAGER")
        self.obs["wager"]["status"] = "void"
        self.obs["wager"]["payout_tx_hash_present"] = True
        self.denied("ORIGINAL_WAGER")

    def test_request_recipient_cannot_be_substituted(self):
        self.journal["request"]["payouts"][0]["to_address"] = "wolo1" + "b" * 40
        self.denied("JOURNAL_RECIPIENT")

    def test_request_amount_must_be_exact_100_wolo_in_micro_units(self):
        self.journal["request"]["payouts"][0]["amount_uwolo"] = "100000001"
        self.denied("JOURNAL_RECIPIENT")

    def test_reported_failure_cannot_be_broadcast_uncertainty(self):
        self.journal["response"]["failure_code"] = "BROADCAST_FAILED"
        self.denied("LEGACY_RUN_NOT_PREBROADCAST")

    def test_ambiguous_tx_hash_must_never_be_classified_as_no_send(self):
        self.journal["response"]["payouts"][0]["tx_hash"] = "a" * 64
        self.denied("PAYOUT_BROADCAST_UNCERTAINTY")

    def test_positive_executed_count_never_qualifies(self):
        self.journal["response"]["executed_payout_count"] = 1
        self.denied("LEGACY_RUN_NOT_PREBROADCAST")

    def test_payout_count_and_idempotency_do_not_silently_change(self):
        self.journal["response"]["idempotent_replay"] = True
        self.denied("LEGACY_RUN_NOT_PREBROADCAST")
        self.journal["response"]["idempotent_replay"] = False
        self.journal["request"]["payouts"].append(copy.deepcopy(self.journal["request"]["payouts"][0]))
        self.denied("EXACTLY_ONE_PAYOUT")

    def test_runtime_identity_not_replaceable_by_an_observer(self):
        self.obs["legacy_binary_vcs"] = "c" * 40
        self.denied("LEGACY_SOURCE_BINARY")
        self.obs["legacy_binary_vcs"] = self.m.EXPECTED_VCS
        self.obs["legacy_binary_sha256"] = "d" * 64
        self.denied("LEGACY_SOURCE_BINARY")

    def test_fake_observer_attestation_cannot_make_authority(self):
        self.obs["wallet_material_exported"] = True
        self.denied("OBSERVATION_NOT_NONMUTATING")
        self.obs["wallet_material_exported"] = False
        self.obs["production_mutated"] = True
        self.denied("OBSERVATION_NOT_NONMUTATING")

    def test_hashed_inputs_reject_untrusted_file_and_wrong_digest(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "claim.json"
            p.write_text(json.dumps(self.obs))
            p.chmod(0o600)
            digest = hashlib.sha256(p.read_bytes()).hexdigest()
            self.assertEqual(self.m.read_pinned(p, digest)["schema"], self.m.OBSERVATION_SCHEMA)
            with self.assertRaisesRegex(self.m.Refusal, "SOURCE_SHA_MISMATCH"):
                self.m.read_pinned(p, "0" * 64)
            p.chmod(0o644)
            with self.assertRaisesRegex(self.m.Refusal, "SOURCE_NOT_PRIVATE"):
                self.m.read_pinned(p, digest)

    def test_symlink_and_duplicate_keys_refused(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            original = base / "original.json"
            original.write_text('{"schema":1,"schema":2}')
            original.chmod(0o600)
            digest = hashlib.sha256(original.read_bytes()).hexdigest()
            with self.assertRaisesRegex(self.m.Refusal, "DUPLICATE_JSON_KEY"):
                self.m.read_pinned(original, digest)
            alias = base / "link.json"
            alias.symlink_to(original)
            with self.assertRaisesRegex(self.m.Refusal, "SOURCE_UNAVAILABLE"):
                self.m.read_pinned(alias, digest)

    def test_cli_only_returns_hold_or_stop(self):
        with tempfile.TemporaryDirectory() as td:
            folder = Path(td)
            obs = folder / "obs.json"
            journal = folder / self.m.EXPECTED_JOURNAL_NAME
            obs.write_text(json.dumps(self.obs))
            journal.write_text(json.dumps(self.journal))
            obs.chmod(0o600)
            journal.chmod(0o600)
            args = ["--observation", str(obs),
                    "--sha256-observation", hashlib.sha256(obs.read_bytes()).hexdigest(),
                    "--journal", str(journal),
                    "--sha256-journal", hashlib.sha256(journal.read_bytes()).hexdigest()]
            with redirect_stdout(StringIO()) as out:
                self.assertEqual(self.m.main(args), 3)
            self.assertIs(json.loads(out.getvalue())["financial_release_authorized"], False)
            self.journal["response"]["status"] = "success"
            journal.write_text(json.dumps(self.journal))
            with redirect_stdout(StringIO()) as out:
                self.assertEqual(self.m.main(args), 2)
            self.assertEqual(json.loads(out.getvalue())["status"], "STOP")

    def test_source_never_networks_writes_or_broadcasts(self):
        src = SCRIPT.read_text()
        for disallowed in ("subprocess", "urllib.request", "requests.post",
                           "wolochaind", "psql", "broadcast_tx", "os.system("):
            self.assertNotIn(disallowed, src)


if __name__ == "__main__":
    unittest.main()

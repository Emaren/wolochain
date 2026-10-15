#!/usr/bin/env python3
"""Offline unit tests. Never connects to a machine, DB, signer or WoloChain."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1] / "scripts/settlement-parallel-de-authority-inventory.py"
spec = importlib.util.spec_from_file_location("parallel_de_inventory", SOURCE)
mod = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(mod)


class ReadOnlyInventoryTests(unittest.TestCase):
    def test_proc_env_does_not_emit_any_values(self):
        literal_secret = b"this-must-never-be-printed"
        env = (
            b"WOLO_SETTLEMENT_AUTH_TOKEN=" + literal_secret
            + b"\x00WOLO_STAKING_CLI=/usr/local/bin/wolochaind"
            + b"\x00WOLO_STAKING_HOME=/root/SECRET"
            + b"\x00DATABASE_URL=postgres://username:password@private"
            + b"\x00WOLO_BET_PAYOUT_MNEMONIC=some mnemonic words"
            + b"\x00NOT_AN_ALLOWLISTED_SECRET=other-private-data"
            + b"\x00WOLO_FAUCET_CLI=\x00"
        )
        grouped = mod.summarize_keys(mod.parse_process_env(env))
        rendered = json.dumps(grouped)
        for forbidden in (
            literal_secret.decode(),
            "private", "/root/", "postgres://", "mnemonic words",
            "NOT_AN_ALLOWLISTED_SECRET"
        ):
            self.assertNotIn(forbidden, rendered)
        self.assertEqual(grouped["remote_settlement_authority"], ["WOLO_SETTLEMENT_AUTH_TOKEN"])
        self.assertEqual(grouped["external_keyring_signers"], ["WOLO_STAKING_CLI", "WOLO_STAKING_HOME"])
        self.assertEqual(grouped["database_authority"], ["DATABASE_URL"])
        self.assertEqual(grouped["signing_secrets"], ["WOLO_BET_PAYOUT_MNEMONIC"])
        self.assertFalse("WOLO_FAUCET_CLI" in grouped["external_keyring_signers"])

    def test_actual_de_staking_signer_paths_are_classified_without_secret_values(self):
        raw = (
            b"WOLO_STAKING_WALLET_MNEMONIC=SECRET MNEMONIC NEVER OUTPUT"
            b"\x00WOLO_STAKING_ALLOW_PAYOUT_MNEMONIC_FALLBACK=1"
            b"\x00WOLO_STAKING_DISABLE_KEYRING_SIGNER=1"
            b"\x00WOLO_STAKING_KEY_NAME=staking"
            b"\x00WOLO_STAKING_KEYRING_BACKEND=test"
            b"\x00WOLO_FAUCET_FROM=faucet-key"
            b"\x00WOLO_STAKING_NODE_RPC=http://private-endpoint"
            b"\x00WOLO_STAKING_WALLET_ADDRESS=wolo1private"
        )
        groups = mod.summarize_keys(mod.parse_process_env(raw))
        self.assertEqual(groups["signing_secrets"], ["WOLO_STAKING_WALLET_MNEMONIC"])
        self.assertEqual(
            groups["signing_controls"],
            ["WOLO_STAKING_ALLOW_PAYOUT_MNEMONIC_FALLBACK",
             "WOLO_STAKING_DISABLE_KEYRING_SIGNER"],
        )
        self.assertIn("WOLO_STAKING_KEY_NAME", groups["external_keyring_signers"])
        self.assertIn("WOLO_FAUCET_FROM", groups["external_keyring_signers"])
        self.assertIn("WOLO_STAKING_NODE_RPC", groups["signer_network_configuration"])
        self.assertIn("WOLO_STAKING_WALLET_ADDRESS", groups["payout_account_configuration"])
        output = json.dumps(groups)
        for forbidden in ("SECRET MNEMONIC", "staking\"",
                          "faucet-key", "private-endpoint", "wolo1private"):
            self.assertNotIn(forbidden, output)

    def test_classification_covers_de_staking_code_and_never_grants_clearance(self):
        self.assertIn("WOLO_STAKING_WALLET_MNEMONIC", mod.GROUPS["signing_secrets"])
        self.assertIn("WOLO_STAKING_ALLOW_PAYOUT_MNEMONIC_FALLBACK", mod.GROUPS["signing_controls"])
        self.assertIn("WOLO_STAKING_DISABLE_KEYRING_SIGNER", mod.GROUPS["signing_controls"])
        self.assertIn("WOLO_STAKING_CLI", mod.GROUPS["external_keyring_signers"])
        self.assertIn("WOLO_FAUCET_CLI", mod.GROUPS["external_keyring_signers"])

    def test_app_local_env_ignores_comments_and_redacts(self):
        raw = b"""# WOLO_FAUCET_CLI=/do/not/count
          export WOLO_FAUCET_HOME=/root/highly-sensitive
          DATABASE_URL="postgres://redacted"
          WOLO_SETTLEMENT_URL=https://secret-host
          WOLO_BET_PAYOUT_ADDRESS="wolo1secretaddress"
          NOT_A_WOLO_KEY=password
          WOLO_BET_PAYOUT_MNEMONIC=""
        """
        groups = mod.summarize_keys(mod.parse_dotenv_keys(raw))
        rendered = json.dumps(groups)
        self.assertEqual(groups["external_keyring_signers"], ["WOLO_FAUCET_HOME"])
        self.assertEqual(groups["database_authority"], ["DATABASE_URL"])
        self.assertEqual(groups["signing_secrets"], [])
        for forbidden in ("/root/", "redacted", "secret-host", "secretaddress", "password"):
            self.assertNotIn(forbidden, rendered)

    def test_output_is_never_release_clearance(self):
        out = io.StringIO()
        with patch.object(mod.os, "geteuid", return_value=0), \
             patch.object(mod, "inspect_unit", side_effect=lambda unit: {
                 "unit": unit, "active": False,
                 "configurationKeysPresentInProcess": mod.summarize_keys(set()),
                 "configurationKeysPresentInAppEnv": mod.summarize_keys(set()),
             }), \
             patch.object(mod, "de_units_seen", return_value=[]), \
             contextlib.redirect_stdout(out):
            status = mod.main()
        payload = json.loads(out.getvalue())
        self.assertEqual(status, 3)
        self.assertEqual(payload["conclusion"], "NOT_CERTIFIED_FOR_SHARED_WOLO_SETTLEMENT_DOWNTIME")
        self.assertFalse(payload["promotionAuthorized"])
        self.assertFalse(payload["servicesChanged"])
        self.assertFalse(payload["tokensMoved"])

    def test_no_private_proc_access_without_root(self):
        err = io.StringIO()
        with patch.object(mod.os, "geteuid", return_value=1000), \
             contextlib.redirect_stderr(err):
            code = mod.main()
        self.assertEqual(code, 2)
        self.assertIn("BLOCKED", err.getvalue())


if __name__ == "__main__":
    unittest.main()

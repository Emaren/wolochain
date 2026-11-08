"""C04/C05 gross nominal-vs-native historical escrow observation HOLD tests.

Hermetic. No network, no production database, no custody access, no payment.
"""
import importlib.util
import json
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch

FILE=(Path(__file__).resolve().parents[1]/
      "scripts/settlement_c05_claimed_pending_vs_legacy_escrow_hold.py")
spec=importlib.util.spec_from_file_location("c05_claims",FILE)
tool=importlib.util.module_from_spec(spec);spec.loader.exec_module(tool)

CLAIMS="claimed_hashless|69|120443|69\npending|948|993289|948\n"
BALANCE={"balances":[{"denom":"uwolo","amount":"826713500000"}],
         "pagination":{"next_key":None,"total":"0"}}

class C05NominalTests(unittest.TestCase):
    def test_full_group_counts_and_nominal_parse(self):
        o=tool.parse_claims(CLAIMS)
        self.assertEqual(o["claimed_hashless"]["rows"],69)
        self.assertEqual(o["pending"]["nominal_wolo"],993289)
        self.assertEqual(sum(x["nominal_wolo"] for x in o.values()),1113732)

    def test_missing_group_or_extra_kind_fail(self):
        for x in ("pending|948|993289|948\n",
                  CLAIMS+"other|1|1|1\n",
                  CLAIMS.replace("claimed_hashless","other")):
            with self.subTest(text=x),self.assertRaises(tool.Hold):
                tool.parse_claims(x)

    def test_detect_claim_population_drift(self):
        for x in (CLAIMS.replace("|69|120443|","|68|120443|"),
                  CLAIMS.replace("993289","993288"),
                  CLAIMS.replace("948|993289|948","948|993289|947")):
            with self.subTest(text=x),self.assertRaises(tool.Hold):
                tool.parse_claims(x)

    def test_detect_duplicates_and_non_integer(self):
        for x in (CLAIMS+"pending|948|993289|948\n",
                  CLAIMS.replace("|69|120443|","|NAN|120443|"),
                  CLAIMS.replace("993289","-993289")):
            with self.subTest(text=x),self.assertRaises(tool.Hold):
                tool.parse_claims(x)

    def test_one_only_uwolo_denom(self):
        self.assertEqual(tool.parse_bank(BALANCE),826713500000)
        self.assertEqual(tool.parse_bank({"balances":[],"pagination":{}}),0)

    def test_no_fake_token_or_extra_denom(self):
        for x in (
           {"balances":[{"denom":"stake","amount":"5"}],"pagination":{}},
           {"balances":[{"denom":"uwolo","amount":"10"},
                        {"denom":"uwolo","amount":"10"}],"pagination":{}},
           {"balances":[{"denom":"uwolo","amount":"5","sender":"x"}],"pagination":{}},
           {"balances":[{"denom":"uwolo","amount":"NaN"}],"pagination":{}},
           {"balances":[{"denom":"uwolo","amount":"999999999999999999999"}],"pagination":{}},
           {"balances":[{"denom":"uwolo","amount":"1"}]},
        ):
            with self.subTest(case=x),self.assertRaises(tool.Hold):
                tool.parse_bank(x)

    def test_sql_has_explicit_read_only_and_rollback(self):
        self.assertIn("BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY",tool.SQL)
        self.assertIn("SET LOCAL statement_timeout='9000ms'",tool.SQL)
        self.assertIn("ROLLBACK",tool.SQL)
        self.assertIn("COUNT",tool.SQL.upper())
        self.assertIn("c.status='pending'",tool.SQL)

    def test_source_contains_no_financial_service_actions(self):
        code=FILE.read_text()
        for forbidden in ("systemctl start","systemctl stop","sudo -S",
                          "tx bank send","--broadcast-mode","ALTER ROLE",
                          "DROP TABLE", "UPDATE public.pending_wolo_claims",
                          "DELETE FROM", "INSERT INTO"):
            self.assertNotIn(forbidden,code)

    def test_nonrelease_labels_are_hardcoded(self):
        code=FILE.read_text()
        for flag in (
          '"c04_finality_gate_closed":False',
          '"c05_solvency_gate_closed":False',
          '"funded_8094_8095_authorized":False',
          '"independent_reserve_holder_or_signer_control_proven":False',
          '"chain_and_sql_cross_system_atomic":False',
          '"arithmetic_difference_is_not_insolvency_or_actual_unpaid_debt":True',
          '"production_modified":False',
        ):
            self.assertIn(flag,code)

    def test_escrow_source_wallet_is_not_discoverable_dynamic_target(self):
        self.assertEqual(tool.WALLET,"wolo1zygwt232ymc4h2g52yvkntffhmd5alx2kglw7p")
        self.assertEqual(tool.NODE,"http://127.0.0.1:27657/")
        self.assertIn("wolochaind-mainnet-node-prewartrophy",str(tool.EXE))

    def test_private_ledger_receipt_mode_and_exclusive(self):
        with tempfile.TemporaryDirectory(prefix="c05-claim-private-") as t:
            original=tool.RECEIPT
            tool.RECEIPT=Path(t)/"evidence"
            try:
                digest=tool.persist({"hello":"world","c05_solvency_gate_closed":False})
                self.assertEqual(len(digest),64)
                path=tool.RECEIPT/"claims-vs-historic-escrow-single-height.json"
                self.assertEqual(stat.S_IMODE(path.stat().st_mode),0o600)
                self.assertEqual(stat.S_IMODE(tool.RECEIPT.stat().st_mode),0o700)
                self.assertFalse(json.loads(path.read_text())["c05_solvency_gate_closed"])
                with self.assertRaisesRegex(tool.Hold,"ALREADY_EXISTS"):
                    tool.persist({"fake":"new"})
            finally:tool.RECEIPT=original

    def test_forged_receipt_symlink_fails(self):
        with tempfile.TemporaryDirectory(prefix="c05-symlink-") as t:
            p=Path(t)
            (p/"real").mkdir()
            (p/"link").symlink_to(p/"real",target_is_directory=True)
            original=tool.RECEIPT
            tool.RECEIPT=p/"link"
            try:
                with self.assertRaises(tool.Hold):tool.persist({"foo":"bar"})
            finally:tool.RECEIPT=original

    def test_native_rpc_only_read_methods(self):
        with self.assertRaises(tool.Hold):tool.rpc("broadcast_tx_sync",{})
        with self.assertRaises(tool.Hold):tool.rpc("tx",{})

if __name__=="__main__":unittest.main()

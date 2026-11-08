from __future__ import annotations

import unittest
from unittest.mock import patch

from scripts import settlement_c03_auth_definer_reachability_hold as audit


def observation():
    out = []
    for name, digest in sorted(audit.EXPECTED_FUNCTIONS.items()):
        out.append(f"F|{name}|aoe2war_auth_owner|search_path=pg_catalog|{digest}|1")
    for relation in sorted(audit.EXPECTED_WRITABLE_RELATIONS):
        out.append(f"W|{relation}")
    for name, delete, truncate in sorted(audit.EXPECTED_DELETE_TRUNCATE):
        out.append(f"D|{name}|{delete}|{truncate}")
    for col, (insert, update) in sorted(audit.EXPECTED_USER_COLUMNS.items()):
        out.append(f"C|{col}|{insert}|{update}")
    out.extend(["H|0|0|0|0", "R|aoe2war_auth_owner|0|0|0",
                "R|aoe2war_web_prod|0|0|0"])
    return "\n".join(out) + "\n"


class ExactAuthDefinerTests(unittest.TestCase):
    def test_real_catalog_contract_remains_financial_hold(self):
        result = audit.parse(observation())
        self.assertEqual(result["status"], "HOLD_C03_GLOBAL_FINANCIAL_WRITER_FENCE_UNPROVEN")
        self.assertFalse(result["finance_authorized"])
        self.assertFalse(result["database_mutated"])
        self.assertFalse(result["direct_chain_rpc_cli_signers_fenced"])
        self.assertEqual(len(result["auth_definer_function_sha256"]), 3)
        self.assertEqual(result["auth_mutation_triggers"], 0)

    def test_unknown_definer_blocks_even_if_private_schema(self):
        changed = observation() + ("F|custom.secret|root|search_path=pg_catalog|"
                                   + "a" * 64 + "|1\n")
        with self.assertRaisesRegex(audit.Hold, "UNREVIEWED_SECURITY_DEFINER"):
            audit.parse(changed)

    def test_mismatched_real_function_body_digest_blocks(self):
        lines = observation().splitlines()
        lines[0] = lines[0].replace(lines[0].split("|")[4], "a" * 64)
        with self.assertRaisesRegex(audit.Hold, "AUTH_DEFINER_BODY"):
            audit.parse("\n".join(lines))

    def test_different_owner_or_search_path_blocks(self):
        for old, new in (("aoe2war_auth_owner|", "aoe2hd_user|"),
                         ("search_path=pg_catalog", "search_path=public")):
            with self.subTest(change=new):
                with self.assertRaisesRegex(audit.Hold, "AUTH_DEFINER_BODY"):
                    audit.parse(observation().replace(old, new, 1))

    def test_unreviewed_financial_or_public_table_grant_blocks(self):
        with self.assertRaisesRegex(audit.Hold, "FINANCIAL_WRITE_REACHABILITY"):
            audit.parse(observation() + "W|public.bet_wagers\n")

    def test_new_user_column_grant_blocks(self):
        with self.assertRaisesRegex(audit.Hold, "USER_COLUMN_PRIVILEGE"):
            audit.parse(observation() + "C|wallet_address|0|1\n")

    def test_read_write_trigger_blocks(self):
        with self.assertRaisesRegex(audit.Hold, "MUTATION_TRIGGER"):
            audit.parse(observation() + "T|public.users|finance_elevator\n")

    def test_extra_delete_rights_block(self):
        with self.assertRaisesRegex(audit.Hold, "DELETE_TRUNCATE"):
            audit.parse(observation() + "D|public.users|1|0\n")

    def test_role_escalation_create_membership_blocks(self):
        with self.assertRaisesRegex(audit.Hold, "MEMBERSHIP"):
            audit.parse(observation().replace("H|0|0|0|0", "H|0|1|0|0"))

    def test_superuser_or_bypass_blocks(self):
        with self.assertRaisesRegex(audit.Hold, "ROLE_ESCALATION"):
            audit.parse(observation().replace("R|aoe2war_web_prod|0|0|0",
                                              "R|aoe2war_web_prod|0|1|0"))

    def test_fail_closed_when_role_or_query_response_missing(self):
        with self.assertRaisesRegex(audit.Hold, "MEMBERSHIP"):
            audit.parse(observation().replace("H|0|0|0|0\n", ""))
        with self.assertRaisesRegex(audit.Hold, "UNKNOWN_CATALOG"):
            audit.parse(observation() + "UNRECOGNIZED|SOMETHING\n")

    def test_duplicate_catalog_rows_block(self):
        with self.assertRaisesRegex(audit.Hold, "DUPLICATE"):
            audit.parse(observation() + observation().splitlines()[0] + "\n")

    def test_sql_is_read_only_and_no_secrets_or_shell(self):
        q = audit.SQL.upper()
        self.assertIn("REPEATABLE READ READ ONLY", q)
        self.assertIn("ROLLBACK;", q)
        self.assertIn("PG_GET_FUNCTIONDEF", q)
        self.assertIn("TGISINTERNAL", q)
        self.assertIn("ROLSUPER", q)
        self.assertIn("ROLBYPASSRLS", q)
        self.assertNotIn("COMMIT;", q)
        self.assertNotIn("CREATE ROLE", q)
        self.assertNotIn("ALTER ROLE", q)
        self.assertNotIn("PG_TERMINATE_BACKEND", q)

    def test_main_cannot_report_financial_pass(self):
        with patch.object(audit, "inspect", return_value=audit.parse(observation())):
            self.assertEqual(audit.main(), 3)
        with patch.object(audit, "inspect", side_effect=audit.Hold("SCOPE_CHANGED")):
            self.assertEqual(audit.main(), 2)


if __name__ == "__main__":
    unittest.main()

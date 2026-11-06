"""C03 financial dependency inventory is read-only and fails closed."""
import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch

P=Path(__file__).resolve().parents[1]/"scripts/settlement_c03_finance_dependency_hold.py"
spec=importlib.util.spec_from_file_location("c03dep",P)
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

def fixture(db="aoe2hd_db",**overrides):
    role,n=m.DATABASES[db]
    rows=[f"META|{db}|{role}|pg_database_owner|1"]
    rows += [f"TABLE|public.finance_{i}|{role}|r|0|0" for i in range(n)]
    rows += [
      f"SEQUENCE|public.finance_seq|{role}|finance_1",
      f"TRIGGER|public.finance_2|safe_guard|public.bound_guard|postgres|0",
      "VIEW|aoe2war_public_v1.published_claims|postgres",
      "NONFINANCE_OWNER_COUNT|323",
    ]
    if "remove" in overrides:rows.remove(overrides["remove"])
    if "extra" in overrides:rows.append(overrides["extra"])
    return "\n".join(rows)+"\n"

class DependencyTests(unittest.TestCase):
    def test_sql_read_only_and_db_allowlist(self):
        for db in m.DATABASES:
            q=m.query(db)
            self.assertIn("REPEATABLE READ READ ONLY",q)
            self.assertIn("ROLLBACK;",q)
            self.assertNotIn("ALTER TABLE",q)
            self.assertNotIn("REVOKE ",q)
        with self.assertRaises(m.Hold):m.query("postgres")

    def test_legacy_owner_and_dependency_counts(self):
        r=m.parse(fixture(),"aoe2hd_db")
        self.assertEqual(len(r["tables"]),24)
        self.assertEqual(len(r["sequences"]),1)
        self.assertEqual(len(r["triggers"]),1)
        self.assertEqual(len(r["views"]),1)
        self.assertEqual(r["nonfinanceOwnerCount"],[323])

    def test_de_expected_census(self):
        self.assertEqual(len(m.parse(fixture("aoe2de_db"),"aoe2de_db")["tables"]),10)

    def test_duplicate_and_fake_census_refused(self):
        x=fixture()
        for bad in (x+x,x+"TABLE|public.finance_1|aoe2hd_user|r|0|0\n",
                    x.replace("META|aoe2hd_db","META|postgres"),
                    x.replace("META|aoe2hd_db|aoe2hd_user","META|aoe2hd_db|postgres"),
                    x.replace("TABLE|public.finance_0","TABLE|public.x;DROP"),
                    x.replace("NONFINANCE_OWNER_COUNT|323","NONFINANCE_OWNER_COUNT|NaN"),
                    x.replace("TABLE|public.finance_0","WRONG|public.finance_0")):
            with self.subTest(x=bad[:75]),self.assertRaises(m.Hold):m.parse(bad,"aoe2hd_db")

    def test_missing_and_changed_owners_refused(self):
        x=fixture()
        for bad in (x.replace("TABLE|public.finance_0|aoe2hd_user","TABLE|public.finance_0|postgres"),
                    x.replace("TABLE|public.finance_0|aoe2hd_user|r|0|0\n",""),
                    x.replace("META|aoe2hd_db|aoe2hd_user|pg_database_owner|1",
                              "META|aoe2hd_db|aoe2hd_user|pg_database_owner|0"),
                    fixture(remove="NONFINANCE_OWNER_COUNT|323")):
            with self.assertRaises(m.Hold):m.parse(bad,"aoe2hd_db")

    def test_root_local_only(self):
        with patch.object(m.os,"geteuid",return_value=501):
            with self.assertRaises(m.Hold):m.inspect("aoe2hd_db")

    def test_successful_observation_only_returns_hold(self):
        class P:
            returncode=0
            stderr=""
            stdout=fixture()
        with patch.object(m.os,"geteuid",return_value=0),\
             patch.object(m.subprocess,"run",return_value=P()) as run:
            self.assertEqual(len(m.inspect("aoe2hd_db")["tables"]),24)
            self.assertEqual(run.call_args.args[0][:4],
                             ["runuser","-u","postgres","--"])

if __name__=="__main__":
    unittest.main()

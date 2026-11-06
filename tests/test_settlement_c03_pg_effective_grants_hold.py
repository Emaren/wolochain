"""C03 HD/DE effective-write grant observer: adversarial fail-closed tests."""
from __future__ import annotations
from contextlib import redirect_stdout
from io import StringIO
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/settlement_c03_pg_effective_grants_hold.py"


def load():
    spec=importlib.util.spec_from_file_location("c03_effective",SCRIPT)
    m=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class EffectiveGrantsCensusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m=load()

    def rows(self, database="aoe2hd_db", hd_writes=24, de_writes=10):
        result=[]
        for name in sorted(self.m.ROLES):
            exists=1
            total=190 if database=="aoe2hd_db" else 52
            ftotal=24 if database=="aoe2hd_db" else 10
            writes=total if name==(self.m.REQUIRED_LEGACY[database]) else 0
            fw=hd_writes if name=="aoe2hd_user" and database=="aoe2hd_db" else (
                de_writes if name=="aoe2de_user" and database=="aoe2de_db" else 0)
            definers=3 if name=="aoe2war_web_prod" and database=="aoe2hd_db" else 0
            result.append("|".join(map(str,(name,exists,total,ftotal,
                                           writes,fw,definers,0,0))))
        return "\n".join(result)+"\n"

    def test_hd_realistic_legacy_finance_writable(self):
        x=self.m.parse_rows(self.rows(),"aoe2hd_db")
        self.assertEqual(x["aoe2hd_user"]["finance_write_capable_relations"],24)
        self.assertEqual(x["aoe2war_web_prod"]["selected_security_definer_functions_executable"],3)

    def test_de_realistic_legacy_finance_writable(self):
        x=self.m.parse_rows(self.rows("aoe2de_db"),"aoe2de_db")
        self.assertEqual(x["aoe2de_user"]["finance_write_capable_relations"],10)

    def test_valid_observations_still_held(self):
        x=self.m.classify(self.m.parse_rows(self.rows(),"aoe2hd_db"),
                          self.m.parse_rows(self.rows("aoe2de_db"),"aoe2de_db"))
        self.assertEqual(x["status"],"HOLD")
        self.assertTrue(x["legacy_hd_finance_writer_capable"])
        self.assertTrue(x["legacy_de_finance_writer_capable"])
        for key in ("financial_writers_quiesced","database_permissions_changed",
                    "backup_or_restore_authorized","funded_release_authorized",
                    "all_schemas_roles_and_bypass_paths_certified"):
            self.assertIs(x[key],False,key)

    def test_zero_writes_does_not_claim_global_fence(self):
        x=self.m.classify(
            self.m.parse_rows(self.rows(hd_writes=0),"aoe2hd_db"),
            self.m.parse_rows(self.rows("aoe2de_db",de_writes=0),"aoe2de_db"))
        self.assertIs(x["legacy_hd_finance_writer_capable"],False)
        self.assertIs(x["legacy_de_finance_writer_capable"],False)
        self.assertIs(x["financial_writers_quiesced"],False)
        self.assertIs(x["funded_release_authorized"],False)

    def test_duplicate_role_rejected(self):
        s=self.rows()+"aoe2hd_user|1|190|24|190|24|0|0|0\n"
        with self.assertRaises(self.m.Hold):
            self.m.parse_rows(s,"aoe2hd_db")

    def test_missing_required_role_rejected(self):
        s=self.rows().replace("aoe2hd_user|1|","aoe2hd_user|0|")
        with self.assertRaises(self.m.Hold):
            self.m.parse_rows(s,"aoe2hd_db")

    def test_missing_row_rejected(self):
        s="\n".join(self.rows().splitlines()[:-1])
        with self.assertRaises(self.m.Hold):
            self.m.parse_rows(s,"aoe2hd_db")

    def test_unexpected_role_rejected(self):
        with self.assertRaises(self.m.Hold):
            self.m.parse_rows(self.rows()+"postgres|1|190|24|190|24|0|1|1\n","aoe2hd_db")

    def test_negative_and_noninteger_denied(self):
        for val in ("-1","1.2","true","", "0x10"):
            s=self.rows().replace("aoe2hd_user|1|190|",f"aoe2hd_user|1|{val}|")
            with self.subTest(val=val),self.assertRaises(self.m.Hold):
                self.m.parse_rows(s,"aoe2hd_db")

    def test_oversized_and_inconsistent_count_denied(self):
        for bad in ("9"*33, "999999"):
            s=self.rows().replace("aoe2hd_user|1|190|",f"aoe2hd_user|1|{bad}|")
            with self.assertRaises(self.m.Hold):
                self.m.parse_rows(s,"aoe2hd_db")
        s=self.rows().replace("aoe2hd_user|1|190|24|190|24",
                              "aoe2hd_user|1|190|24|190|25")
        with self.assertRaises(self.m.Hold):
            self.m.parse_rows(s,"aoe2hd_db")

    def test_invalid_db_denied(self):
        with self.assertRaises(self.m.Hold):
            self.m.parse_rows(self.rows(),"maintenance")

    def test_only_local_postgres_catalog_read_commands(self):
        m=self.m
        calls=[]
        def fake_run(argv,**kwargs):
            calls.append(argv)
            self.assertEqual(argv[:3],["runuser","-u","postgres"])
            self.assertIn("BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY",argv[-1])
            self.assertIn("ROLLBACK",argv[-1])
            self.assertNotIn("CREATE TABLE",argv[-1])
            return SimpleNamespace(returncode=0,stdout=self.rows(),stderr="")
        with patch.object(m.os,"geteuid",return_value=0),patch.object(m.subprocess,"run",side_effect=fake_run):
            data=m.inspect("aoe2hd_db")
        self.assertEqual(len(calls),1)
        self.assertEqual(data["aoe2hd_user"]["finance_write_capable_relations"],24)

    def test_nonroot_never_runs_psql(self):
        with patch.object(self.m.os,"geteuid",return_value=501),patch.object(
                self.m.subprocess,"run") as proc:
            with self.assertRaises(self.m.Hold):self.m.inspect("aoe2hd_db")
            proc.assert_not_called()

    def test_psql_error_fail_closed(self):
        with patch.object(self.m.os,"geteuid",return_value=0),patch.object(
                self.m.subprocess,"run",return_value=SimpleNamespace(
                    returncode=1,stdout="",stderr="could not connect")):
            with self.assertRaises(self.m.Hold):self.m.inspect("aoe2hd_db")

    def test_cli_passes_no_financial_authority(self):
        with patch.object(self.m,"inspect",side_effect=lambda d:self.m.parse_rows(
                self.rows(d),d)),redirect_stdout(StringIO()) as text:
            self.assertEqual(self.m.main(),3)
        d=json.loads(text.getvalue())
        self.assertEqual(d["status"],"HOLD")
        self.assertFalse(d["funded_release_authorized"])

    def test_cli_error_cannot_return_success(self):
        with patch.object(self.m,"inspect",side_effect=self.m.Hold("failed")),redirect_stdout(StringIO()) as text:
            self.assertEqual(self.m.main(),2)
        self.assertEqual(json.loads(text.getvalue())["status"],"STOP")

if __name__=="__main__":
    unittest.main()

"""C06 read-only HEL1 capture-capacity evaluator; NEVER a backup authority."""
from __future__ import annotations
import importlib.util
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import unittest
from io import StringIO
from contextlib import redirect_stdout
import json

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/settlement_c06_capture_capacity_hold.py"


def load():
    spec = importlib.util.spec_from_file_location("c06_capacity", SCRIPT)
    instance = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(instance)
    return instance


class C06CapacityHoldTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = load()

    def facts(self, **kwargs):
        f = dict(volume_free=18 << 30,
                 disk_sizes={"aoe2hd_db": 11 << 30, "aoe2de_db": 12 << 20},
                 stage_empty=True, snapshot_root_safe=True, same_volume=True,
                 legacy_writers_active=True)
        f.update(kwargs)
        return f

    def report(self, **kwargs):
        return self.m.report(**self.facts(**kwargs))

    def test_prepared_directory_never_authorizes_financial_capture(self):
        o = self.report()
        self.assertEqual(o["status"], "HOLD")
        self.assertEqual(o["upper_bound_for_separately_authorized_max_total_bytes"],
                         17 << 30)
        for flag in ("backup_or_restore_authorized", "financial_release_authorized",
                     "global_financial_writers_fenced", "backup_capture_executed",
                     "offhost_ciphertext_receipt_verified", "backup_size_guaranteed_to_fit"):
            self.assertIs(o[flag], False)

    def test_restoration_loop_is_never_added_to_backup_free(self):
        r = self.report()
        self.assertIs(r["restore_loop_free_excluded_from_capture_capacity"], True)
        self.assertEqual(r["volume_free_bytes"], 18 << 30)
        self.assertNotIn("restore_available_bytes", r)

    def test_tiny_free_space_never_underflows_margin(self):
        x = self.report(volume_free=1)
        self.assertEqual(x["upper_bound_for_separately_authorized_max_total_bytes"], 0)
        self.assertEqual(x["status"], "HOLD")

    def test_equal_one_gib_reserve_has_no_payload_headroom(self):
        self.assertEqual(self.report(volume_free=1 << 30)[
            "upper_bound_for_separately_authorized_max_total_bytes"], 0)

    def test_database_size_cannot_be_used_as_compressed_backup_size(self):
        d = self.report(disk_sizes={"aoe2hd_db": 120 << 30, "aoe2de_db": 10 << 30})
        self.assertIs(d["postgres_database_sizes_sum_is_not_dump_size"], True)
        self.assertIs(d["backup_size_guaranteed_to_fit"], False)

    def test_invalid_negative_and_bool_capacity_rejected(self):
        for x in (-1, True, None, 1.2, "5000"):
            with self.subTest(x=x), self.assertRaises(self.m.Hold):
                self.report(volume_free=x)

    def test_wrong_database_names_and_incomplete_results_rejected(self):
        for x in ({"aoe2hd_db": 42}, {"aoe2hd_db": 42, "wrong": 3},
                  {"aoe2hd_db": 42, "aoe2de_db": 0},
                  {"aoe2hd_db": 42, "aoe2de_db": True}):
            with self.subTest(x=x), self.assertRaises(self.m.Hold):
                self.report(disk_sizes=x)

    def test_parse_pg_database_sizes_exact_and_no_duplicates(self):
        self.assertEqual(self.m.parse_db_sizes("aoe2de_db|123\naoe2hd_db|300\n"),
                         {"aoe2de_db": 123, "aoe2hd_db": 300})
        for text in ("aoe2hd_db|23\n", "aoe2hd_db|23\naoe2hd_db|24\naoe2de_db|8\n",
                     "aoe2hd_db|bad\naoe2de_db|8", "aoe2hd_db|4\naoe2de_db|2\nother|9",
                     "aoe2hd_db|1|2\naoe2de_db|8"):
            with self.subTest(text=text), self.assertRaises(self.m.Hold):
                self.m.parse_db_sizes(text)

    def test_nonboolean_observation_flags_rejected(self):
        for flag in ("stage_empty", "snapshot_root_safe",
                     "same_volume", "legacy_writers_active"):
            with self.subTest(flag=flag), self.assertRaises(self.m.Hold):
                self.report(**{flag: 1})

    def test_inspect_verified_collectors_never_mutate(self):
        m = self.m
        volumes = SimpleNamespace(st_dev=77)
        statfs = SimpleNamespace(f_bavail=18 * (1 << 20), f_frsize=1024)
        active = SimpleNamespace(returncode=0, stdout="active\n")
        pg = SimpleNamespace(returncode=0, stdout="aoe2de_db|1048576\naoe2hd_db|123456789\n")
        def fake_subprocess(command, **kwargs):
            self.assertFalse(any(c in command for c in ("pg_dump", "psql -c DROP", "systemctl stop")))
            if command[0] == "runuser":
                self.assertIn("BEGIN TRANSACTION READ ONLY", command[-1])
                return pg
            self.assertEqual(command[:2], ["systemctl", "show"])
            return active
        with patch.object(m.os, "geteuid", return_value=0), \
             patch.object(m.os.path, "ismount", return_value=True), \
             patch.object(m, "safe_directory", return_value=volumes), \
             patch.object(m.Path, "stat", return_value=volumes), \
             patch.object(m.Path, "iterdir", return_value=iter(())), \
             patch.object(m.os, "statvfs", return_value=statfs), \
             patch.object(m.subprocess, "run", side_effect=fake_subprocess):
            result = m.inspect()
        self.assertEqual(result["volume_free_bytes"], 18 << 30)
        self.assertTrue(result["legacy_producer_services_active"])
        self.assertEqual(result["status"], "HOLD")

    def test_bad_mount_not_attempt_to_run_subprocess(self):
        with patch.object(self.m.os, "geteuid", return_value=0), \
             patch.object(self.m.os.path, "ismount", return_value=False), \
             patch.object(self.m.subprocess, "run") as run:
            with self.assertRaisesRegex(self.m.Hold, "EXPECTED_VOLUME_NOT_MOUNTED"):
                self.m.inspect()
            run.assert_not_called()

    def test_bad_staging_permissions_refuse(self):
        mock_stat = SimpleNamespace(st_mode=0o40755, st_uid=0, st_gid=0)
        with patch.object(self.m.Path, "lstat", return_value=mock_stat):
            with self.assertRaisesRegex(self.m.Hold, "STAGING_DIRECTORY_NOT_0700"):
                self.m.safe_directory(self.m.BACKUPS, private=True)

    def test_nonroot_staging_refused(self):
        mock_stat = SimpleNamespace(st_mode=0o40700, st_uid=501, st_gid=20)
        with patch.object(self.m.Path, "lstat", return_value=mock_stat):
            with self.assertRaisesRegex(self.m.Hold, "DIRECTORY_NOT_ROOT_OWNED"):
                self.m.safe_directory(self.m.BACKUPS, private=True)

    def test_cli_never_returns_success_for_financial_readiness(self):
        with patch.object(self.m, "inspect", return_value=self.report()), \
             redirect_stdout(StringIO()) as captured:
            self.assertEqual(self.m.main(["--inspect"]), 3)
        r = json.loads(captured.getvalue())
        self.assertEqual(r["status"], "HOLD")
        self.assertFalse(r["financial_release_authorized"])
        with patch.object(self.m, "inspect", side_effect=self.m.Hold("FAIL_CLOSED")), \
             redirect_stdout(StringIO()) as blocked:
            self.assertEqual(self.m.main(["--inspect"]), 2)
        self.assertEqual(json.loads(blocked.getvalue())["status"], "STOP")


if __name__ == "__main__":
    unittest.main()

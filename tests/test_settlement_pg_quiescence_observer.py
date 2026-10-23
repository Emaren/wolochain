"""Actual PostgreSQL 16 integration regression. Disposable database ONLY."""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import sys
import unittest
import uuid

import psycopg
from psycopg import sql

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "settlement_pg_quiescence_observer.py"
spec = importlib.util.spec_from_file_location("settlement_pg_quiescence_observer_test", SCRIPT)
obs = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = obs
spec.loader.exec_module(obs)
DSN = os.environ.get("WOLO_TEST_PG_DSN")


@unittest.skipUnless(DSN, "requires isolated PostgreSQL 16 CI DSN")
class GenuinePostgresQuiescence(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.admin = psycopg.connect(DSN, autocommit=True)
        cls.db = cls.admin.info.dbname
        cls.other = None

    @classmethod
    def tearDownClass(cls):
        if cls.other:
            cls.other.close()
        cls.admin.close()

    def tearDown(self):
        if self.other:
            self.other.close()
            self.other = None

    def test_clear_is_only_single_instant_observation(self):
        v = obs.observe(self.admin, (self.db,))
        self.assertEqual((v.other_sessions, v.prepared_transactions), (0, 0))

    def test_idle_open_writer_connection_blocks(self):
        self.other = psycopg.connect(DSN, autocommit=True)
        v = obs.observe(self.admin, (self.db,))
        self.assertGreaterEqual(v.other_sessions, 1)

    def test_prepared_transaction_survives_disconnected_writer(self):
        gid = "wolo_pg_qualify_" + uuid.uuid4().hex
        conn = psycopg.connect(DSN, autocommit=False)
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                cur.execute(sql.SQL("PREPARE TRANSACTION {}").format(sql.Literal(gid)))
        finally:
            conn.close()
        try:
            v = obs.observe(self.admin, (self.db,))
            self.assertEqual(v.other_sessions, 0)
            self.assertGreaterEqual(v.prepared_transactions, 1)
        finally:
            with self.admin.cursor() as cur:
                cur.execute(sql.SQL("ROLLBACK PREPARED {}").format(sql.Literal(gid)))

    def test_underprivileged_monitor_fails_before_querying_activity(self):
        role = "wolo_observer_" + uuid.uuid4().hex[:10]
        password = "disposable-ci-only"
        with self.admin.cursor() as cur:
            cur.execute(sql.SQL("CREATE ROLE {} LOGIN PASSWORD {}").format(
                sql.Identifier(role), sql.Literal(password)))
            cur.execute(sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
                sql.Identifier(self.db), sql.Identifier(role)))
        try:
            from psycopg.conninfo import conninfo_to_dict, make_conninfo
            info = conninfo_to_dict(DSN)
            info.update(user=role, password=password)
            with psycopg.connect(make_conninfo(**info), autocommit=True) as low:
                with self.assertRaisesRegex(obs.Hold, "visibility"):
                    obs.observe(low, (self.db,))
        finally:
            with self.admin.cursor() as cur:
                cur.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(role)))

    def test_invalid_database_inventory_and_non_autocommit_fail(self):
        with self.assertRaisesRegex(obs.Hold, "inventory"):
            obs.observe(self.admin, ("bad-name",))
        with self.assertRaisesRegex(obs.Hold, "absent"):
            obs.observe(self.admin, ("missing_" + uuid.uuid4().hex[:8],))
        self.other = psycopg.connect(DSN, autocommit=False)
        with self.assertRaisesRegex(obs.Hold, "autocommit"):
            obs.observe(self.other, (self.db,))


if __name__ == "__main__":
    unittest.main()

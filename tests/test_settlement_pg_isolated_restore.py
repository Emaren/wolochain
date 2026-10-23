"""Disposable PG16 pg_dump/pg_restore qualification for BOTH mock HD and DE lanes.

TEST HARNESS ONLY. Deliberately uses synthetic journals, not production HD/DE.
A successful run cannot certify actual mainnet restore or producer quiescence.
"""
from __future__ import annotations

import hashlib
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import unittest
import uuid

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "scripts" / "settlement_pg_quiescence_observer.py"
spec = importlib.util.spec_from_file_location("pg_qualify_observer_restore", PATH)
observer = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = observer
spec.loader.exec_module(observer)

DSN = os.environ.get("WOLO_TEST_PG_DSN", "")
ENABLED = os.environ.get("WOLO_PG_DISPOSABLE_ONLY") == "YES"
LOCAL = (
    ENABLED and bool(DSN) and
    conninfo_to_dict(DSN).get("host") == "127.0.0.1" and
    conninfo_to_dict(DSN).get("port") == "55432" and
    conninfo_to_dict(DSN).get("dbname") == "wolo_qualify"
)


@unittest.skipUnless(LOCAL, "requires explicit disposable Docker PG16 CI only")
class TwoDatabaseRestoreRegression(unittest.TestCase):
    def db_connect(self, database):
        params = conninfo_to_dict(DSN)
        params["dbname"] = database
        return psycopg.connect(make_conninfo(**params), autocommit=True)

    def docker(self, *args):
        return subprocess.run(
            ["docker", "exec", "wolo-qualify-postgres", *args],
            check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=30,
        ).stdout

    def test_both_database_archives_restore_without_replaying_or_rewriting(self):
        suffix = uuid.uuid4().hex[:10]
        names = [f"wolo_qualify_{lane}_{suffix}" for lane in ("hd", "de")]
        restores = [f"{name}_restored" for name in names]
        archives = [f"/tmp/{name}.dump" for name in names]
        admin = psycopg.connect(DSN, autocommit=True)
        try:
            for database in names + restores:
                with admin.cursor() as cur:
                    cur.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database)))

            expected = {}
            for lane, database in zip(("hd", "de"), names):
                with self.db_connect(database) as db:
                    with db.cursor() as cur:
                        cur.execute(
                            "CREATE TABLE settlement_journal ("
                            "id BIGSERIAL PRIMARY KEY, operation_id TEXT NOT NULL UNIQUE, "
                            "amount_uwolo BIGINT NOT NULL CHECK(amount_uwolo>0), "
                            "status TEXT NOT NULL CHECK(status IN "
                            "('pending','confirmed','unknown_hold')))"
                        )
                        cur.execute(
                            "INSERT INTO settlement_journal(operation_id,amount_uwolo,status) "
                            "VALUES (%s,%s,%s),(%s,%s,%s)",
                            (lane+":accepted", 100_000_000, "confirmed",
                             lane+":unresolved", 300_000_000, "unknown_hold"),
                        )
                        cur.execute(
                            "SELECT id,operation_id,amount_uwolo,status "
                            "FROM settlement_journal ORDER BY id"
                        )
                        expected[database] = cur.fetchall()

            snapshot = observer.observe(admin, tuple(names))
            self.assertEqual(snapshot.other_sessions, 0)
            self.assertEqual(snapshot.prepared_transactions, 0)

            before_hashes = []
            for database, archive in zip(names, archives):
                self.docker("pg_dump", "-U", "postgres", "--format=custom",
                            "--file="+archive, "--dbname="+database)
                raw = self.docker("sha256sum", archive).decode().split()[0]
                self.assertRegex(raw, r"^[0-9a-f]{64}$")
                before_hashes.append(raw)
            # No original DB is overwritten. Both restores are separate names.
            for archive, restored in zip(archives, restores):
                self.docker("pg_restore", "-U", "postgres", "--exit-on-error",
                            "--no-owner", "--dbname="+restored, archive)
            for original, restored in zip(names, restores):
                with self.db_connect(restored) as db:
                    with db.cursor() as cur:
                        cur.execute(
                            "SELECT id,operation_id,amount_uwolo,status "
                            "FROM settlement_journal ORDER BY id"
                        )
                        self.assertEqual(cur.fetchall(), expected[original])
                        with self.assertRaises(psycopg.errors.CheckViolation):
                            cur.execute(
                                "INSERT INTO settlement_journal(operation_id,amount_uwolo,status) "
                                "VALUES ('corrupt',-1,'confirmed')"
                            )
                        cur.execute(
                            "INSERT INTO settlement_journal(operation_id,amount_uwolo,status) "
                            "VALUES ('after_restore',1,'pending') RETURNING id"
                        )
                        self.assertEqual(cur.fetchone()[0], 3)
            for archive, digest in zip(archives, before_hashes):
                self.assertEqual(self.docker("sha256sum", archive).decode().split()[0], digest)
            print("DISPOSABLE_PG16_DUAL_DATABASE_RESTORE_PASS; FINANCIAL_HARD_HOLD")
        finally:
            # The admin DB is outside the explicit HD/DE fixture inventories.
            for database in restores + names:
                with admin.cursor() as cur:
                    cur.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(
                        sql.Identifier(database)))
            admin.close()
            for archive in archives:
                self.docker("rm", "-f", archive)


if __name__ == "__main__":
    unittest.main()

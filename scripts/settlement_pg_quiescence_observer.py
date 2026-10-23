#!/usr/bin/env python3
"""Read-only PostgreSQL quiescence OBSERVATION; never a release permit.

Does not fence new connections, acquire the shared operator mutex, take
backups, authorize promotion, or certify restore. Independently establish
producer fencing and serialize the ENTIRE financial maintenance operation.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from dataclasses import dataclass


class Hold(RuntimeError):
    pass


DB_NAME = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]{0,62}$")


@dataclass(frozen=True)
class Observation:
    databases: tuple[str, ...]
    other_sessions: int
    prepared_transactions: int


def observe(connection, databases: tuple[str, ...]) -> Observation:
    """One instant's catalog evidence, not proof writers cannot reconnect."""
    if not databases or len(set(databases)) != len(databases) or any(
        not isinstance(name, str) or DB_NAME.fullmatch(name) is None
        for name in databases
    ):
        raise Hold("invalid or duplicate explicit PostgreSQL database inventory")
    if not connection.autocommit:
        raise Hold("monitor requires autocommit to avoid stale statistics snapshots")
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT current_setting('is_superuser')='on', "
            "pg_has_role(current_user,'pg_read_all_stats','USAGE')"
        )
        privilege = cursor.fetchone()
        if privilege is None or len(privilege) != 2 or not any(value is True for value in privilege):
            raise Hold("monitor lacks full pg_stat_activity visibility")
        cursor.execute(
            "SELECT datname FROM pg_catalog.pg_database "
            "WHERE datname = ANY(%s) AND datallowconn",
            (list(databases),),
        )
        existing = {row[0] for row in cursor.fetchall()}
        if existing != set(databases):
            raise Hold("requested database inventory absent or not connectable")
        # Never equate invisible NULL state with idle. Idle sessions also block.
        cursor.execute(
            "SELECT pid, datname, state, usename, backend_type "
            "FROM pg_catalog.pg_stat_activity "
            "WHERE datname=ANY(%s) AND pid <> pg_backend_pid()",
            (list(databases),),
        )
        rows = cursor.fetchall()
        for row in rows:
            if len(row) != 5 or any(value is None for value in row):
                raise Hold("incomplete PostgreSQL session visibility")
        cursor.execute(
            "SELECT count(*) FROM pg_catalog.pg_prepared_xacts "
            "WHERE database=ANY(%s)", (list(databases),)
        )
        prepared_row = cursor.fetchone()
        if prepared_row is None or len(prepared_row) != 1 or prepared_row[0] is None:
            raise Hold("PostgreSQL prepared transaction status unavailable")
        prepared = int(prepared_row[0])
        if prepared < 0:
            raise Hold("invalid PostgreSQL prepared transaction count")
        return Observation(databases, len(rows), prepared)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", action="append", required=True,
                        help="Explicit HD/DE PostgreSQL database; repeat per DB")
    parser.add_argument("--dsn-env", default="WOLO_POSTGRES_MONITOR_DSN",
                        help="Environment variable holding private monitoring DSN")
    args = parser.parse_args(argv)
    if not re.fullmatch(r"[A-Z_][A-Z0-9_]*", args.dsn_env):
        print("HOLD: invalid configuration variable", file=sys.stderr)
        return 3
    dsn = os.environ.get(args.dsn_env)
    if not dsn:
        print("HOLD: monitoring connection unavailable", file=sys.stderr)
        return 3
    try:
        import psycopg
        with psycopg.connect(dsn, autocommit=True, connect_timeout=5) as connection:
            observation = observe(connection, tuple(args.database))
        if observation.other_sessions or observation.prepared_transactions:
            print(f"HOLD: other_sessions={observation.other_sessions} "
                  f"prepared_transactions={observation.prepared_transactions}")
        else:
            print("OBSERVED_ZERO_AT_ONE_INSTANT: not a lock, producer fence, "
                  "backup certification or financial permit")
        print("FINANCIAL_HARD_HOLD: NO RELEASE AUTHORITY")
    except Exception as exc:
        # Never print DSNs, query text, prepared GIDs, identities or credentials.
        print(f"HOLD: PostgreSQL evidence unavailable ({type(exc).__name__})",
              file=sys.stderr)
        print("FINANCIAL_HARD_HOLD: NO RELEASE AUTHORITY")
    return 3


if __name__ == "__main__":
    raise SystemExit(main())

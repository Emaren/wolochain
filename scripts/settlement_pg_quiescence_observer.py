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


def validate_database_inventory(databases: tuple[str, ...]) -> None:
    if not isinstance(databases, tuple) or not databases or any(
        not isinstance(name, str) or DB_NAME.fullmatch(name) is None
        for name in databases
    ) or len(set(databases)) != len(databases):
        raise Hold("invalid or duplicate explicit PostgreSQL database inventory")


def validate_visibility(privilege) -> None:
    if (not isinstance(privilege, (tuple, list)) or len(privilege) != 2 or
            any(type(value) is not bool for value in privilege) or not any(privilege)):
        raise Hold("monitor lacks full pg_stat_activity visibility")


def validate_catalog_observation(databases, privilege, existing, sessions, prepared) -> Observation:
    """Shared driver-independent contract for one complete catalog observation.

    The privileged DB-API observer and protected psql backup path use this same
    refusal policy. Zero counts cannot replace full role and session visibility.
    No observation prevents connections reopening after the query.
    """
    validate_database_inventory(databases)
    validate_visibility(privilege)
    if (not isinstance(existing, (tuple, list)) or
            any(not isinstance(name, str) for name in existing) or
            len(existing) != len(set(existing)) or set(existing) != set(databases)):
        raise Hold("requested database inventory absent or not connectable")
    if not isinstance(sessions, (tuple, list)):
        raise Hold("incomplete PostgreSQL session visibility")
    for row in sessions:
        if (not isinstance(row, (tuple, list)) or len(row) != 5 or
                type(row[0]) is not int or row[0] <= 0 or row[1] not in databases or
                any(not isinstance(value, str) or not value for value in row[1:])):
            raise Hold("incomplete PostgreSQL session visibility")
    if type(prepared) is not int or prepared < 0:
        raise Hold("invalid PostgreSQL prepared transaction count")
    return Observation(databases, len(sessions), prepared)


def observe(connection, databases: tuple[str, ...]) -> Observation:
    """One instant's catalog evidence, not proof writers cannot reconnect."""
    validate_database_inventory(databases)
    if not connection.autocommit:
        raise Hold("monitor requires autocommit to avoid stale statistics snapshots")
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT current_setting('is_superuser')='on', "
            "pg_has_role(current_user,'pg_read_all_stats','USAGE')"
        )
        privilege = cursor.fetchone()
        validate_visibility(privilege)
        cursor.execute(
            "SELECT datname FROM pg_catalog.pg_database "
            "WHERE datname = ANY(%s) AND datallowconn",
            (list(databases),),
        )
        existing = [row[0] for row in cursor.fetchall()]
        # Never equate invisible NULL state with idle. Idle sessions also block.
        cursor.execute(
            "SELECT pid, datname, state, usename, backend_type "
            "FROM pg_catalog.pg_stat_activity "
            "WHERE datname=ANY(%s) AND pid <> pg_backend_pid()",
            (list(databases),),
        )
        rows = cursor.fetchall()
        cursor.execute(
            "SELECT count(*) FROM pg_catalog.pg_prepared_xacts "
            "WHERE database=ANY(%s)", (list(databases),)
        )
        prepared_row = cursor.fetchone()
        if prepared_row is None or len(prepared_row) != 1 or prepared_row[0] is None:
            raise Hold("PostgreSQL prepared transaction status unavailable")
        return validate_catalog_observation(databases, privilege, existing, rows, prepared_row[0])


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

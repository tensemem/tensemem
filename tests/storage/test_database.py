from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

import pytest

from tensemem.core.clock import FrozenClock, format_instant
from tensemem.storage.sqlite import SqliteDatabase


def test_open_applies_init_migration() -> None:
    clock = FrozenClock(datetime(2026, 10, 17, 12, 0, 0, tzinfo=UTC))
    with SqliteDatabase(":memory:", clock=clock, read_pool_size=2) as db:
        version = db.read(lambda c: c.execute("SELECT version FROM schema_migrations").fetchone())
        assert version is not None
        assert version["version"] == 1
        tables = db.read(
            lambda c: {
                row[0]
                for row in c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            }
        )
        assert {"scopes", "episodes", "facts", "jobs", "meta"} <= tables


def test_write_and_read_see_same_data() -> None:
    with SqliteDatabase(":memory:", read_pool_size=2) as db:

        def insert(conn: sqlite3.Connection) -> int:
            conn.execute(
                "INSERT INTO meta(key, value) VALUES (?, ?)",
                ("probe", "abc"),
            )
            conn.commit()
            return 1

        assert db.write(insert) == 1
        value = db.read(lambda c: c.execute("SELECT value FROM meta WHERE key='probe'").fetchone())
        assert value is not None
        assert value["value"] == "abc"


def test_write_exceptions_reach_caller() -> None:
    with SqliteDatabase(":memory:", read_pool_size=1) as db:

        def boom(_conn: sqlite3.Connection) -> None:
            raise RuntimeError("nope")

        with pytest.raises(RuntimeError, match="nope"):
            db.write(boom)


def test_concurrent_reads_and_serialized_writes(tmp_path: Path) -> None:
    path = tmp_path / "t.db"
    with SqliteDatabase(path, read_pool_size=4) as db:

        def seed(conn: sqlite3.Connection) -> None:
            conn.execute("INSERT INTO meta(key, value) VALUES ('n', '0')")
            conn.commit()

        db.write(seed)

        def bump(conn: sqlite3.Connection) -> int:
            conn.execute("BEGIN IMMEDIATE")
            current = int(conn.execute("SELECT value FROM meta WHERE key='n'").fetchone()[0])
            conn.execute("UPDATE meta SET value=? WHERE key='n'", (str(current + 1),))
            conn.commit()
            return current + 1

        def write_once(_i: int) -> int:
            return db.write(bump)

        def read_once(_i: int) -> str:
            row = db.read(lambda c: c.execute("SELECT value FROM meta WHERE key='n'").fetchone())
            assert row is not None
            return str(row[0])

        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(write_once, range(20)))
            reads = list(pool.map(read_once, range(20)))

        assert sorted(results) == list(range(1, 21))
        final_row = db.read(lambda c: c.execute("SELECT value FROM meta WHERE key='n'").fetchone())
        assert final_row is not None
        assert final_row[0] == "20"
        assert all(int(value) <= 20 for value in reads)


def test_reopen_is_idempotent(tmp_path: Path) -> None:
    path = tmp_path / "t.db"
    clock = FrozenClock(datetime(2026, 10, 17, 12, 0, 0, tzinfo=UTC))
    with SqliteDatabase(path, clock=clock, read_pool_size=1) as db:
        count = db.read(lambda c: c.execute("SELECT COUNT(*) FROM schema_migrations").fetchone())[0]
        assert count == 2

    with SqliteDatabase(path, clock=clock, read_pool_size=1) as db:
        count = db.read(lambda c: c.execute("SELECT COUNT(*) FROM schema_migrations").fetchone())[0]
        assert count == 2
        versions = db.read(
            lambda c: [
                row[0]
                for row in c.execute(
                    "SELECT version FROM schema_migrations ORDER BY version"
                ).fetchall()
            ]
        )
        assert versions == [1, 2]
        assert all(
            row[0] == format_instant(clock())
            for row in db.read(
                lambda c: c.execute("SELECT applied_at FROM schema_migrations").fetchall()
            )
        )

    # No pending migration => no backup on reopen.
    assert not path.with_suffix(".db.bak").exists()

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from tensemem.core.clock import FrozenClock, format_instant
from tensemem.storage.sqlite.connection import connect
from tensemem.storage.sqlite.migrate import apply_migrations, pending_migrations


def test_apply_migrations_from_custom_dir(tmp_path: Path) -> None:
    migrations = tmp_path / "migrations"
    migrations.mkdir()
    (migrations / "0001_one.sql").write_text(
        "CREATE TABLE one (id INTEGER PRIMARY KEY);",
        encoding="utf-8",
    )
    (migrations / "0002_two.sql").write_text(
        "CREATE TABLE two (id INTEGER PRIMARY KEY);",
        encoding="utf-8",
    )
    clock = FrozenClock(datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC))
    conn = connect(":memory:", shared_memory_name="migrate-test")
    try:
        assert [v for v, _ in pending_migrations(conn, migrations_dir=migrations)] == [1, 2]
        applied = apply_migrations(conn, clock=clock, migrations_dir=migrations)
        assert applied == [1, 2]
        assert pending_migrations(conn, migrations_dir=migrations) == []
        rows = conn.execute(
            "SELECT version, applied_at FROM schema_migrations ORDER BY version"
        ).fetchall()
        assert [tuple(r) for r in rows] == [
            (1, format_instant(clock())),
            (2, format_instant(clock())),
        ]
        assert apply_migrations(conn, clock=clock, migrations_dir=migrations) == []
    finally:
        conn.close()

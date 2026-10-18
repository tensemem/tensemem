"""Numbered SQL migrations applied automatically on open."""

from __future__ import annotations

import re
import sqlite3
from importlib import resources
from importlib.resources.abc import Traversable
from pathlib import Path

from tensemem.core.clock import Clock, format_instant, utc_now

_MIGRATION_NAME = re.compile(r"^(\d+)_.+\.sql$")


def pending_migrations(
    conn: sqlite3.Connection,
    *,
    migrations_dir: Path | None = None,
) -> list[tuple[int, Traversable | Path]]:
    """Return migration files that have not been applied yet."""
    _ensure_migrations_table(conn)
    applied = {
        int(row[0]) for row in conn.execute("SELECT version FROM schema_migrations").fetchall()
    }
    return [
        (version, path)
        for version, path in _iter_migrations(migrations_dir)
        if version not in applied
    ]


def apply_migrations(
    conn: sqlite3.Connection,
    *,
    clock: Clock = utc_now,
    migrations_dir: Path | None = None,
) -> list[int]:
    """Apply pending ``NNNN_name.sql`` files in order. Returns versions applied.

    Each migration and its ``schema_migrations`` row commit atomically.
    """
    newly: list[int] = []
    for version, path in pending_migrations(conn, migrations_dir=migrations_dir):
        sql = path.read_text(encoding="utf-8")
        # Values are an int and a fixed-format timestamp, so inlining them is safe.
        record = (
            "INSERT INTO schema_migrations(version, applied_at) "
            f"VALUES ({version}, '{format_instant(clock())}');"
        )
        try:
            conn.executescript(f"BEGIN IMMEDIATE;\n{sql}\n{record}\nCOMMIT;")
        except BaseException:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise
        newly.append(version)
    return newly


def _ensure_migrations_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
          version INTEGER PRIMARY KEY,
          applied_at TEXT NOT NULL
        )
        """
    )


def _iter_migrations(migrations_dir: Path | None) -> list[tuple[int, Traversable | Path]]:
    if migrations_dir is None:
        root = resources.files("tensemem.storage.sqlite").joinpath("migrations")
        entries: list[Traversable | Path] = list(root.iterdir())
    else:
        entries = list(migrations_dir.glob("*.sql"))

    found: list[tuple[int, Traversable | Path]] = []
    for entry in entries:
        match = _MIGRATION_NAME.match(entry.name)
        if match is None:
            continue
        found.append((int(match.group(1)), entry))
    return sorted(found, key=lambda item: item[0])

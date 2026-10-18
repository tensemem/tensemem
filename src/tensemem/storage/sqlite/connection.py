"""SQLite connection setup and capability checks (ADR 0003)."""

from __future__ import annotations

import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

MIN_SQLITE_VERSION = (3, 35, 0)

_WRITE_PRAGMAS = (
    "PRAGMA journal_mode = WAL",
    "PRAGMA synchronous = NORMAL",
    "PRAGMA foreign_keys = ON",
    "PRAGMA busy_timeout = 5000",
)

_READ_PRAGMAS = (
    "PRAGMA foreign_keys = ON",
    "PRAGMA busy_timeout = 5000",
    "PRAGMA query_only = ON",
)


class SqliteCapabilityError(RuntimeError):
    """Raised when the bundled SQLite cannot run TenseMem."""


def connect(
    path: str | Path,
    *,
    read_only: bool = False,
    shared_memory_name: str | None = None,
) -> sqlite3.Connection:
    """Open a connection with the PRAGMAs from ADR 0003.

    ``:memory:`` databases use a shared-cache URI so the writer and read pool
    see one database. Pass a unique ``shared_memory_name`` per
    :class:`~tensemem.storage.sqlite.database.SqliteDatabase` instance.
    """
    uri = resolve_uri(path, read_only=read_only, shared_memory_name=shared_memory_name)
    # Autocommit mode: transactions are opened explicitly with immediate_transaction().
    conn = sqlite3.connect(uri, uri=True, check_same_thread=False, isolation_level=None)
    conn.row_factory = sqlite3.Row
    try:
        apply_pragmas(conn, read_only=read_only)
        if not read_only:
            # Capability checks on the writer connection only (need CREATE for FTS probe).
            ensure_capabilities(conn)
    except Exception:
        conn.close()
        raise
    return conn


@contextmanager
def immediate_transaction(conn: sqlite3.Connection) -> Generator[sqlite3.Connection]:
    """``BEGIN IMMEDIATE`` ... ``COMMIT``, rolling back on any failure.

    A failed ``COMMIT`` also rolls back so the shared writer connection is not
    left mid-transaction for the next caller.
    """
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except BaseException:
        _rollback_quietly(conn)
        raise
    try:
        conn.execute("COMMIT")
    except BaseException:
        _rollback_quietly(conn)
        raise


def _rollback_quietly(conn: sqlite3.Connection) -> None:
    try:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
    except sqlite3.Error:
        pass


def apply_pragmas(conn: sqlite3.Connection, *, read_only: bool) -> None:
    pragmas = _READ_PRAGMAS if read_only else _WRITE_PRAGMAS
    for statement in pragmas:
        conn.execute(statement)


def ensure_capabilities(conn: sqlite3.Connection) -> None:
    """Require SQLite ≥ 3.35 and FTS5."""
    version = sqlite3.sqlite_version_info
    if version < MIN_SQLITE_VERSION:
        msg = (
            f"TenseMem needs SQLite {'.'.join(map(str, MIN_SQLITE_VERSION))}+ "
            f"(found {sqlite3.sqlite_version})"
        )
        raise SqliteCapabilityError(msg)

    try:
        conn.execute(
            "CREATE VIRTUAL TABLE IF NOT EXISTS _tensemem_fts_probe "
            "USING fts5(text, content='', tokenize='porter unicode61')"
        )
        conn.execute("DROP TABLE IF EXISTS _tensemem_fts_probe")
    except sqlite3.OperationalError as exc:
        msg = "TenseMem needs SQLite built with FTS5"
        raise SqliteCapabilityError(msg) from exc


def resolve_uri(
    path: str | Path,
    *,
    read_only: bool = False,
    shared_memory_name: str | None = None,
) -> str:
    text = str(path)
    if text == ":memory:":
        name = shared_memory_name or "tensemem"
        return f"file:{name}?mode=memory&cache=shared"
    if text.startswith("file:"):
        return text

    resolved = Path(text).expanduser().resolve()
    if read_only:
        if not resolved.exists():
            msg = f"database does not exist: {resolved}"
            raise FileNotFoundError(msg)
        return f"file:{resolved.as_posix()}?mode=ro"
    resolved.parent.mkdir(parents=True, exist_ok=True)
    return f"file:{resolved.as_posix()}"

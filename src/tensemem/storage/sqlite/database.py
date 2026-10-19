"""SQLite database with one writer thread and a read pool (ADR 0003)."""

from __future__ import annotations

import atexit
import queue
import shutil
import sqlite3
import threading
import time
import uuid
from collections.abc import Callable
from concurrent.futures import Future
from pathlib import Path
from typing import Any, TypeVar, cast

from tensemem.core.clock import Clock, format_instant, utc_now
from tensemem.core.ontology import Ontology
from tensemem.storage.sqlite.connection import connect, immediate_transaction, rollback_quietly
from tensemem.storage.sqlite.meta import ensure_fence_tag
from tensemem.storage.sqlite.migrate import apply_migrations, pending_migrations
from tensemem.storage.sqlite.seed import seed_ontology

T = TypeVar("T")

_SENTINEL = object()
_WorkItem = tuple[Callable[[sqlite3.Connection], Any], Future[Any]]
_TABLE_LOCK_ATTEMPTS = 50
_TABLE_LOCK_SLEEP = 0.01


class SqliteDatabase:
    """Owns the write connection and a pool of read-only connections."""

    def __init__(
        self,
        path: str | Path = ":memory:",
        *,
        clock: Clock = utc_now,
        read_pool_size: int = 4,
        backup_before_migrate: bool = True,
    ) -> None:
        if read_pool_size < 1:
            msg = "read_pool_size must be >= 1"
            raise ValueError(msg)

        self._path = path
        self._clock = clock
        self._closed = False
        self._write_queue: queue.Queue[_WorkItem | object] = queue.Queue()
        self._read_pool: queue.Queue[sqlite3.Connection] = queue.Queue()
        self._memory_name = f"tensemem-{uuid.uuid4().hex}" if str(path) == ":memory:" else None

        self._writer = connect(path, read_only=False, shared_memory_name=self._memory_name)
        pending = pending_migrations(self._writer)
        already_versioned = (
            self._writer.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0] > 0
        )
        if backup_before_migrate and pending and already_versioned:
            # Fresh databases skip backup; upgrades of existing files get a .bak copy.
            _backup_if_file(path)
        apply_migrations(self._writer, clock=clock)
        ensure_fence_tag(self._writer)

        for _ in range(read_pool_size):
            self._read_pool.put(connect(path, read_only=True, shared_memory_name=self._memory_name))

        self._thread = threading.Thread(
            target=self._writer_loop,
            name="tensemem-sqlite-writer",
            daemon=True,
        )
        self._thread.start()
        atexit.register(self.close)

    @property
    def path(self) -> str | Path:
        return self._path

    def now(self) -> str:
        """Current time from the injected clock, formatted for storage."""
        return format_instant(self._clock())

    def write(self, fn: Callable[[sqlite3.Connection], T]) -> T:
        """Run ``fn`` on the writer thread and return its result."""
        self._ensure_open()
        future: Future[Any] = Future()
        self._write_queue.put((fn, future))
        return cast(T, future.result())

    def transaction(self, fn: Callable[[sqlite3.Connection], T]) -> T:
        """Like :meth:`write`, but inside ``BEGIN IMMEDIATE``; rolls back if ``fn`` raises."""

        def run(conn: sqlite3.Connection) -> T:
            with immediate_transaction(conn):
                return fn(conn)

        return self.write(run)

    def seed(self, ontology: Ontology) -> None:
        """Optionally load predicates and entities from an app-owned ontology."""
        self.transaction(lambda conn: seed_ontology(conn, ontology, now=self.now()))

    def backup_to(self, dest: str | Path) -> None:
        """Copy this database to ``dest`` using SQLite's online backup API."""
        target = Path(dest).expanduser()
        if str(self._path) not in {":memory:", ""} and not str(self._path).startswith("file:"):
            source = Path(self._path).expanduser().resolve()
            if target.resolve() == source:
                msg = "backup destination is the open database"
                raise ValueError(msg)
        target.parent.mkdir(parents=True, exist_ok=True)

        def run(conn: sqlite3.Connection) -> None:
            dst = sqlite3.connect(str(target))
            try:
                conn.backup(dst)
                dst.commit()
            finally:
                dst.close()

        self.write(run)

    def read(self, fn: Callable[[sqlite3.Connection], T]) -> T:
        """Borrow a read-only connection, run ``fn``, and return it to the pool.

        In-memory DBs use shared cache, so a reader can see ``SQLITE_LOCKED``
        while the writer holds ``BEGIN IMMEDIATE``. ``busy_timeout`` does not
        retry that; we do.
        """
        self._ensure_open()
        conn = self._read_pool.get()
        try:
            return _retry_table_lock(fn, conn)
        finally:
            self._read_pool.put(conn)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._write_queue.put(_SENTINEL)
        self._thread.join(timeout=5)
        while True:
            try:
                conn = self._read_pool.get_nowait()
            except queue.Empty:
                break
            conn.close()
        self._writer.close()

    def __enter__(self) -> SqliteDatabase:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def _writer_loop(self) -> None:
        while True:
            item = self._write_queue.get()
            if item is _SENTINEL:
                return
            fn, future = cast(_WorkItem, item)
            if future.set_running_or_notify_cancel():
                try:
                    # Shared-cache readers can lock a table; busy_timeout does not retry that.
                    future.set_result(_retry_table_lock(fn, self._writer, rollback_on_lock=True))
                except BaseException as extra:
                    rollback_quietly(self._writer)
                    # Propagate every failure (including cancel) to the waiting caller.
                    future.set_exception(extra)

    def _ensure_open(self) -> None:
        if self._closed:
            msg = "SqliteDatabase is closed"
            raise RuntimeError(msg)


def _retry_table_lock(
    fn: Callable[[sqlite3.Connection], T],
    conn: sqlite3.Connection,
    *,
    rollback_on_lock: bool = False,
) -> T:
    last: sqlite3.OperationalError | None = None
    for _ in range(_TABLE_LOCK_ATTEMPTS):
        try:
            return fn(conn)
        except sqlite3.OperationalError as extra:
            if not _is_table_locked(extra):
                raise
            last = extra
            if rollback_on_lock:
                rollback_quietly(conn)
            time.sleep(_TABLE_LOCK_SLEEP)
    assert last is not None
    raise last


def _is_table_locked(exc: sqlite3.OperationalError) -> bool:
    code = getattr(exc, "sqlite_errorcode", None)
    if code == sqlite3.SQLITE_LOCKED:
        return True
    return "database table is locked" in str(exc)


def _backup_if_file(path: str | Path) -> None:
    text = str(path)
    if text == ":memory:" or text.startswith("file:"):
        return
    resolved = Path(text).expanduser()
    if not resolved.exists() or resolved.stat().st_size == 0:
        return
    backup = resolved.with_suffix(resolved.suffix + ".bak")
    shutil.copy2(resolved, backup)

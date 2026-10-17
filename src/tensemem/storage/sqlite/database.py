"""SQLite database with one writer thread and a read pool (ADR 0003)."""

from __future__ import annotations

import atexit
import queue
import shutil
import sqlite3
import threading
import uuid
from collections.abc import Callable
from concurrent.futures import Future
from pathlib import Path
from typing import Any, TypeVar, cast

from tensemem.core.clock import Clock, utc_now
from tensemem.storage.sqlite.connection import connect
from tensemem.storage.sqlite.migrate import apply_migrations, pending_migrations

T = TypeVar("T")

_SENTINEL = object()
_WorkItem = tuple[Callable[[sqlite3.Connection], Any], Future[Any]]


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

    def write(self, fn: Callable[[sqlite3.Connection], T]) -> T:
        """Run ``fn`` on the writer thread and return its result."""
        self._ensure_open()
        future: Future[Any] = Future()
        self._write_queue.put((fn, future))
        return cast(T, future.result())

    def read(self, fn: Callable[[sqlite3.Connection], T]) -> T:
        """Borrow a read-only connection, run ``fn``, and return it to the pool."""
        self._ensure_open()
        conn = self._read_pool.get()
        try:
            return fn(conn)
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
                    future.set_result(fn(self._writer))
                except BaseException as exc:
                    # Propagate every failure (including cancel) to the waiting caller.
                    future.set_exception(exc)

    def _ensure_open(self) -> None:
        if self._closed:
            msg = "SqliteDatabase is closed"
            raise RuntimeError(msg)


def _backup_if_file(path: str | Path) -> None:
    text = str(path)
    if text == ":memory:" or text.startswith("file:"):
        return
    resolved = Path(text).expanduser()
    if not resolved.exists() or resolved.stat().st_size == 0:
        return
    backup = resolved.with_suffix(resolved.suffix + ".bak")
    shutil.copy2(resolved, backup)

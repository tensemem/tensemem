"""Storage backend protocol (ADR 0003, ADR 0020)."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol, Self, TypeVar, runtime_checkable

from tensemem.core.ontology import Ontology

T = TypeVar("T")


@runtime_checkable
class StorageBackend(Protocol):
    """Store lifecycle. Work-unit type is backend-private."""

    def now(self) -> str:
        """Current time from the store clock, formatted for storage."""
        ...

    def write(self, fn: Callable[[Any], T]) -> T:
        """Run ``fn`` on the writer and return its result."""
        ...

    def transaction(self, fn: Callable[[Any], T]) -> T:
        """Like :meth:`write`, rolled back if ``fn`` raises."""
        ...

    def read(self, fn: Callable[[Any], T]) -> T:
        """Run ``fn`` on a reader and return its result."""
        ...

    def seed(self, ontology: Ontology) -> None:
        """Load predicates and entities from an app-owned ontology."""
        ...

    def backup_to(self, dest: str | Path) -> None:
        """Copy this store to ``dest``."""
        ...

    def close(self) -> None:
        """Release writer and reader resources. Idempotent."""
        ...

    def __enter__(self) -> Self: ...

    def __exit__(self, *exc: object) -> None: ...


@runtime_checkable
class SqliteBackend(Protocol):
    """``StorageBackend`` whose work units are ``sqlite3.Connection``.

    ``Memory.store=`` and the extract worker require this until repositories
    stop taking a connection.
    """

    def now(self) -> str: ...

    def write(self, fn: Callable[[sqlite3.Connection], T]) -> T: ...

    def transaction(self, fn: Callable[[sqlite3.Connection], T]) -> T: ...

    def read(self, fn: Callable[[sqlite3.Connection], T]) -> T: ...

    def seed(self, ontology: Ontology) -> None: ...

    def backup_to(self, dest: str | Path) -> None: ...

    def close(self) -> None: ...

    def __enter__(self) -> Self: ...

    def __exit__(self, *exc: object) -> None: ...

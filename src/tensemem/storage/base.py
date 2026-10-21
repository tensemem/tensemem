"""Storage backend protocol (ADR 0003, ADR 0020)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol, Self, TypeVar, runtime_checkable

from tensemem.core.ontology import Ontology

T = TypeVar("T")


@runtime_checkable
class StorageBackend(Protocol):
    """Store lifecycle. Work units are backend-private (SQLite uses a connection)."""

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

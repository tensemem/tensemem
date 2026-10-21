"""Conformance for StorageBackend. Register another factory when a second store lands."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

import pytest

from tensemem import Memory
from tensemem.core.clock import FrozenClock, format_instant
from tensemem.core.models import PredicateSpec
from tensemem.core.ontology import Ontology
from tensemem.storage import SqliteDatabase, StorageBackend


class BackendFactory(Protocol):
    def __call__(
        self,
        path: str | Path = ":memory:",
        *,
        clock: FrozenClock | None = None,
    ) -> StorageBackend: ...


def sqlite_backend(
    path: str | Path = ":memory:",
    *,
    clock: FrozenClock | None = None,
) -> SqliteDatabase:
    return SqliteDatabase(
        path,
        clock=clock or FrozenClock(datetime(2026, 10, 21, 12, 0, 0, tzinfo=UTC)),
        read_pool_size=1,
    )


BACKENDS: dict[str, BackendFactory] = {"sqlite": sqlite_backend}


@pytest.fixture(params=list(BACKENDS))
def backend_factory(request: pytest.FixtureRequest) -> BackendFactory:
    return BACKENDS[str(request.param)]


def test_sqlite_satisfies_storage_backend() -> None:
    with sqlite_backend() as db:
        assert isinstance(db, StorageBackend)


def test_now_uses_store_clock(backend_factory: BackendFactory) -> None:
    clock = FrozenClock(datetime(2026, 10, 21, 9, 30, 0, tzinfo=UTC))
    with backend_factory(clock=clock) as db:
        assert db.now() == format_instant(clock())


def test_memory_set_roundtrip_on_injected_store(backend_factory: BackendFactory) -> None:
    with backend_factory() as db:
        mem = Memory(store=db, start_worker=False)
        mem.register_predicate("lives_in")
        mem.set(user_id="u1", predicate="lives_in", value="Delhi")
        assert mem.state("u1").values["lives_in"] == "Delhi"
        mem.close()
        again = Memory(store=db, start_worker=False)
        assert again.state("u1").values["lives_in"] == "Delhi"
        again.close()


def test_seed_is_visible_to_memory(backend_factory: BackendFactory) -> None:
    with backend_factory() as db:
        db.seed(Ontology(predicates=(PredicateSpec(name="hometown"),)))
        mem = Memory(store=db, start_worker=False)
        mem.set(user_id="u1", predicate="hometown", value="Pune")
        assert mem.state("u1").values["hometown"] == "Pune"
        mem.close()


def test_raising_transaction_leaves_facts(backend_factory: BackendFactory) -> None:
    with backend_factory() as db:
        mem = Memory(store=db, start_worker=False)
        mem.register_predicate("lives_in")
        mem.set(user_id="u1", predicate="lives_in", value="Delhi")
        mem.close()

        def boom(_work: object) -> None:
            raise RuntimeError("nope")

        with pytest.raises(RuntimeError, match="nope"):
            db.transaction(boom)
        again = Memory(store=db, start_worker=False)
        assert again.state("u1").values["lives_in"] == "Delhi"
        again.close()


def test_backup_to_restores_facts(backend_factory: BackendFactory, tmp_path: Path) -> None:
    dest = tmp_path / "copy.db"
    with backend_factory() as db:
        mem = Memory(store=db, start_worker=False)
        mem.register_predicate("lives_in")
        mem.set(user_id="u1", predicate="lives_in", value="Delhi")
        mem.close()
        db.backup_to(dest)
    with backend_factory(dest) as restored:
        mem = Memory(store=restored, start_worker=False)
        assert mem.state("u1").values["lives_in"] == "Delhi"
        mem.close()


def test_close_rejects_later_writes(backend_factory: BackendFactory) -> None:
    db = backend_factory()
    db.close()
    with pytest.raises(RuntimeError):
        db.write(lambda _work: None)

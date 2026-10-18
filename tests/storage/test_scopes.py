import sqlite3

import pytest

from tensemem.core.errors import RegistryConflictError
from tensemem.core.models import Scope, ScopeKey
from tensemem.storage.sqlite import SqliteDatabase
from tensemem.storage.sqlite.entities import (
    add_entity_alias,
    ensure_global_entity,
    resolve_entity,
)
from tensemem.storage.sqlite.scopes import get_or_create_scope, get_scope


def test_get_or_create_scope_is_idempotent(db: SqliteDatabase) -> None:
    key = ScopeKey(user_id="u1")

    first = _scope(db, key)
    second = _scope(db, key)

    assert first == second
    assert first.applied_seq == 0
    assert first.projection_version == 1


def test_agents_get_separate_scopes(db: SqliteDatabase) -> None:
    coach = _scope(db, ScopeKey(user_id="u1", agent_id="coach"))
    tutor = _scope(db, ScopeKey(user_id="u1", agent_id="tutor"))

    assert coach.id != tutor.id
    assert coach.self_entity_id != tutor.self_entity_id


def test_get_scope_reads_without_creating(db: SqliteDatabase) -> None:
    key = ScopeKey(user_id="u1")
    assert db.read(lambda c: get_scope(c, key)) is None

    created = _scope(db, key)

    assert db.read(lambda c: get_scope(c, key)) == created


def test_global_entity_aliases_resolve_in_any_scope(db: SqliteDatabase) -> None:
    scope = _scope(db, ScopeKey(user_id="u1"))

    def seed_postgres(conn: sqlite3.Connection) -> int:
        entity_id = ensure_global_entity(conn, "PostgreSQL", kind="tech", now=db.now())
        add_entity_alias(conn, "PostgreSQL", entity_id)
        add_entity_alias(conn, "postgres", entity_id)
        add_entity_alias(conn, "pg", entity_id)
        return entity_id

    entity_id = db.transaction(seed_postgres)
    postgres = db.read(lambda c: resolve_entity(c, "postgres", scope_id=scope.id))
    pg = db.read(lambda c: resolve_entity(c, "PG", scope_id=scope.id))

    assert postgres == entity_id
    assert pg == entity_id


def test_duplicate_global_entity_alias_is_rejected(db: SqliteDatabase) -> None:
    def clash(conn: sqlite3.Connection) -> None:
        a = ensure_global_entity(conn, "PostgreSQL", kind="tech", now=db.now())
        b = ensure_global_entity(conn, "Python", kind="tech", now=db.now())
        add_entity_alias(conn, "pg", a)
        with pytest.raises(RegistryConflictError, match="already points"):
            add_entity_alias(conn, "PG", b)

    db.transaction(clash)


def test_scope_alias_overrides_global(db: SqliteDatabase) -> None:
    scope = _scope(db, ScopeKey(user_id="u1"))

    def setup(conn: sqlite3.Connection) -> None:
        entity_id = ensure_global_entity(conn, "PostgreSQL", kind="tech", now=db.now())
        add_entity_alias(conn, "pg", entity_id)
        add_entity_alias(conn, "pg", scope.self_entity_id, scope_id=scope.id)

    db.transaction(setup)

    assert db.read(lambda c: resolve_entity(c, "pg", scope_id=scope.id)) == scope.self_entity_id


def _scope(db: SqliteDatabase, key: ScopeKey) -> Scope:
    def run(conn: sqlite3.Connection) -> Scope:
        return get_or_create_scope(conn, key, now=db.now())

    return db.transaction(run)

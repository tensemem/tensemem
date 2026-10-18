import sqlite3

from tensemem.core.models import Scope, ScopeKey
from tensemem.storage.sqlite import SqliteDatabase
from tensemem.storage.sqlite.entities import add_entity_alias, resolve_entity
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

    postgres = db.read(lambda c: resolve_entity(c, "postgres", scope_id=scope.id))
    pg = db.read(lambda c: resolve_entity(c, "PG", scope_id=scope.id))

    assert postgres is not None
    assert postgres == pg


def test_scope_alias_overrides_global(db: SqliteDatabase) -> None:
    scope = _scope(db, ScopeKey(user_id="u1"))

    def alias_pg_to_self(conn: sqlite3.Connection) -> None:
        add_entity_alias(conn, "pg", scope.self_entity_id, scope_id=scope.id)

    db.transaction(alias_pg_to_self)

    assert db.read(lambda c: resolve_entity(c, "pg", scope_id=scope.id)) == scope.self_entity_id


def _scope(db: SqliteDatabase, key: ScopeKey) -> Scope:
    def run(conn: sqlite3.Connection) -> Scope:
        return get_or_create_scope(conn, key, now=db.now())

    return db.transaction(run)

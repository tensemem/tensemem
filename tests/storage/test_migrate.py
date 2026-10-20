from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from importlib import resources
from pathlib import Path

from tensemem import Memory
from tensemem.core.clock import FrozenClock, format_instant
from tensemem.core.models import Cardinality, ExtractedOp, Mutation, OpKind, PredicateSpec, ScopeKey
from tensemem.core.normalize import normalize_value
from tensemem.storage.sqlite import SqliteDatabase
from tensemem.storage.sqlite.connection import connect, immediate_transaction
from tensemem.storage.sqlite.episodes import insert_episode
from tensemem.storage.sqlite.facts import ApplyContext, apply_mutations
from tensemem.storage.sqlite.migrate import apply_migrations, pending_migrations
from tensemem.storage.sqlite.registry import register_predicate
from tensemem.storage.sqlite.scopes import get_or_create_scope


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


def test_open_applies_newer_migrations_to_v2_fixture(tmp_path: Path) -> None:
    path = tmp_path / "legacy.db"
    migrations = tmp_path / "v2"
    migrations.mkdir()
    packaged = resources.files("tensemem.storage.sqlite").joinpath("migrations")
    for name in ("0001_init.sql", "0002_entity_alias_global_unique.sql"):
        sql = packaged.joinpath(name).read_text(encoding="utf-8")
        (migrations / name).write_text(sql, encoding="utf-8")
    conn = connect(path)
    try:
        apply_migrations(conn, migrations_dir=migrations)
        versions = [
            row[0] for row in conn.execute("SELECT version FROM schema_migrations ORDER BY version")
        ]
        assert versions == [1, 2]
        now = "2026-10-17T12:00:00.000000Z"
        with immediate_transaction(conn):
            key = ScopeKey(user_id="u1")
            scope = get_or_create_scope(conn, key, now=now)
            spec = PredicateSpec(name="lives_in", cardinality=Cardinality.ONE)
            predicate = register_predicate(conn, spec, now=now)
            seq, _ = insert_episode(
                conn, scope_id=scope.id, content="SET user.lives_in=Delhi", now=now
            )
            op = ExtractedOp(
                subject="user",
                predicate="lives_in",
                object="Delhi",
                op=OpKind.SET,
                evidence="SET user.lives_in=Delhi",
            )
            ctx = ApplyContext(
                scope_id=scope.id,
                episode_id=seq,
                recorded_seq=seq,
                subject_id=scope.self_entity_id,
                predicate_id=predicate.id,
                object_norm=normalize_value("Delhi"),
                cardinality=Cardinality.ONE,
            )
            apply_mutations(
                conn,
                [(Mutation(kind="insert_active", op=op, reason="no_active_fact"), ctx)],
                now=now,
            )
    finally:
        conn.close()

    with SqliteDatabase(path) as db:
        versions = db.read(_schema_versions)
        assert versions == [1, 2, 3, 4]
    with Memory(path) as mem:
        assert mem.state(user_id="u1").values == {"lives_in": "Delhi"}
        hits = mem.search(user_id="u1", query="Delhi")
        assert any("Delhi" in hit.text for hit in hits.hits)


def _schema_versions(conn: sqlite3.Connection) -> list[int]:
    rows = conn.execute("SELECT version FROM schema_migrations ORDER BY version")
    return [int(row[0]) for row in rows]

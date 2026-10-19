import sqlite3

import pytest

from tensemem.core.errors import ApplyError
from tensemem.core.ids import new_ulid, ulid_timestamp_ms
from tensemem.core.models import (
    Cardinality,
    ExtractedOp,
    FactStatus,
    Mutation,
    OpKind,
    PredicateSpec,
    ScopeKey,
)
from tensemem.core.normalize import normalize_value
from tensemem.core.resolver import IncomingOp, Snapshot, resolve
from tensemem.storage.sqlite import SqliteDatabase
from tensemem.storage.sqlite.facts import ApplyContext, ApplyResult, apply_mutations, get_fact
from tensemem.storage.sqlite.registry import register_predicate
from tensemem.storage.sqlite.scopes import get_or_create_scope


def test_insert_active_writes_fact_event_edge_and_fts(db: SqliteDatabase) -> None:
    world = _world(db)
    mutation = Mutation(
        kind="insert_active",
        op=_op("Bangalore"),
        reason="no_active_fact",
    )

    result = _apply(db, mutation, world.ctx)

    assert result.public_id is not None
    ulid_timestamp_ms(result.public_id)
    fact = db.read(lambda conn: get_fact(conn, result.public_id or ""))
    assert fact is not None
    assert fact["status"] == FactStatus.ACTIVE
    assert fact["object_norm"] == "bangalore"
    assert fact["recorded_seq"] == 1
    assert _events(db, int(fact["id"])) == [(None, "ACTIVE", "no_active_fact")]
    assert _edges(db, int(fact["id"])) == [("EVIDENCED_BY", world.ctx.episode_id)]
    hits = db.read(
        lambda conn: conn.execute(
            "SELECT text FROM facts_fts WHERE facts_fts MATCH 'bangalore'"
        ).fetchall()
    )
    assert len(hits) == 1


def test_drop_writes_nothing(db: SqliteDatabase) -> None:
    world = _world(db)
    mutation = Mutation(kind="drop", op=_op("Pune"), reason="hypothetical")

    result = _apply(db, mutation, world.ctx)

    assert result.public_id is None
    count = db.read(lambda conn: conn.execute("SELECT COUNT(*) AS n FROM facts").fetchone()["n"])
    assert count == 0


def test_second_active_in_the_same_slot_is_rejected(db: SqliteDatabase) -> None:
    world = _world(db)
    first = Mutation(kind="insert_active", op=_op("Bangalore"), reason="no_active_fact")
    second = Mutation(kind="insert_active", op=_op("Pune"), reason="no_active_fact")

    def write(conn: sqlite3.Connection) -> None:
        apply_mutations(conn, [(first, world.ctx)], now=db.now())
        apply_mutations(conn, [(second, world.ctx)], now=db.now())

    with pytest.raises(ApplyError, match="ACTIVE"):
        db.transaction(write)


def test_cannot_change_a_fact_that_is_already_closed(db: SqliteDatabase) -> None:
    world = _world(db)
    inserted = _apply(
        db,
        Mutation(kind="insert_active", op=_op("Bangalore"), reason="no_active_fact"),
        world.ctx,
    )
    _apply(
        db,
        Mutation(
            kind="retract",
            op=_op("Bangalore", op=OpKind.RETRACT),
            reason="retract",
            target_fact_id=inserted.public_id,
        ),
        world.ctx,
    )

    with pytest.raises(ApplyError, match="not ACTIVE"):
        _apply(
            db,
            Mutation(
                kind="reinforce",
                op=_op("Bangalore"),
                reason="same_value",
                target_fact_id=inserted.public_id,
            ),
            world.ctx,
        )


def test_cannot_target_a_fact_from_another_scope(db: SqliteDatabase) -> None:
    first = _world(db, user_id="u1")
    second = _world(db, user_id="u2")
    inserted = _apply(
        db,
        Mutation(kind="insert_active", op=_op("Bangalore"), reason="no_active_fact"),
        first.ctx,
    )

    with pytest.raises(ApplyError, match="does not match the apply context"):
        _apply(
            db,
            Mutation(
                kind="retract",
                op=_op("Bangalore", op=OpKind.RETRACT),
                reason="retract",
                target_fact_id=inserted.public_id,
            ),
            second.ctx,
        )


def test_supersede_then_reject(db: SqliteDatabase) -> None:
    world = _world(db)
    inserted = _apply(
        db,
        Mutation(kind="insert_active", op=_op("Bangalore"), reason="no_active_fact"),
        world.ctx,
    )
    assert inserted.public_id is not None

    superseded = db.transaction(
        lambda conn: apply_mutations(
            conn,
            [
                (
                    Mutation(
                        kind="supersede",
                        op=_op("Pune", confidence=0.9),
                        reason="newer_value",
                        target_fact_id=inserted.public_id,
                    ),
                    world.ctx.model_copy(update={"object_norm": "pune"}),
                )
            ],
            now=db.now(),
        )[0]
    )
    old = db.read(lambda conn: get_fact(conn, inserted.public_id or ""))
    new = db.read(lambda conn: get_fact(conn, superseded.public_id or ""))
    assert old is not None
    assert new is not None
    assert old["status"] == FactStatus.SUPERSEDED
    assert old["superseded_by"] == new["id"]
    assert new["status"] == FactStatus.ACTIVE
    assert ("SUPERSEDES", int(old["id"])) in _edges(db, int(new["id"]))

    denied = db.transaction(
        lambda conn: apply_mutations(
            conn,
            [
                (
                    Mutation(
                        kind="reject",
                        op=_op("Pune", op=OpKind.DENY),
                        reason="deny",
                        target_fact_id=superseded.public_id,
                    ),
                    world.ctx.model_copy(update={"object_norm": "pune"}),
                )
            ],
            now=db.now(),
        )[0]
    )
    rejected = db.read(lambda conn: get_fact(conn, denied.public_id or ""))
    restored = db.read(lambda conn: get_fact(conn, inserted.public_id or ""))
    assert rejected is not None
    assert rejected["status"] == FactStatus.REJECTED
    assert restored is not None
    assert restored["status"] == FactStatus.ACTIVE
    assert restored["superseded_by"] is None
    claims = db.read(
        lambda conn: conn.execute(
            "SELECT object_norm, until_seq FROM rejected_claims WHERE scope_id = ?",
            (world.ctx.scope_id,),
        ).fetchall()
    )
    assert [(row["object_norm"], row["until_seq"]) for row in claims] == [("pune", 1)]


def test_resolve_then_apply_reinforces_a_pending_insert(db: SqliteDatabase) -> None:
    world = _world(db)
    first = IncomingOp(op=_op("Bangalore"), object_norm="bangalore", cardinality=Cardinality.ONE)
    second = IncomingOp(
        op=_op("Bangalore", is_confirmation=True, confidence=0.8),
        object_norm="bangalore",
        cardinality=Cardinality.ONE,
    )
    mutations = resolve((first, second), Snapshot())
    assert [item.kind for item in mutations] == ["insert_active", "reinforce"]
    assert mutations[1].target_fact_id == "pending:user:lives_in:bangalore"

    results = db.transaction(
        lambda conn: apply_mutations(
            conn,
            [(mutations[0], world.ctx), (mutations[1], world.ctx)],
            now=db.now(),
        )
    )
    assert results[0].public_id == results[1].public_id
    fact = db.read(lambda conn: get_fact(conn, results[0].public_id or ""))
    assert fact is not None
    assert fact["status"] == FactStatus.ACTIVE
    # 1 - (1-1.0)*(1-0.4) stays 1.0; confirmation still records a second event.
    assert fact["confidence"] == pytest.approx(1.0)
    assert _events(db, int(fact["id"])) == [
        (None, "ACTIVE", "no_active_fact"),
        ("ACTIVE", "ACTIVE", "same_value"),
    ]


def test_retract_closes_the_active_fact(db: SqliteDatabase) -> None:
    world = _world(db)
    inserted = _apply(
        db,
        Mutation(kind="insert_active", op=_op("Bangalore"), reason="no_active_fact"),
        world.ctx,
    )
    db.transaction(
        lambda conn: apply_mutations(
            conn,
            [
                (
                    Mutation(
                        kind="retract",
                        op=_op("Bangalore", op=OpKind.RETRACT),
                        reason="retract",
                        target_fact_id=inserted.public_id,
                    ),
                    world.ctx,
                )
            ],
            now=db.now(),
        )
    )
    fact = db.read(lambda conn: get_fact(conn, inserted.public_id or ""))
    assert fact is not None
    assert fact["status"] == FactStatus.RETRACTED


def test_many_values_can_both_be_active(db: SqliteDatabase) -> None:
    def setup(conn: sqlite3.Connection) -> tuple[ApplyContext, ApplyContext]:
        scope = get_or_create_scope(conn, ScopeKey(user_id="u1"), now=db.now())
        predicate = register_predicate(
            conn, PredicateSpec(name="uses_language", cardinality=Cardinality.MANY), now=db.now()
        )
        episode_id = _insert_episode(conn, scope.id, now=db.now())
        rust = ApplyContext(
            scope_id=scope.id,
            episode_id=episode_id,
            recorded_seq=1,
            subject_id=scope.self_entity_id,
            predicate_id=predicate.id,
            object_norm="rust",
            cardinality=Cardinality.MANY,
        )
        go = rust.model_copy(update={"object_norm": "go"})
        return rust, go

    rust_ctx, go_ctx = db.transaction(setup)
    db.transaction(
        lambda conn: apply_mutations(
            conn,
            [
                (
                    Mutation(
                        kind="insert_active",
                        op=ExtractedOp(
                            subject="user", predicate="uses_language", object="Rust", op=OpKind.ADD
                        ),
                        reason="no_active_fact",
                    ),
                    rust_ctx,
                ),
                (
                    Mutation(
                        kind="insert_active",
                        op=ExtractedOp(
                            subject="user", predicate="uses_language", object="Go", op=OpKind.ADD
                        ),
                        reason="no_active_fact",
                    ),
                    go_ctx,
                ),
            ],
            now=db.now(),
        )
    )
    statuses = db.read(
        lambda conn: [
            row["status"]
            for row in conn.execute(
                "SELECT status FROM facts WHERE predicate_id = ? ORDER BY object_norm",
                (rust_ctx.predicate_id,),
            ).fetchall()
        ]
    )
    assert statuses == [FactStatus.ACTIVE, FactStatus.ACTIVE]


def test_historical_insert_leaves_active_in_place(db: SqliteDatabase) -> None:
    world = _world(db)
    active_op = _op("Bangalore", valid_from="2026-03-01T00:00:00.000000Z")
    older_op = _op("Delhi", valid_from="2024-01-01T00:00:00.000000Z")
    inserted = _apply(
        db, Mutation(kind="insert_active", op=active_op, reason="no_active_fact"), world.ctx
    )
    historical = _apply(
        db, Mutation(kind="insert_historical", op=older_op, reason="older_than_active"), world.ctx
    )

    current = db.read(lambda conn: get_fact(conn, inserted.public_id or ""))
    past = db.read(lambda conn: get_fact(conn, historical.public_id or ""))
    assert current is not None
    assert past is not None
    assert current["status"] == FactStatus.ACTIVE
    assert past["status"] == FactStatus.SUPERSEDED
    assert past["valid_to"] == current["valid_from"]


def _apply(db: SqliteDatabase, mutation: Mutation, ctx: ApplyContext) -> ApplyResult:
    return db.transaction(lambda conn: apply_mutations(conn, [(mutation, ctx)], now=db.now())[0])


class _World:
    def __init__(self, ctx: ApplyContext) -> None:
        self.ctx = ctx


def _world(db: SqliteDatabase, *, user_id: str = "u1") -> _World:
    def setup(conn: sqlite3.Connection) -> ApplyContext:
        scope = get_or_create_scope(conn, ScopeKey(user_id=user_id), now=db.now())
        predicate = register_predicate(
            conn, PredicateSpec(name="lives_in", cardinality=Cardinality.ONE), now=db.now()
        )
        episode_id = _insert_episode(conn, scope.id, now=db.now())
        return ApplyContext(
            scope_id=scope.id,
            episode_id=episode_id,
            recorded_seq=1,
            subject_id=scope.self_entity_id,
            predicate_id=predicate.id,
            object_norm="bangalore",
            cardinality=Cardinality.ONE,
        )

    return _World(db.transaction(setup))


def _op(
    city: str,
    *,
    op: OpKind = OpKind.SET,
    confidence: float = 1.0,
    valid_from: str | None = None,
    is_confirmation: bool = False,
) -> ExtractedOp:
    return ExtractedOp(
        subject="user",
        predicate="lives_in",
        object=city,
        op=op,
        confidence=confidence,
        valid_from=valid_from,
        is_confirmation=is_confirmation,
    )


def _insert_episode(conn: sqlite3.Connection, scope_id: int, *, now: str) -> int:
    row = conn.execute(
        """
        INSERT INTO episodes (
          public_id, scope_id, kind, role, content, occurred_at, ingested_at, content_hash
        ) VALUES (?, ?, 'explicit_op', 'user', 'I live in Bangalore', ?, ?, ?)
        RETURNING id
        """,
        (new_ulid(), scope_id, now, now, normalize_value("I live in Bangalore")),
    ).fetchone()
    return int(row["id"])


def _events(db: SqliteDatabase, fact_id: int) -> list[tuple[str | None, str, str]]:
    rows = db.read(
        lambda conn: conn.execute(
            "SELECT from_status, to_status, reason FROM fact_events WHERE fact_id = ? ORDER BY id",
            (fact_id,),
        ).fetchall()
    )
    return [(row["from_status"], row["to_status"], row["reason"]) for row in rows]


def _edges(db: SqliteDatabase, fact_id: int) -> list[tuple[str, int]]:
    rows = db.read(
        lambda conn: conn.execute(
            "SELECT kind, dst_id FROM fact_edges WHERE src_fact_id = ? ORDER BY kind",
            (fact_id,),
        ).fetchall()
    )
    return [(row["kind"], int(row["dst_id"])) for row in rows]

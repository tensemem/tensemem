"""Write resolver mutations into facts, edges, events, and rejected claims.

Functions take a connection and never commit; callers own the transaction.
``reject`` records the claim and marks the fact; re-resolving the slot so a
superseded value can return to ACTIVE is a later slice (ADR 0008).
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable

from pydantic import BaseModel, ConfigDict, Field

from tensemem.core.errors import ApplyError
from tensemem.core.ids import new_ulid
from tensemem.core.models import (
    Cardinality,
    EdgeKind,
    ExtractedOp,
    FactSource,
    FactStatus,
    Mutation,
    MutationKind,
)
from tensemem.core.slots import slot_key


class ApplyContext(BaseModel):
    """Resolved ids the writer needs; the pipeline fills this in before apply."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    scope_id: int
    episode_id: int
    recorded_seq: int = Field(ge=0)
    subject_id: int
    predicate_id: int
    object_norm: str
    cardinality: Cardinality
    object_entity_id: int | None = None
    source: FactSource = FactSource.EXTRACTED
    extractor_version: str | None = None


class ApplyResult(BaseModel):
    """The row ``apply`` touched, if any. ``drop`` leaves both ids empty."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: MutationKind
    reason: str
    public_id: str | None = None
    fact_id: int | None = None


def apply_mutations(
    conn: sqlite3.Connection,
    items: Iterable[tuple[Mutation, ApplyContext]],
    *,
    now: str,
) -> tuple[ApplyResult, ...]:
    """Write ``items`` in order. Later mutations can target facts this batch inserted."""
    pending: dict[str, str] = {}
    return tuple(
        _apply_one(conn, mutation, ctx, now=now, pending=pending) for mutation, ctx in items
    )


def get_fact(conn: sqlite3.Connection, public_id: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM facts WHERE public_id = ?", (public_id,)).fetchone()


def _apply_one(
    conn: sqlite3.Connection,
    mutation: Mutation,
    ctx: ApplyContext,
    *,
    now: str,
    pending: dict[str, str],
) -> ApplyResult:
    kind = mutation.kind
    if kind == "drop":
        return ApplyResult(kind=kind, reason=mutation.reason)
    if kind == "insert_active":
        return _insert(conn, mutation, ctx, status=FactStatus.ACTIVE, now=now, pending=pending)
    if kind == "insert_candidate":
        return _insert(conn, mutation, ctx, status=FactStatus.CANDIDATE, now=now, pending=pending)
    if kind == "insert_historical":
        return _insert_historical(conn, mutation, ctx, now=now, pending=pending)
    if kind == "reinforce":
        return _reinforce(conn, mutation, ctx, now=now, pending=pending)
    if kind == "supersede":
        return _supersede(conn, mutation, ctx, now=now, pending=pending)
    if kind == "retract":
        return _close(conn, mutation, ctx, to=FactStatus.RETRACTED, now=now, pending=pending)
    if kind == "reject":
        return _reject(conn, mutation, ctx, now=now, pending=pending)
    msg = f"unknown mutation kind: {kind}"
    raise ApplyError(msg)


def _insert(
    conn: sqlite3.Connection,
    mutation: Mutation,
    ctx: ApplyContext,
    *,
    status: FactStatus,
    now: str,
    pending: dict[str, str],
    valid_to: str | None = None,
    invalidated_at: str | None = None,
) -> ApplyResult:
    public_id = new_ulid()
    key = _slot(ctx)
    try:
        row = conn.execute(
            """
            INSERT INTO facts (
              public_id, scope_id, subject_id, predicate_id, object_text,
              object_entity_id, object_norm, slot_key, status, modality,
              confidence, source, valid_from, valid_precision, valid_to,
              recorded_at, invalidated_at, last_confirmed_at, source_episode_id,
              recorded_seq, extractor_version
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            RETURNING id
            """,
            (
                public_id,
                ctx.scope_id,
                ctx.subject_id,
                ctx.predicate_id,
                mutation.op.object,
                ctx.object_entity_id,
                ctx.object_norm,
                key,
                status.value,
                mutation.op.modality.value,
                mutation.op.confidence,
                ctx.source.value,
                mutation.op.valid_from,
                mutation.op.valid_precision.value,
                valid_to,
                now,
                invalidated_at,
                now,
                ctx.episode_id,
                ctx.recorded_seq,
                ctx.extractor_version,
            ),
        ).fetchone()
    except sqlite3.IntegrityError as exc:
        msg = f"cannot insert {status.value} fact in slot {key}: {exc}"
        raise ApplyError(msg) from exc
    fact_id = int(row["id"])
    _remember(pending, mutation.op, ctx, public_id)
    _record_event(
        conn,
        fact_id,
        from_status=None,
        to_status=status,
        reason=mutation.reason,
        episode_id=ctx.episode_id,
        at=now,
    )
    _add_edge(conn, fact_id, ctx.episode_id, EdgeKind.EVIDENCED_BY, now)
    _index_fact(conn, fact_id, mutation.op)
    return ApplyResult(
        kind=mutation.kind, reason=mutation.reason, public_id=public_id, fact_id=fact_id
    )


def _insert_historical(
    conn: sqlite3.Connection,
    mutation: Mutation,
    ctx: ApplyContext,
    *,
    now: str,
    pending: dict[str, str],
) -> ApplyResult:
    active = conn.execute(
        "SELECT valid_from FROM facts WHERE slot_key = ? AND status = 'ACTIVE'",
        (_slot(ctx),),
    ).fetchone()
    valid_to = None if active is None else active["valid_from"]
    return _insert(
        conn,
        mutation,
        ctx,
        status=FactStatus.SUPERSEDED,
        now=now,
        pending=pending,
        valid_to=valid_to,
    )


def _reinforce(
    conn: sqlite3.Connection,
    mutation: Mutation,
    ctx: ApplyContext,
    *,
    now: str,
    pending: dict[str, str],
) -> ApplyResult:
    row = _require_target(conn, mutation, ctx, pending)
    blended = _blend(
        float(row["confidence"]),
        mutation.op.confidence,
        confirmation=mutation.op.is_confirmation,
    )
    conn.execute(
        "UPDATE facts SET confidence = ?, last_confirmed_at = ? WHERE id = ?",
        (blended, now, row["id"]),
    )
    _record_event(
        conn,
        int(row["id"]),
        from_status=FactStatus.ACTIVE,
        to_status=FactStatus.ACTIVE,
        reason=mutation.reason,
        episode_id=ctx.episode_id,
        at=now,
    )
    _add_edge(conn, int(row["id"]), ctx.episode_id, EdgeKind.EVIDENCED_BY, now)
    return ApplyResult(
        kind=mutation.kind,
        reason=mutation.reason,
        public_id=row["public_id"],
        fact_id=int(row["id"]),
    )


def _supersede(
    conn: sqlite3.Connection,
    mutation: Mutation,
    ctx: ApplyContext,
    *,
    now: str,
    pending: dict[str, str],
) -> ApplyResult:
    old = _require_target(conn, mutation, ctx, pending)
    conn.execute(
        """
        UPDATE facts
        SET status = 'SUPERSEDED', valid_to = ?, invalidated_at = ?
        WHERE id = ?
        """,
        (mutation.op.valid_from, now, old["id"]),
    )
    _record_event(
        conn,
        int(old["id"]),
        from_status=FactStatus(old["status"]),
        to_status=FactStatus.SUPERSEDED,
        reason=mutation.reason,
        episode_id=ctx.episode_id,
        at=now,
    )
    inserted = _insert(conn, mutation, ctx, status=FactStatus.ACTIVE, now=now, pending=pending)
    if inserted.fact_id is None:
        msg = "supersede inserted an ACTIVE fact without an id"
        raise ApplyError(msg)
    conn.execute("UPDATE facts SET superseded_by = ? WHERE id = ?", (inserted.fact_id, old["id"]))
    _add_edge(conn, inserted.fact_id, int(old["id"]), EdgeKind.SUPERSEDES, now)
    return inserted


def _close(
    conn: sqlite3.Connection,
    mutation: Mutation,
    ctx: ApplyContext,
    *,
    to: FactStatus,
    now: str,
    pending: dict[str, str],
) -> ApplyResult:
    row = _require_target(conn, mutation, ctx, pending)
    conn.execute(
        """
        UPDATE facts
        SET status = ?, valid_to = ?, invalidated_at = ?
        WHERE id = ?
        """,
        (to.value, mutation.op.valid_from, now, row["id"]),
    )
    _record_event(
        conn,
        int(row["id"]),
        from_status=FactStatus(row["status"]),
        to_status=to,
        reason=mutation.reason,
        episode_id=ctx.episode_id,
        at=now,
    )
    _add_edge(conn, int(row["id"]), ctx.episode_id, EdgeKind.EVIDENCED_BY, now)
    return ApplyResult(
        kind=mutation.kind,
        reason=mutation.reason,
        public_id=row["public_id"],
        fact_id=int(row["id"]),
    )


def _reject(
    conn: sqlite3.Connection,
    mutation: Mutation,
    ctx: ApplyContext,
    *,
    now: str,
    pending: dict[str, str],
) -> ApplyResult:
    result = _close(conn, mutation, ctx, to=FactStatus.REJECTED, now=now, pending=pending)
    conn.execute(
        """
        INSERT INTO rejected_claims (
          scope_id, subject_id, predicate_id, object_norm, until_seq, episode_id, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            ctx.scope_id,
            ctx.subject_id,
            ctx.predicate_id,
            ctx.object_norm,
            ctx.recorded_seq,
            ctx.episode_id,
            now,
        ),
    )
    return result


def _require_target(
    conn: sqlite3.Connection,
    mutation: Mutation,
    ctx: ApplyContext,
    pending: dict[str, str],
) -> sqlite3.Row:
    raw = mutation.target_fact_id
    if raw is None:
        msg = f"{mutation.kind} needs a target fact"
        raise ApplyError(msg)
    public_id = pending.get(raw, raw)
    row = get_fact(conn, public_id)
    if row is None:
        msg = f"{mutation.kind} target {raw!r} does not exist"
        raise ApplyError(msg)
    if row["status"] != FactStatus.ACTIVE.value:
        msg = f"{mutation.kind} target {raw!r} is {row['status']}, not ACTIVE"
        raise ApplyError(msg)
    # Object may differ on ONE supersede; scope/subject/predicate must still match.
    if (
        row["scope_id"] != ctx.scope_id
        or row["subject_id"] != ctx.subject_id
        or row["predicate_id"] != ctx.predicate_id
    ):
        msg = f"{mutation.kind} target {raw!r} does not match the apply context"
        raise ApplyError(msg)
    return row


def _remember(pending: dict[str, str], op: ExtractedOp, ctx: ApplyContext, public_id: str) -> None:
    pending[f"pending:{op.subject}:{op.predicate}:{ctx.object_norm}"] = public_id
    pending[public_id] = public_id


def _slot(ctx: ApplyContext) -> str:
    return slot_key(
        scope_id=ctx.scope_id,
        subject_id=ctx.subject_id,
        predicate_id=ctx.predicate_id,
        cardinality=ctx.cardinality,
        object_norm=ctx.object_norm,
    )


def _blend(current: float, incoming: float, *, confirmation: bool) -> float:
    weight = incoming * 0.5 if confirmation else incoming
    return 1.0 - (1.0 - current) * (1.0 - weight)


def _record_event(
    conn: sqlite3.Connection,
    fact_id: int,
    *,
    from_status: FactStatus | None,
    to_status: FactStatus,
    reason: str,
    episode_id: int,
    at: str,
) -> None:
    conn.execute(
        """
        INSERT INTO fact_events (fact_id, from_status, to_status, reason, episode_id, at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            fact_id,
            None if from_status is None else from_status.value,
            to_status.value,
            reason,
            episode_id,
            at,
        ),
    )


def _add_edge(
    conn: sqlite3.Connection, src_fact_id: int, dst_id: int, kind: EdgeKind, now: str
) -> None:
    conn.execute(
        """
        INSERT OR IGNORE INTO fact_edges (src_fact_id, dst_id, kind, created_at)
        VALUES (?, ?, ?, ?)
        """,
        (src_fact_id, dst_id, kind.value, now),
    )


def _index_fact(conn: sqlite3.Connection, fact_id: int, op: ExtractedOp) -> None:
    text = " ".join((op.subject, op.predicate, op.object))
    conn.execute("INSERT INTO facts_fts(rowid, text) VALUES (?, ?)", (fact_id, text))

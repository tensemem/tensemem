"""Optional embedding BLOBs keyed by owner and model (ADR 0004)."""

from __future__ import annotations

import sqlite3
import struct
from collections.abc import Sequence

from tensemem.security.scrub import scrub
from tensemem.storage.sqlite.facts import ApplyResult, search_text
from tensemem.storage.sqlite.jobs import enqueue_embed
from tensemem.storage.sqlite.snapshot import load_fact_view, to_fact_view


def pack_vector(values: Sequence[float]) -> bytes:
    return struct.pack(f"<{len(values)}f", *values)


def unpack_vector(blob: bytes) -> tuple[float, ...]:
    count = len(blob) // 4
    return struct.unpack(f"<{count}f", blob)


def upsert_embedding(
    conn: sqlite3.Connection,
    *,
    owner_kind: str,
    owner_id: int,
    model: str,
    vector: Sequence[float],
) -> None:
    conn.execute(
        """
        INSERT INTO embeddings(owner_kind, owner_id, model, dim, vector)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(owner_kind, owner_id, model) DO UPDATE SET
          dim = excluded.dim,
          vector = excluded.vector
        """,
        (owner_kind, owner_id, model, len(vector), pack_vector(vector)),
    )


def fact_vectors(
    conn: sqlite3.Connection, scope_id: int, model: str
) -> dict[str, tuple[float, ...]]:
    rows = conn.execute(
        """
        SELECT f.public_id, e.vector
        FROM embeddings e
        JOIN facts f ON f.id = e.owner_id
        WHERE e.owner_kind = 'fact' AND e.model = ? AND f.scope_id = ?
        """,
        (model, scope_id),
    ).fetchall()
    return {str(row["public_id"]): unpack_vector(row["vector"]) for row in rows}


def episode_vectors(
    conn: sqlite3.Connection, scope_id: int, model: str
) -> dict[str, tuple[float, ...]]:
    rows = conn.execute(
        """
        SELECT ep.public_id, e.vector
        FROM embeddings e
        JOIN episodes ep ON ep.id = e.owner_id
        WHERE e.owner_kind = 'episode' AND e.model = ? AND ep.scope_id = ?
        """,
        (model, scope_id),
    ).fetchall()
    return {str(row["public_id"]): unpack_vector(row["vector"]) for row in rows}


def delete_scope_embeddings(conn: sqlite3.Connection, scope_id: int) -> None:
    conn.execute(
        """
        DELETE FROM embeddings
        WHERE owner_kind = 'fact' AND owner_id IN (
          SELECT id FROM facts WHERE scope_id = ?
        )
        """,
        (scope_id,),
    )
    conn.execute(
        """
        DELETE FROM embeddings
        WHERE owner_kind = 'episode' AND owner_id IN (
          SELECT id FROM episodes WHERE scope_id = ?
        )
        """,
        (scope_id,),
    )


def enqueue_fact_embeds(
    conn: sqlite3.Connection,
    *,
    scope_id: int,
    now: str,
    results: Sequence[ApplyResult],
) -> None:
    for result in results:
        if result.fact_id is None or result.public_id is None:
            continue
        row = load_fact_view(conn, result.public_id)
        if row is None:
            continue
        view = to_fact_view(row)
        enqueue_embed(
            conn,
            scope_id=scope_id,
            now=now,
            owner_kind="fact",
            owner_id=result.fact_id,
            text=scrub(search_text(view.subject, view.predicate, view.object)),
        )


def enqueue_episode_embed(
    conn: sqlite3.Connection,
    *,
    scope_id: int,
    now: str,
    episode_id: int,
    text: str,
) -> None:
    enqueue_embed(
        conn,
        scope_id=scope_id,
        now=now,
        owner_kind="episode",
        owner_id=episode_id,
        text=scrub(text),
    )

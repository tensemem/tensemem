"""FTS5 lookup over facts and episodes."""

from __future__ import annotations

import sqlite3

from tensemem.core.models import FactStatus, FactView
from tensemem.core.retrieve import EpisodeHit, fts_query
from tensemem.storage.sqlite.snapshot import FACT_SELECT, to_fact_view


def search_facts(
    conn: sqlite3.Connection,
    scope_id: int,
    query: str,
    *,
    statuses: tuple[FactStatus, ...] = (FactStatus.ACTIVE,),
    limit: int = 32,
) -> tuple[tuple[FactView, float], ...]:
    """Facts in ``scope_id`` matching ``query``, with raw BM25 rank (lower is better)."""
    match = fts_query(query)
    if match is None:
        return ()
    placeholders = ",".join("?" * len(statuses))
    head, tail = FACT_SELECT.split("FROM facts f", 1)
    sql = (
        head
        + ", bm25(facts_fts) AS rank FROM facts f"
        + tail
        + f"""
        JOIN facts_fts ON facts_fts.rowid = f.id
        WHERE f.scope_id = ?
          AND f.status IN ({placeholders})
          AND facts_fts MATCH ?
        ORDER BY rank
        LIMIT ?
        """
    )
    params: list[object] = [scope_id, *[status.value for status in statuses], match, limit]
    try:
        rows = conn.execute(sql, params).fetchall()
    except sqlite3.OperationalError:
        return ()
    return tuple((to_fact_view(row), float(row["rank"])) for row in rows)


def search_episodes(
    conn: sqlite3.Connection,
    scope_id: int,
    query: str,
    *,
    limit: int = 8,
) -> tuple[EpisodeHit, ...]:
    match = fts_query(query)
    if match is None:
        return ()
    try:
        rows = conn.execute(
            """
            SELECT e.public_id, e.content, e.occurred_at, bm25(episodes_fts) AS rank
            FROM episodes e
            JOIN episodes_fts ON episodes_fts.rowid = e.id
            WHERE e.scope_id = ?
              AND e.kind = 'message'
              AND e.status IN ('PROCESSED', 'SKIPPED')
              AND episodes_fts MATCH ?
            ORDER BY rank
            LIMIT ?
            """,
            (scope_id, match, limit),
        ).fetchall()
    except sqlite3.OperationalError:
        return ()
    return tuple(
        EpisodeHit(
            public_id=str(row["public_id"]),
            content=str(row["content"]),
            occurred_at=str(row["occurred_at"]),
            rank=float(row["rank"]),
        )
        for row in rows
    )


def list_processed_episodes(
    conn: sqlite3.Connection, scope_id: int, *, limit: int = 8
) -> tuple[EpisodeHit, ...]:
    rows = conn.execute(
        """
        SELECT public_id, content, occurred_at
        FROM episodes
        WHERE scope_id = ? AND kind = 'message' AND status IN ('PROCESSED', 'SKIPPED')
        ORDER BY id DESC
        LIMIT ?
        """,
        (scope_id, limit),
    ).fetchall()
    return tuple(
        EpisodeHit(
            public_id=str(row["public_id"]),
            content=str(row["content"]),
            occurred_at=str(row["occurred_at"]),
        )
        for row in rows
    )

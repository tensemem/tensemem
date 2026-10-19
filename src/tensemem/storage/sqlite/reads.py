"""Read helpers for state, history, explain, and forget."""

from __future__ import annotations

import sqlite3

from tensemem.core.models import (
    ExplainResult,
    FactEventView,
    FactSet,
    FactStatus,
    Scope,
)
from tensemem.storage.sqlite.embeddings import delete_scope_embeddings
from tensemem.storage.sqlite.entities import subject_label
from tensemem.storage.sqlite.episodes import unindex_episode
from tensemem.storage.sqlite.facts import search_text, unindex_fact
from tensemem.storage.sqlite.snapshot import freshness_for, list_facts, to_fact_view

_STATE_STATUSES = (FactStatus.ACTIVE,)
_HISTORY_STATUSES = (FactStatus.ACTIVE, FactStatus.SUPERSEDED, FactStatus.RETRACTED)


def read_state(conn: sqlite3.Connection, scope: Scope | None) -> FactSet:
    if scope is None:
        return FactSet(facts=(), freshness=freshness_for(conn, None))
    facts = list_facts(conn, scope.id, statuses=_STATE_STATUSES)
    return FactSet(facts=tuple(facts), freshness=freshness_for(conn, scope))


def read_history(
    conn: sqlite3.Connection, scope: Scope | None, *, predicate: str | None = None
) -> FactSet:
    if scope is None:
        return FactSet(facts=(), freshness=freshness_for(conn, None))
    facts = list_facts(conn, scope.id, statuses=_HISTORY_STATUSES, predicate=predicate)
    return FactSet(facts=tuple(facts), freshness=freshness_for(conn, scope))


def read_explain(conn: sqlite3.Connection, row: sqlite3.Row) -> ExplainResult:
    fact = to_fact_view(row)
    events = [
        FactEventView(
            from_status=None if event["from_status"] is None else FactStatus(event["from_status"]),
            to_status=FactStatus(event["to_status"]),
            reason=event["reason"],
            episode_id=event["episode_id"],
            at=event["at"],
        )
        for event in conn.execute(
            """
            SELECT from_status, to_status, reason, episode_id, at
            FROM fact_events WHERE fact_id = ? ORDER BY id
            """,
            (row["id"],),
        ).fetchall()
    ]
    evidence = [
        int(edge["dst_id"])
        for edge in conn.execute(
            """
            SELECT dst_id FROM fact_edges
            WHERE src_fact_id = ? AND kind = 'EVIDENCED_BY' ORDER BY created_at
            """,
            (row["id"],),
        ).fetchall()
    ]
    superseded_by = None
    if row["superseded_by"] is not None:
        linked = conn.execute(
            "SELECT public_id FROM facts WHERE id = ?", (row["superseded_by"],)
        ).fetchone()
        if linked is not None:
            superseded_by = str(linked["public_id"])
    return ExplainResult(
        fact=fact,
        events=tuple(events),
        evidence_episode_ids=tuple(evidence),
        superseded_by=superseded_by,
    )


def wipe_projection(conn: sqlite3.Connection, scope_id: int) -> None:
    """Delete facts and jobs for ``scope_id``; keep episodes, entities, and claims.

    ``rebuild()`` calls this inside the same transaction that replays the log, so
    readers never observe a half-rebuilt projection.
    """
    rows = conn.execute(
        """
        SELECT f.id, f.subject_id, f.object_text, p.name AS predicate
        FROM facts f
        JOIN predicates p ON p.id = f.predicate_id
        WHERE f.scope_id = ?
        """,
        (scope_id,),
    ).fetchall()
    for row in rows:
        text = search_text(
            subject_label(conn, int(row["subject_id"])),
            row["predicate"],
            row["object_text"],
        )
        unindex_fact(conn, int(row["id"]), text)
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
        DELETE FROM fact_edges WHERE src_fact_id IN (
          SELECT id FROM facts WHERE scope_id = ?
        )
        """,
        (scope_id,),
    )
    conn.execute(
        """
        DELETE FROM fact_events WHERE fact_id IN (
          SELECT id FROM facts WHERE scope_id = ?
        )
        """,
        (scope_id,),
    )
    conn.execute("DELETE FROM facts WHERE scope_id = ?", (scope_id,))
    conn.execute("DELETE FROM jobs WHERE scope_id = ?", (scope_id,))
    conn.execute(
        """
        UPDATE episodes SET status = 'PENDING'
        WHERE scope_id = ? AND kind = 'message' AND status <> 'DELETED'
        """,
        (scope_id,),
    )
    conn.execute(
        """
        UPDATE scopes
        SET applied_seq = 0, projection_version = projection_version + 1
        WHERE id = ?
        """,
        (scope_id,),
    )


def forget_scope(conn: sqlite3.Connection, scope_id: int) -> None:
    """Hard-delete a scope and the rows that belong to it."""
    rows = conn.execute(
        """
        SELECT f.id, f.subject_id, f.object_text, p.name AS predicate
        FROM facts f
        JOIN predicates p ON p.id = f.predicate_id
        WHERE f.scope_id = ?
        """,
        (scope_id,),
    ).fetchall()
    for row in rows:
        text = search_text(
            subject_label(conn, int(row["subject_id"])),
            row["predicate"],
            row["object_text"],
        )
        unindex_fact(conn, int(row["id"]), text)
    episodes = conn.execute(
        "SELECT id, content FROM episodes WHERE scope_id = ?", (scope_id,)
    ).fetchall()
    for episode in episodes:
        unindex_episode(conn, int(episode["id"]), str(episode["content"]))
    delete_scope_embeddings(conn, scope_id)
    conn.execute(
        """
        DELETE FROM fact_edges WHERE src_fact_id IN (
          SELECT id FROM facts WHERE scope_id = ?
        )
        """,
        (scope_id,),
    )
    conn.execute(
        """
        DELETE FROM fact_events WHERE fact_id IN (
          SELECT id FROM facts WHERE scope_id = ?
        )
        """,
        (scope_id,),
    )
    conn.execute("DELETE FROM facts WHERE scope_id = ?", (scope_id,))
    conn.execute("DELETE FROM rejected_claims WHERE scope_id = ?", (scope_id,))
    conn.execute("DELETE FROM jobs WHERE scope_id = ?", (scope_id,))
    conn.execute("DELETE FROM episodes WHERE scope_id = ?", (scope_id,))
    conn.execute("DELETE FROM entity_aliases WHERE scope_id = ?", (scope_id,))
    conn.execute("DELETE FROM entities WHERE scope_id = ?", (scope_id,))
    conn.execute("DELETE FROM scopes WHERE id = ?", (scope_id,))

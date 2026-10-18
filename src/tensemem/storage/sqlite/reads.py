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


def forget_scope(conn: sqlite3.Connection, scope_id: int) -> None:
    """Hard-delete a scope and the rows that belong to it."""
    fact_ids = [
        int(row["id"])
        for row in conn.execute("SELECT id FROM facts WHERE scope_id = ?", (scope_id,)).fetchall()
    ]
    for fact_id in fact_ids:
        conn.execute(
            "INSERT INTO facts_fts(facts_fts, rowid) VALUES ('delete', ?)",
            (fact_id,),
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
    conn.execute("DELETE FROM rejected_claims WHERE scope_id = ?", (scope_id,))
    conn.execute("DELETE FROM jobs WHERE scope_id = ?", (scope_id,))
    conn.execute("DELETE FROM episodes WHERE scope_id = ?", (scope_id,))
    conn.execute("DELETE FROM entity_aliases WHERE scope_id = ?", (scope_id,))
    conn.execute("DELETE FROM entities WHERE scope_id = ?", (scope_id,))
    conn.execute("DELETE FROM scopes WHERE id = ?", (scope_id,))

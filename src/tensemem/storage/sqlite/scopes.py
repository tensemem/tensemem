"""Scopes: whose memory a fact or episode belongs to.

Functions never commit; callers own the transaction.
"""

from __future__ import annotations

import sqlite3

from tensemem.core.models import Scope, ScopeKey
from tensemem.storage.sqlite.entities import ensure_self_entity, find_self_entity


def get_or_create_scope(conn: sqlite3.Connection, key: ScopeKey, *, now: str) -> Scope:
    """Return the scope for ``key``, creating it and its self entity if needed."""
    # The no-op update makes RETURNING yield the row whether or not it already existed.
    row = conn.execute(
        """
        INSERT INTO scopes(namespace, user_id, agent_id, created_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(namespace, user_id, agent_id) DO UPDATE SET namespace = excluded.namespace
        RETURNING id, applied_seq, projection_version
        """,
        (key.namespace, key.user_id, key.agent_id, now),
    ).fetchone()
    self_entity_id = ensure_self_entity(conn, row["id"], now=now)
    return _to_scope(row, key, self_entity_id)


def get_scope(conn: sqlite3.Connection, key: ScopeKey) -> Scope | None:
    """Return the scope for ``key`` without creating it (safe on read connections)."""
    row = conn.execute(
        """
        SELECT id, applied_seq, projection_version FROM scopes
        WHERE namespace = ? AND user_id = ? AND agent_id = ?
        """,
        (key.namespace, key.user_id, key.agent_id),
    ).fetchone()
    if row is None:
        return None
    self_entity_id = find_self_entity(conn, row["id"])
    if self_entity_id is None:
        return None
    return _to_scope(row, key, self_entity_id)


def _to_scope(row: sqlite3.Row, key: ScopeKey, self_entity_id: int) -> Scope:
    return Scope(
        id=row["id"],
        key=key,
        self_entity_id=self_entity_id,
        applied_seq=row["applied_seq"],
        projection_version=row["projection_version"],
    )

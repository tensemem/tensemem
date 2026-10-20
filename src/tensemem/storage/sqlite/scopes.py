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


def get_scope_by_id(conn: sqlite3.Connection, scope_id: int) -> Scope | None:
    row = conn.execute(
        """
        SELECT id, user_id, agent_id, namespace, applied_seq, projection_version
        FROM scopes WHERE id = ?
        """,
        (scope_id,),
    ).fetchone()
    if row is None:
        return None
    self_entity_id = find_self_entity(conn, row["id"])
    if self_entity_id is None:
        return None
    key = ScopeKey(user_id=row["user_id"], agent_id=row["agent_id"], namespace=row["namespace"])
    return _to_scope(row, key, self_entity_id)


def list_scopes(conn: sqlite3.Connection, *, namespace: str | None = None) -> tuple[Scope, ...]:
    """Return stored scopes, optionally limited to one namespace."""
    sql = """
        SELECT id, user_id, agent_id, namespace, applied_seq, projection_version
        FROM scopes
    """
    params: tuple[object, ...] = ()
    if namespace is not None:
        sql += " WHERE namespace = ?"
        params = (namespace,)
    sql += " ORDER BY user_id, agent_id, namespace"
    found: list[Scope] = []
    for row in conn.execute(sql, params).fetchall():
        self_entity_id = find_self_entity(conn, row["id"])
        if self_entity_id is None:
            continue
        key = ScopeKey(
            user_id=row["user_id"],
            agent_id=row["agent_id"],
            namespace=row["namespace"],
        )
        found.append(_to_scope(row, key, self_entity_id))
    return tuple(found)


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

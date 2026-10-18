"""Entities and entity aliases.

A global entity (``scope_id IS NULL``) is shared by every scope, e.g.
"PostgreSQL". Scope aliases override global ones, so a user's "pg" can mean
something else. Functions never commit; callers own the transaction.
"""

from __future__ import annotations

import sqlite3

from tensemem.core.errors import RegistryConflictError
from tensemem.core.models import EntityKind
from tensemem.core.normalize import normalize_value

SELF_NAME = "user"


def ensure_self_entity(conn: sqlite3.Connection, scope_id: int, *, now: str) -> int:
    """Return the entity that represents the scope's user, creating it if needed."""
    entity_id = find_self_entity(conn, scope_id)
    if entity_id is not None:
        return entity_id
    return _insert_entity(conn, SELF_NAME, kind="self", scope_id=scope_id, now=now)


def find_self_entity(conn: sqlite3.Connection, scope_id: int) -> int | None:
    row = conn.execute(
        "SELECT id FROM entities WHERE scope_id = ? AND kind = 'self'", (scope_id,)
    ).fetchone()
    return None if row is None else int(row["id"])


def ensure_global_entity(
    conn: sqlite3.Connection, name: str, *, kind: EntityKind = "thing", now: str
) -> int:
    """Return the global entity named ``name``, creating it if needed."""
    row = conn.execute(
        "SELECT id FROM entities WHERE scope_id IS NULL AND canonical_name = ?", (name,)
    ).fetchone()
    if row is not None:
        return int(row["id"])
    return _insert_entity(conn, name, kind=kind, scope_id=None, now=now)


def add_entity_alias(
    conn: sqlite3.Connection, alias: str, entity_id: int, *, scope_id: int | None = None
) -> None:
    """Map ``alias`` to ``entity_id`` within a scope (or globally when ``scope_id`` is None)."""
    key = normalize_value(alias)
    current = _alias_target(conn, key, scope_id)
    if current is None:
        try:
            conn.execute(
                "INSERT INTO entity_aliases(alias_norm, scope_id, entity_id) VALUES (?, ?, ?)",
                (key, scope_id, entity_id),
            )
        except sqlite3.IntegrityError as exc:
            msg = f"entity alias {alias!r} already points at another entity"
            raise RegistryConflictError(msg) from exc
    elif current != entity_id:
        msg = f"entity alias {alias!r} already points at another entity"
        raise RegistryConflictError(msg)


def resolve_entity(conn: sqlite3.Connection, text: str, *, scope_id: int) -> int | None:
    """Find the entity ``text`` refers to: scope aliases first, then global ones."""
    key = normalize_value(text)
    return _alias_target(conn, key, scope_id) or _alias_target(conn, key, None)


def ensure_subject_entity(
    conn: sqlite3.Connection, scope_id: int, subject: str, *, now: str
) -> int:
    """Resolve ``subject`` to an entity id, creating a scope-local one if needed."""
    if normalize_value(subject) in {SELF_NAME, "self"}:
        return ensure_self_entity(conn, scope_id, now=now)
    found = resolve_entity(conn, subject, scope_id=scope_id)
    if found is not None:
        return found
    row = conn.execute(
        "SELECT id FROM entities WHERE scope_id = ? AND canonical_name = ?",
        (scope_id, subject),
    ).fetchone()
    if row is not None:
        return int(row["id"])
    entity_id = _insert_entity(conn, subject, kind="thing", scope_id=scope_id, now=now)
    add_entity_alias(conn, subject, entity_id, scope_id=scope_id)
    return entity_id


def subject_label(conn: sqlite3.Connection, entity_id: int) -> str:
    """Resolver-facing subject name: ``user`` for self, else canonical_name."""
    row = conn.execute(
        "SELECT kind, canonical_name FROM entities WHERE id = ?", (entity_id,)
    ).fetchone()
    if row is None:
        msg = f"entity {entity_id} does not exist"
        raise LookupError(msg)
    if row["kind"] == "self":
        return SELF_NAME
    return str(row["canonical_name"])


def _alias_target(conn: sqlite3.Connection, key: str, scope_id: int | None) -> int | None:
    # "IS" rather than "=" so a NULL scope matches global aliases.
    row = conn.execute(
        "SELECT entity_id FROM entity_aliases WHERE alias_norm = ? AND scope_id IS ?",
        (key, scope_id),
    ).fetchone()
    return None if row is None else int(row["entity_id"])


def _insert_entity(
    conn: sqlite3.Connection,
    name: str,
    *,
    kind: EntityKind,
    scope_id: int | None,
    now: str,
) -> int:
    row = conn.execute(
        """
        INSERT INTO entities(scope_id, canonical_name, kind, created_at)
        VALUES (?, ?, ?, ?)
        RETURNING id
        """,
        (scope_id, name, kind, now),
    ).fetchone()
    return int(row["id"])

"""Predicate registry: canonical predicates, their cardinality, and aliases.

Functions take a connection and never commit; callers own the transaction.
"""

from __future__ import annotations

import sqlite3

from tensemem.core.errors import RegistryConflictError
from tensemem.core.models import Cardinality, Predicate, PredicateSpec
from tensemem.core.normalize import normalize_key


def register_predicate(
    conn: sqlite3.Connection,
    spec: PredicateSpec,
    *,
    now: str,
    builtin: bool = False,
) -> Predicate:
    """Register ``spec`` and its aliases. Re-registering the same definition is a no-op.

    Raises :class:`RegistryConflictError` if the name exists with a different
    cardinality, the name is already an alias of another predicate, or an alias
    already points at another predicate.
    """
    predicate = get_predicate_by_name(conn, spec.name)
    if predicate is None:
        _reject_if_name_is_alias(conn, spec.name)
        predicate = _insert_predicate(conn, spec, now=now, builtin=builtin)
    elif predicate.cardinality is not spec.cardinality:
        msg = (
            f"predicate {predicate.name!r} is already {predicate.cardinality}, "
            f"cannot redefine as {spec.cardinality}"
        )
        raise RegistryConflictError(msg)

    for alias in spec.aliases:
        add_predicate_alias(conn, alias, predicate)
    return predicate


def add_predicate_alias(conn: sqlite3.Connection, alias: str, predicate: Predicate) -> None:
    """Map ``alias`` to ``predicate``. Raises if the alias already means something else."""
    key = normalize_key(alias)
    if key == predicate.name:
        return

    named = get_predicate_by_name(conn, key)
    if named is not None:
        msg = f"alias {alias!r} is the name of predicate {named.name!r}"
        raise RegistryConflictError(msg)

    row = conn.execute(
        "SELECT predicate_id FROM predicate_aliases WHERE alias_norm = ?", (key,)
    ).fetchone()
    if row is None:
        conn.execute(
            "INSERT INTO predicate_aliases(alias_norm, predicate_id) VALUES (?, ?)",
            (key, predicate.id),
        )
    elif row["predicate_id"] != predicate.id:
        msg = f"alias {alias!r} already points at another predicate"
        raise RegistryConflictError(msg)


def get_predicate(conn: sqlite3.Connection, name_or_alias: str) -> Predicate | None:
    """Look up a predicate by canonical name, then by alias."""
    predicate = get_predicate_by_name(conn, name_or_alias)
    if predicate is not None:
        return predicate
    row = conn.execute(
        """
        SELECT p.* FROM predicate_aliases a
        JOIN predicates p ON p.id = a.predicate_id
        WHERE a.alias_norm = ?
        """,
        (normalize_key(name_or_alias),),
    ).fetchone()
    return None if row is None else _to_predicate(row)


def get_predicate_by_name(conn: sqlite3.Connection, name: str) -> Predicate | None:
    row = conn.execute("SELECT * FROM predicates WHERE name = ?", (normalize_key(name),)).fetchone()
    return None if row is None else _to_predicate(row)


def list_predicates(conn: sqlite3.Connection) -> list[Predicate]:
    rows = conn.execute("SELECT * FROM predicates ORDER BY name").fetchall()
    return [_to_predicate(row) for row in rows]


def _reject_if_name_is_alias(conn: sqlite3.Connection, name: str) -> None:
    key = normalize_key(name)
    row = conn.execute(
        "SELECT predicate_id FROM predicate_aliases WHERE alias_norm = ?", (key,)
    ).fetchone()
    if row is not None:
        msg = f"{name!r} is already an alias of another predicate"
        raise RegistryConflictError(msg)


def _insert_predicate(
    conn: sqlite3.Connection, spec: PredicateSpec, *, now: str, builtin: bool
) -> Predicate:
    row = conn.execute(
        """
        INSERT INTO predicates
          (name, description, cardinality, value_type, pinned, builtin, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        RETURNING *
        """,
        (
            normalize_key(spec.name),
            spec.description,
            spec.cardinality.value,
            spec.value_type,
            int(spec.pinned),
            int(builtin),
            now,
        ),
    ).fetchone()
    return _to_predicate(row)


def _to_predicate(row: sqlite3.Row) -> Predicate:
    return Predicate(
        id=row["id"],
        name=row["name"],
        cardinality=Cardinality(row["cardinality"]),
        description=row["description"],
        value_type=row["value_type"],
        pinned=bool(row["pinned"]),
        builtin=bool(row["builtin"]),
    )

"""Map extractor ops onto registry names, aliases, and entities."""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence

from tensemem.core.models import ExtractedOp, Scope
from tensemem.core.normalize import normalize_value, strip_articles
from tensemem.core.resolver import IncomingOp
from tensemem.storage.sqlite.entities import (
    ensure_subject_entity,
    resolve_entity,
    subject_label,
)
from tensemem.storage.sqlite.registry import add_predicate_alias, get_predicate, register_predicate


def normalize_ops(
    conn: sqlite3.Connection,
    scope: Scope,
    ops: Sequence[ExtractedOp],
    *,
    now: str,
) -> tuple[IncomingOp, ...]:
    """Resolve aliases and subjects. Ops with no matching predicate are dropped."""
    incoming: list[IncomingOp] = []
    for op in ops:
        prepared = _normalize_one(conn, scope, op, now=now)
        if prepared is not None:
            incoming.append(prepared)
    return tuple(incoming)


def _normalize_one(
    conn: sqlite3.Connection,
    scope: Scope,
    op: ExtractedOp,
    *,
    now: str,
) -> IncomingOp | None:
    predicate = get_predicate(conn, op.predicate)
    if predicate is None and op.new_predicate is not None:
        predicate = register_predicate(conn, op.new_predicate, now=now)
        if get_predicate(conn, op.predicate) is None:
            add_predicate_alias(conn, op.predicate, predicate)
        predicate = get_predicate(conn, op.predicate) or predicate
    if predicate is None:
        return None

    subject_id = ensure_subject_entity(conn, scope.id, op.subject, now=now)
    subject = subject_label(conn, subject_id)
    object_text, object_norm = _object(conn, scope.id, op.object)
    cleaned = op.model_copy(
        update={"subject": subject, "predicate": predicate.name, "object": object_text}
    )
    return IncomingOp(op=cleaned, object_norm=object_norm, cardinality=predicate.cardinality)


def _object(conn: sqlite3.Connection, scope_id: int, value: str) -> tuple[str, str]:
    raw = strip_articles(value).strip()
    if not raw:
        return "", ""
    entity_id = resolve_entity(conn, raw, scope_id=scope_id)
    if entity_id is not None:
        name = subject_label(conn, entity_id)
        return name, normalize_value(name)
    return raw, normalize_value(raw)

"""JSONL dump of predicates and episodes for a scope."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator, Mapping
from typing import Any, cast

from tensemem.core.models import Scope
from tensemem.storage.sqlite.episodes import list_episodes
from tensemem.storage.sqlite.registry import list_predicates


def dump_scope(conn: sqlite3.Connection, scope: Scope) -> str:
    """Predicates first, then episodes in log order, one JSON object per line."""
    lines = [
        json.dumps(record, separators=(",", ":"), ensure_ascii=False)
        for record in iter_records(conn, scope)
    ]
    return "\n".join(lines) + ("\n" if lines else "")


def iter_records(conn: sqlite3.Connection, scope: Scope) -> Iterator[dict[str, Any]]:
    for predicate in list_predicates(conn):
        yield {
            "type": "predicate",
            "name": predicate.name,
            "cardinality": predicate.cardinality.value,
            "description": predicate.description,
            "pinned": predicate.pinned,
        }
    for episode in list_episodes(conn, scope.id):
        yield {
            "type": "episode",
            "kind": str(episode["kind"]),
            "role": str(episode["role"]),
            "content": str(episode["content"]),
            "occurred_at": str(episode["occurred_at"]),
        }


def parse_jsonl(text: str) -> tuple[Mapping[str, Any], ...]:
    records: list[Mapping[str, Any]] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        item = json.loads(line)
        if isinstance(item, dict):
            records.append(cast(dict[str, Any], item))
    return tuple(records)

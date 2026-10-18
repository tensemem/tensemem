"""Seed the starter ontology into a database. Safe to run on every open."""

from __future__ import annotations

import sqlite3
from contextlib import suppress

from tensemem.core.errors import RegistryConflictError
from tensemem.core.ontology import Ontology
from tensemem.storage.sqlite.entities import add_entity_alias, ensure_global_entity
from tensemem.storage.sqlite.registry import (
    add_predicate_alias,
    get_predicate_by_name,
    register_predicate,
)


def seed_ontology(conn: sqlite3.Connection, ontology: Ontology, *, now: str) -> None:
    """Insert built-in predicates, entities, and aliases that are missing.

    Existing definitions win: a developer who already registered a name or claimed
    an alias keeps it, and the built-in one is skipped.
    """
    for spec in ontology.predicates:
        predicate = get_predicate_by_name(conn, spec.name)
        if predicate is None:
            predicate = register_predicate(
                conn, spec.model_copy(update={"aliases": ()}), now=now, builtin=True
            )
        for alias in spec.aliases:
            with suppress(RegistryConflictError):
                add_predicate_alias(conn, alias, predicate)

    for entity in ontology.entities:
        entity_id = ensure_global_entity(conn, entity.name, kind=entity.kind, now=now)
        for alias in (entity.name, *entity.aliases):
            with suppress(RegistryConflictError):
                add_entity_alias(conn, alias, entity_id)

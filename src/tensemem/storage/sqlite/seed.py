"""Apply an :class:`~tensemem.core.ontology.Ontology` to a database.

Not run automatically. Callers pass an ontology they built or loaded from a file.
"""

from __future__ import annotations

import sqlite3
from contextlib import suppress

from tensemem.core.errors import RegistryConflictError
from tensemem.core.normalize import normalize_key
from tensemem.core.ontology import Ontology
from tensemem.storage.sqlite.entities import add_entity_alias, ensure_global_entity
from tensemem.storage.sqlite.registry import (
    add_predicate_alias,
    get_predicate,
    register_predicate,
)


def seed_ontology(conn: sqlite3.Connection, ontology: Ontology, *, now: str) -> None:
    """Insert predicates, entities, and aliases from ``ontology`` that are missing.

    Existing definitions win: a name or alias already in the DB is left alone.
    """
    for spec in ontology.predicates:
        existing = get_predicate(conn, spec.name)
        if existing is None:
            predicate = register_predicate(
                conn, spec.model_copy(update={"aliases": ()}), now=now, builtin=False
            )
        elif normalize_key(existing.name) != normalize_key(spec.name):
            # ``spec.name`` is already an alias of another predicate; keep that mapping.
            continue
        else:
            predicate = existing
        for alias in spec.aliases:
            with suppress(RegistryConflictError):
                add_predicate_alias(conn, alias, predicate)

    for entity in ontology.entities:
        entity_id = ensure_global_entity(conn, entity.name, kind=entity.kind, now=now)
        for alias in (entity.name, *entity.aliases):
            with suppress(RegistryConflictError):
                add_entity_alias(conn, alias, entity_id)

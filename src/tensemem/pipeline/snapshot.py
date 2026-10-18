"""Compact registry + ACTIVE facts shown to the extractor."""

from __future__ import annotations

import sqlite3

from pydantic import BaseModel, ConfigDict

from tensemem.core.models import Cardinality, FactStatus, Scope
from tensemem.storage.sqlite.registry import list_predicates
from tensemem.storage.sqlite.snapshot import list_facts


class RegistryEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    cardinality: Cardinality
    description: str = ""


class CompactFact(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    subject: str
    predicate: str
    object: str


class ExtractSnapshot(BaseModel):
    """What the extractor may see: vocabulary and current beliefs."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    reference_time: str
    registry: tuple[RegistryEntry, ...] = ()
    facts: tuple[CompactFact, ...] = ()


def load_extract_snapshot(
    conn: sqlite3.Connection,
    scope: Scope | None,
    *,
    reference_time: str,
) -> ExtractSnapshot:
    registry = tuple(
        RegistryEntry(name=item.name, cardinality=item.cardinality, description=item.description)
        for item in list_predicates(conn)
    )
    facts: tuple[CompactFact, ...] = ()
    if scope is not None:
        facts = tuple(
            CompactFact(subject=fact.subject, predicate=fact.predicate, object=fact.object)
            for fact in list_facts(conn, scope.id, statuses=(FactStatus.ACTIVE,))
        )
    return ExtractSnapshot(reference_time=reference_time, registry=registry, facts=facts)

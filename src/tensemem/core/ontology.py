"""Optional ontology files that apps can load and seed.

The engine ships with an empty registry. An ontology is just a TOML (or
in-memory) description of predicates and entities that a caller may apply with
:meth:`~tensemem.storage.base.StorageBackend.seed`.
"""

from __future__ import annotations

import tomllib
from collections.abc import Callable, Iterable
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator

from tensemem.core.models import EntityKind, PredicateSpec
from tensemem.core.normalize import normalize_key, normalize_value


class EntitySpec(BaseModel):
    """A named entity with optional aliases (global or later scoped by the app)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1)
    kind: EntityKind = "thing"
    aliases: tuple[str, ...] = ()


class Ontology(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    predicates: tuple[PredicateSpec, ...] = ()
    entities: tuple[EntitySpec, ...] = ()

    @model_validator(mode="after")
    def _aliases_are_unambiguous(self) -> Ontology:
        _require_unique(((p.name, p.aliases) for p in self.predicates), normalize_key)
        _require_unique(((e.name, e.aliases) for e in self.entities), normalize_value)
        return self

    @classmethod
    def from_toml(cls, path: str | Path) -> Ontology:
        """Load an ontology from a TOML file the app owns."""
        text = Path(path).read_text(encoding="utf-8")
        return cls.model_validate(tomllib.loads(text))


def _require_unique(
    entries: Iterable[tuple[str, tuple[str, ...]]],
    normalize: Callable[[str], str],
) -> None:
    owners: dict[str, str] = {}
    for name, aliases in entries:
        for key in (name, *aliases):
            owner = owners.setdefault(normalize(key), name)
            if owner != name:
                msg = f"{key!r} is claimed by both {owner!r} and {name!r}"
                raise ValueError(msg)

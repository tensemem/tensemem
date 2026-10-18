"""Starter ontology: built-in predicates and common entity aliases (``ontology.toml``)."""

from __future__ import annotations

import tomllib
from collections.abc import Callable, Iterable
from functools import cache
from importlib import resources

from pydantic import BaseModel, ConfigDict, Field, model_validator

from tensemem.core.models import EntityKind, PredicateSpec
from tensemem.core.normalize import normalize_key, normalize_value


class EntitySpec(BaseModel):
    """A global entity, such as a city or technology, with its common aliases."""

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


@cache
def load_ontology() -> Ontology:
    """Load the ontology shipped with the package."""
    text = resources.files("tensemem.core").joinpath("ontology.toml").read_text(encoding="utf-8")
    return Ontology.model_validate(tomllib.loads(text))


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

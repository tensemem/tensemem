import sqlite3

import pytest

from tensemem.core.errors import RegistryConflictError
from tensemem.core.models import Cardinality, Predicate, PredicateSpec
from tensemem.storage.sqlite import SqliteDatabase
from tensemem.storage.sqlite.registry import get_predicate, list_predicates, register_predicate


def test_starter_ontology_is_seeded_on_open(db: SqliteDatabase) -> None:
    predicates = db.read(list_predicates)

    assert len(predicates) >= 40
    assert all(p.builtin for p in predicates)


def test_lookup_by_name_or_alias(db: SqliteDatabase) -> None:
    by_alias = db.read(lambda c: get_predicate(c, "Home City"))

    assert by_alias is not None
    assert by_alias.name == "lives_in"
    assert by_alias.cardinality is Cardinality.ONE
    assert db.read(lambda c: get_predicate(c, "no_such_thing")) is None


def test_register_custom_predicate_with_aliases(db: SqliteDatabase) -> None:
    spec = PredicateSpec(name="Favorite Band", cardinality=Cardinality.MANY, aliases=("top band",))

    created = _register(db, spec)
    again = _register(db, spec)

    assert created == again
    assert created.name == "favorite_band"
    assert created.builtin is False
    assert db.read(lambda c: get_predicate(c, "top_band")) == created


def test_redefining_cardinality_is_a_conflict(db: SqliteDatabase) -> None:
    with pytest.raises(RegistryConflictError, match="already ONE"):
        _register(db, PredicateSpec(name="lives_in", cardinality=Cardinality.MANY))


def test_alias_cannot_point_at_two_predicates(db: SqliteDatabase) -> None:
    with pytest.raises(RegistryConflictError, match="another predicate"):
        _register(db, PredicateSpec(name="home_base", aliases=("city",)))

    # The failed transaction rolled back, so the predicate was not half-created.
    assert db.read(lambda c: get_predicate(c, "home_base")) is None


def _register(db: SqliteDatabase, spec: PredicateSpec) -> Predicate:
    def run(conn: sqlite3.Connection) -> Predicate:
        return register_predicate(conn, spec, now=db.now())

    return db.transaction(run)

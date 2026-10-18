import sqlite3

import pytest

from tensemem.core.errors import RegistryConflictError
from tensemem.core.models import Cardinality, Predicate, PredicateSpec
from tensemem.core.ontology import Ontology
from tensemem.storage.sqlite import SqliteDatabase
from tensemem.storage.sqlite.registry import get_predicate, list_predicates, register_predicate


def test_registry_starts_empty(db: SqliteDatabase) -> None:
    assert db.read(list_predicates) == []


def test_seed_loads_app_ontology(db: SqliteDatabase) -> None:
    ontology = Ontology(
        predicates=(
            PredicateSpec(
                name="lives_in",
                cardinality=Cardinality.ONE,
                aliases=("city", "home_city"),
            ),
        )
    )
    db.seed(ontology)

    by_alias = db.read(lambda c: get_predicate(c, "Home City"))
    assert by_alias is not None
    assert by_alias.name == "lives_in"
    assert by_alias.cardinality is Cardinality.ONE
    assert by_alias.builtin is False
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
    _register(db, PredicateSpec(name="lives_in", cardinality=Cardinality.ONE))
    with pytest.raises(RegistryConflictError, match="already ONE"):
        _register(db, PredicateSpec(name="lives_in", cardinality=Cardinality.MANY))


def test_alias_cannot_point_at_two_predicates(db: SqliteDatabase) -> None:
    _register(db, PredicateSpec(name="lives_in", aliases=("city",)))
    with pytest.raises(RegistryConflictError, match="another predicate"):
        _register(db, PredicateSpec(name="home_base", aliases=("city",)))

    assert db.read(lambda c: get_predicate(c, "home_base")) is None


def _register(db: SqliteDatabase, spec: PredicateSpec) -> Predicate:
    def run(conn: sqlite3.Connection) -> Predicate:
        return register_predicate(conn, spec, now=db.now())

    return db.transaction(run)

import pytest
from pydantic import ValidationError

from tensemem.core.models import Cardinality, PredicateSpec
from tensemem.core.ontology import Ontology, load_ontology


def test_starter_ontology_loads() -> None:
    ontology = load_ontology()
    by_name = {p.name: p for p in ontology.predicates}

    assert len(by_name) >= 40
    assert by_name["lives_in"].cardinality is Cardinality.ONE
    assert by_name["uses_language"].cardinality is Cardinality.MANY
    assert "city" in by_name["lives_in"].aliases
    assert any(e.name == "PostgreSQL" for e in ontology.entities)


def test_ambiguous_predicate_alias_is_rejected() -> None:
    with pytest.raises(ValidationError, match="claimed by both"):
        Ontology(
            predicates=(
                PredicateSpec(name="lives_in", aliases=("place",)),
                PredicateSpec(name="hometown", aliases=("Place",)),
            )
        )

from pathlib import Path

import pytest
from pydantic import ValidationError

from tensemem.core.models import Cardinality, PredicateSpec
from tensemem.core.ontology import Ontology


def test_ontology_from_toml(tmp_path: Path) -> None:
    path = tmp_path / "onto.toml"
    path.write_text(
        """
[[predicates]]
name = "lives_in"
aliases = ["city"]

[[predicates]]
name = "uses_language"
cardinality = "MANY"

[[entities]]
name = "PostgreSQL"
kind = "tech"
aliases = ["Postgres", "pg"]
""",
        encoding="utf-8",
    )
    ontology = Ontology.from_toml(path)
    by_name = {p.name: p for p in ontology.predicates}
    assert by_name["lives_in"].cardinality is Cardinality.ONE
    assert by_name["uses_language"].cardinality is Cardinality.MANY
    assert ontology.entities[0].name == "PostgreSQL"


def test_ambiguous_predicate_alias_is_rejected() -> None:
    with pytest.raises(ValidationError, match="claimed by both"):
        Ontology(
            predicates=(
                PredicateSpec(name="lives_in", aliases=("place",)),
                PredicateSpec(name="hometown", aliases=("Place",)),
            )
        )

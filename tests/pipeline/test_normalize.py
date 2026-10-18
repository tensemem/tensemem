from datetime import UTC, datetime

from tensemem import Memory
from tensemem.core.clock import FrozenClock
from tensemem.core.models import Cardinality, ExtractedOp, OpKind, PredicateSpec
from tensemem.core.ontology import EntitySpec, Ontology


def test_alias_subject_and_value() -> None:
    with _memory() as mem:
        mem.register_predicate("lives_in", aliases=("city",))
        mem.seed(
            Ontology(
                entities=(EntitySpec(name="Bangalore", kind="place", aliases=("BLR", "Bengaluru")),)
            )
        )
        incoming = mem.normalize(
            "u1",
            (
                ExtractedOp(
                    subject="self",
                    predicate="city",
                    object="the BLR",
                    op=OpKind.SET,
                    evidence="I live in BLR",
                ),
            ),
        )
        assert len(incoming) == 1
        assert incoming[0].op.subject == "user"
        assert incoming[0].op.predicate == "lives_in"
        assert incoming[0].op.object == "Bangalore"
        assert incoming[0].object_norm == "bangalore"
        assert incoming[0].cardinality is Cardinality.ONE


def test_new_predicate_is_registered_and_unknown_is_dropped() -> None:
    with _memory() as mem:
        incoming = mem.normalize(
            "u1",
            (
                ExtractedOp(
                    subject="user",
                    predicate="diet",
                    object="vegetarian",
                    op=OpKind.SET,
                    new_predicate=PredicateSpec(name="diet", description="what they eat"),
                    evidence="I'm vegetarian",
                ),
                ExtractedOp(
                    subject="user",
                    predicate="made_up",
                    object="x",
                    op=OpKind.SET,
                    evidence="x",
                ),
            ),
        )
        assert [item.op.predicate for item in incoming] == ["diet"]
        again = mem.normalize(
            "u1",
            (
                ExtractedOp(
                    subject="user",
                    predicate="diet",
                    object="vegan",
                    op=OpKind.SET,
                    evidence="now vegan",
                ),
            ),
        )
        assert again[0].op.predicate == "diet"


def test_relational_subject_stays_scope_local() -> None:
    with _memory() as mem:
        incoming = mem.normalize(
            "u1",
            (
                ExtractedOp(
                    subject="user.wife",
                    predicate="hometown",
                    object="Pune",
                    op=OpKind.SET,
                    new_predicate=PredicateSpec(name="hometown"),
                    evidence="my wife is from Pune",
                ),
            ),
        )
        assert incoming[0].op.subject == "user.wife"
        assert incoming[0].op.predicate == "hometown"
        assert incoming[0].op.object == "Pune"


def _memory() -> Memory:
    return Memory(":memory:", clock=FrozenClock(datetime(2026, 10, 18, 11, 0, 0, tzinfo=UTC)))

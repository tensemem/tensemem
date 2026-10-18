from datetime import UTC, datetime

import pytest

from tensemem import Memory
from tensemem.core.clock import FrozenClock
from tensemem.core.errors import UnknownFactError, UnknownPredicateError
from tensemem.core.models import Cardinality, FactStatus


def test_delhi_to_bangalore_and_correction() -> None:
    with _memory() as mem:
        mem.register_predicate("lives_in", cardinality=Cardinality.ONE)
        mem.set(user_id="u1", predicate="lives_in", value="Delhi")
        moved = mem.set(user_id="u1", predicate="lives_in", value="Bangalore")

        state = mem.state(user_id="u1")
        assert state.values == {"lives_in": "Bangalore"}
        assert state.freshness.is_current
        assert state.freshness.as_of_seq == moved.seq

        history = mem.history(user_id="u1", predicate="lives_in")
        assert [fact.object for fact in history.facts] == ["Delhi", "Bangalore"]
        assert [fact.status for fact in history.facts] == [FactStatus.SUPERSEDED, FactStatus.ACTIVE]

        bangalore = next(fact for fact in history.facts if fact.object == "Bangalore")
        explained = mem.explain(bangalore.id)
        assert explained.superseded_by is None
        assert any(event.reason == "newer_value" for event in explained.events)

        mem.correct(bangalore.id, note="misread a trip as a move")
        restored = mem.state(user_id="u1")
        assert restored.values == {"lives_in": "Delhi"}
        assert all(fact.object != "Bangalore" for fact in mem.history(user_id="u1").facts)


def test_correct_with_replacement() -> None:
    with _memory() as mem:
        mem.register_predicate("lives_in", cardinality=Cardinality.ONE)
        mem.set(user_id="u1", predicate="lives_in", value="Pune")
        pune = mem.state(user_id="u1").facts[0]
        mem.correct(pune.id, replacement="Bangalore")
        assert mem.state(user_id="u1").values == {"lives_in": "Bangalore"}


def test_many_values_replace_and_remove() -> None:
    with _memory() as mem:
        mem.register_predicate("uses_language", cardinality=Cardinality.MANY)
        mem.add_value(user_id="u1", predicate="uses_language", value="Python")
        mem.add_value(user_id="u1", predicate="uses_language", value="Go")
        mem.replace_values(user_id="u1", predicate="uses_language", values=("Rust", "Go"))

        assert mem.state(user_id="u1").values == {"uses_language": ("Go", "Rust")}

        mem.remove_value(user_id="u1", predicate="uses_language", value="Go")
        assert mem.state(user_id="u1").values == {"uses_language": ("Rust",)}


def test_retract_clears_a_one_slot() -> None:
    with _memory() as mem:
        mem.register_predicate("diet")
        mem.set(user_id="u1", predicate="diet", value="vegetarian")
        mem.retract(user_id="u1", predicate="diet")
        assert mem.state(user_id="u1").values == {}
        assert mem.history(user_id="u1", predicate="diet").facts[0].status is FactStatus.RETRACTED


def test_unknown_predicate_and_fact() -> None:
    with _memory() as mem:
        with pytest.raises(UnknownPredicateError, match="lives_in"):
            mem.set(user_id="u1", predicate="lives_in", value="Delhi")
        with pytest.raises(UnknownFactError):
            mem.explain("01AAAAAAAAAAAAAAAAAAAAAAAA")


def test_scopes_do_not_share_state() -> None:
    with _memory() as mem:
        mem.register_predicate("lives_in")
        mem.set(user_id="u1", predicate="lives_in", value="Delhi")
        mem.set(user_id="u2", predicate="lives_in", value="Pune")
        assert mem.state(user_id="u1").values == {"lives_in": "Delhi"}
        assert mem.state(user_id="u2").values == {"lives_in": "Pune"}


def test_forget_removes_the_scope() -> None:
    with _memory() as mem:
        mem.register_predicate("lives_in")
        mem.set(user_id="u1", predicate="lives_in", value="Delhi")
        mem.forget(user_id="u1")
        assert mem.state(user_id="u1").facts == ()
        assert mem.state(user_id="u1").freshness.latest_seq == 0


def _memory() -> Memory:
    clock = FrozenClock(datetime(2026, 10, 18, 11, 0, 0, tzinfo=UTC))
    return Memory(":memory:", clock=clock)

from datetime import UTC, datetime

from tensemem import Memory
from tensemem.core.clock import FrozenClock
from tensemem.core.models import Cardinality


def test_extract_snapshot_is_active_facts_and_registry() -> None:
    clock = FrozenClock(datetime(2026, 10, 18, 11, 0, 0, tzinfo=UTC))
    with Memory(":memory:", clock=clock) as mem:
        mem.register_predicate("lives_in", description="city")
        mem.register_predicate("uses_language", cardinality=Cardinality.MANY)
        mem.set(user_id="u1", predicate="lives_in", value="Delhi")
        mem.set(user_id="u1", predicate="lives_in", value="Bangalore")
        mem.add_value(user_id="u1", predicate="uses_language", value="Python")

        snap = mem.extract_snapshot(user_id="u1")
        assert snap.reference_time == "2026-10-18"
        names = {item.name: item for item in snap.registry}
        assert names["lives_in"].cardinality is Cardinality.ONE
        assert names["uses_language"].cardinality is Cardinality.MANY
        pairs = {(fact.predicate, fact.object) for fact in snap.facts}
        assert pairs == {("lives_in", "Bangalore"), ("uses_language", "Python")}


def test_unknown_user_has_registry_only() -> None:
    clock = FrozenClock(datetime(2026, 10, 18, 11, 0, 0, tzinfo=UTC))
    with Memory(":memory:", clock=clock) as mem:
        mem.register_predicate("lives_in")
        snap = mem.extract_snapshot(user_id="nobody")
        assert [item.name for item in snap.registry] == ["lives_in"]
        assert snap.facts == ()

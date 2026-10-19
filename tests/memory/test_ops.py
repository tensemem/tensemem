from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path

from tensemem import FakeExtractor, Memory
from tensemem.core.clock import FrozenClock
from tensemem.core.models import Cardinality


def test_backup_round_trips_state(tmp_path: Path) -> None:
    dest = tmp_path / "copy.db"
    with _memory() as mem:
        mem.register_predicate("lives_in")
        mem.set(user_id="u1", predicate="lives_in", value="Delhi")
        mem.backup(dest)
    with Memory(dest) as restored:
        assert restored.state(user_id="u1").values == {"lives_in": "Delhi"}


def test_export_import_replays_explicit_ops() -> None:
    with _memory() as mem:
        mem.register_predicate("lives_in")
        mem.register_predicate("uses_language", cardinality=Cardinality.MANY)
        mem.set(user_id="u1", predicate="lives_in", value="Delhi")
        mem.add_value(user_id="u1", predicate="uses_language", value="Rust")
        dump = mem.export_jsonl("u1")
    with _memory() as other:
        assert other.import_jsonl("u1", dump) >= 2
        assert other.state(user_id="u1").values == {
            "lives_in": "Delhi",
            "uses_language": ("Rust",),
        }


def test_rebuild_replays_explicit_ops_and_keeps_corrections() -> None:
    with _memory() as mem:
        mem.register_predicate("lives_in")
        mem.set(user_id="u1", predicate="lives_in", value="Delhi")
        mem.set(user_id="u1", predicate="lives_in", value="Bangalore")
        history = mem.history(user_id="u1", predicate="lives_in")
        bangalore = next(fact for fact in history.facts if fact.object == "Bangalore")
        mem.correct(bangalore.id)
        assert mem.state(user_id="u1").values == {"lives_in": "Delhi"}
        version = mem.rebuild("u1")
        assert version == 2
        assert mem.state(user_id="u1").values == {"lives_in": "Delhi"}
        history = mem.history(user_id="u1", predicate="lives_in")
        assert all(fact.object != "Bangalore" for fact in history.facts)
        assert history.values == {"lives_in": "Delhi"}


def test_rebuild_reextracts_messages() -> None:
    clock = FrozenClock(datetime(2026, 10, 18, 11, 0, 0, tzinfo=UTC))
    with Memory(":memory:", clock=clock, llm=FakeExtractor()) as mem:
        mem.register_predicate("lives_in")
        mem.add("u1", "I live in Delhi", wait=True)
        assert mem.state(user_id="u1").values == {"lives_in": "Delhi"}
        mem.rebuild("u1", wait=True)
        assert mem.state(user_id="u1").values == {"lives_in": "Delhi"}
        assert mem.state(user_id="u1").freshness.is_current


def test_stats_and_hooks_see_writes() -> None:
    events: list[str] = []

    def boom(_name: str, _payload: Mapping[str, object]) -> None:
        raise RuntimeError("hook must not fail the write")

    clock = FrozenClock(datetime(2026, 10, 18, 11, 0, 0, tzinfo=UTC))
    with Memory(":memory:", clock=clock, hooks=[lambda name, _: events.append(name), boom]) as mem:
        mem.register_predicate("lives_in")
        mem.set(user_id="u1", predicate="lives_in", value="Delhi")
        stats = mem.stats("u1")
        assert stats.facts == 1
        assert stats.episodes == 1
        assert stats.queue_depth == 0
        assert stats.estimated_tokens >= 0
        assert "commit" in events


def _memory() -> Memory:
    clock = FrozenClock(datetime(2026, 10, 18, 11, 0, 0, tzinfo=UTC))
    return Memory(":memory:", clock=clock)

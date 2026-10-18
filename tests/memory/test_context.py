from datetime import UTC, datetime

import pytest

from tensemem import Memory
from tensemem.core.clock import FrozenClock
from tensemem.core.models import Cardinality, OnStale, StaleMemoryError


def test_context_is_fenced_and_fresh() -> None:
    with _memory() as mem:
        mem.register_predicate("lives_in")
        mem.register_predicate("uses_language", cardinality=Cardinality.MANY)
        added = mem.set(user_id="u1", predicate="lives_in", value="Bangalore")
        mem.add_value(user_id="u1", predicate="uses_language", value="Rust")

        ctx = mem.context(user_id="u1")
        assert ctx.freshness.is_current
        assert ctx.freshness.as_of_seq == added.seq or ctx.freshness.as_of_seq >= added.seq
        assert "<tensemem-context tag=" in ctx.text
        assert "- lives in: Bangalore" in ctx.text
        assert "Rust" in ctx.text
        assert "What I know" not in mem.unfence(ctx.text)
        assert ctx.facts_used


def test_context_query_and_token_budget() -> None:
    with _memory() as mem:
        mem.register_predicate("lives_in")
        mem.register_predicate("diet")
        mem.set(user_id="u1", predicate="lives_in", value="Bangalore")
        mem.set(user_id="u1", predicate="diet", value="vegetarian")

        rust_first = mem.context(user_id="u1", query="diet")
        diet_line = next(line for line in rust_first.text.splitlines() if line.startswith("- "))
        assert "diet" in diet_line

        tiny = mem.context(user_id="u1", max_tokens=3)
        assert tiny.facts_used == ()


def test_min_seq_raise_and_custom_fence() -> None:
    with _memory() as mem:
        mem.register_predicate("lives_in")
        mem.set(user_id="u1", predicate="lives_in", value="Delhi")
        with pytest.raises(StaleMemoryError):
            mem.context(user_id="u1", min_seq=99, on_stale=OnStale.RAISE)
        flagged = mem.context(user_id="u1", min_seq=99)
        assert flagged.freshness.as_of_seq < 99
        custom = mem.fence("hello")
        assert "hello" in custom
        assert "hello" not in mem.unfence(custom)


def _memory() -> Memory:
    clock = FrozenClock(datetime(2026, 10, 18, 11, 0, 0, tzinfo=UTC))
    return Memory(":memory:", clock=clock)

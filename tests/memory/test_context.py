from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any, TypeVar

import pytest
from pydantic import BaseModel

from tensemem import FakeExtractor, Memory
from tensemem.core.clock import FrozenClock
from tensemem.core.models import Cardinality, StaleMemoryError
from tensemem.providers.llm.base import LLMProvider, ProviderError

T = TypeVar("T", bound=BaseModel)


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
        assert "- `lives in`: `Bangalore`" in ctx.text
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
        assert tiny.text == ""
        assert tiny.token_count == 0


def test_context_wait_applies_the_message() -> None:
    with _memory(llm=FakeExtractor()) as mem:
        mem.register_predicate("lives_in")
        added = mem.add("u1", "I live in Delhi")
        ctx = mem.context("u1", min_seq=added.seq, wait=2.0)
        assert ctx.freshness.as_of_seq >= added.seq
        assert "Delhi" in ctx.text


def test_context_wait_times_out_and_raises() -> None:
    with _memory(llm=_Boom()) as mem:
        mem.register_predicate("lives_in")
        added = mem.add("u1", "I live in Delhi")
        with pytest.raises(StaleMemoryError):
            mem.context("u1", min_seq=added.seq, wait=0.2, on_stale="raise")


def test_context_includes_unprocessed_messages() -> None:
    with _memory() as mem:
        mem.register_predicate("lives_in")
        mem.set(user_id="u1", predicate="lives_in", value="Delhi")
        mem.add("u1", "I just got a dog")
        ctx = mem.context("u1")
        assert ctx.freshness.is_current is False
        assert "Said recently" in ctx.text
        assert "I just got a dog" in ctx.text
        assert "`lives in`: `Delhi`" in ctx.text


def test_context_hot_buffer_hides_secrets() -> None:
    with _memory() as mem:
        mem.add("u1", "I live in Delhi sk-abcdefghijklmnopqrstuvwxyz123456")
        ctx = mem.context("u1")
        assert "sk-abcdefgh" not in ctx.text
        assert "[REDACTED]" in ctx.text


def test_min_seq_raise_and_custom_fence() -> None:
    with _memory() as mem:
        mem.register_predicate("lives_in")
        mem.set(user_id="u1", predicate="lives_in", value="Delhi")
        with pytest.raises(StaleMemoryError):
            mem.context(user_id="u1", min_seq=99, on_stale="raise")
        with pytest.raises(ValueError, match="nope"):
            mem.context(user_id="u1", on_stale="nope")
        flagged = mem.context(user_id="u1", min_seq=99)
        assert flagged.freshness.as_of_seq < 99
        custom = mem.fence("hello")
        assert "hello" in custom
        assert "hello" not in mem.unfence(custom)


class _Boom:
    model = "boom"

    def structured(
        self,
        messages: Sequence[Mapping[str, str]],
        schema: type[T],
        **kwargs: Any,
    ) -> T:
        del messages, schema, kwargs
        raise ProviderError("down")


def _memory(*, llm: LLMProvider | None = None) -> Memory:
    clock = FrozenClock(datetime(2026, 10, 18, 11, 0, 0, tzinfo=UTC))
    return Memory(":memory:", clock=clock, llm=llm)

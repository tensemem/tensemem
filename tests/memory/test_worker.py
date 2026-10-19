import threading
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any, TypeVar

import pytest
from pydantic import BaseModel

from tensemem import FakeExtractor, Memory
from tensemem.core.clock import FrozenClock
from tensemem.core.models import Cardinality, JobStatus
from tensemem.providers.llm.base import LLMProvider, ProviderError, last_user_text

T = TypeVar("T", bound=BaseModel)


def test_flush_extracts_and_advances_watermark() -> None:
    with _memory() as mem:
        mem.register_predicate("lives_in")
        mem.add("u1", "I live in Delhi")
        mem.flush()
        state = mem.state("u1")
        assert state.values == {"lives_in": "Delhi"}
        assert state.freshness.is_current
        assert mem.jobs("u1")[0].status is JobStatus.DONE


def test_add_wait_applies_before_returning() -> None:
    with _memory() as mem:
        mem.register_predicate("lives_in")
        mem.add("u1", "I live in Delhi", wait=True)
        assert mem.state("u1").values == {"lives_in": "Delhi"}
        assert mem.state("u1").freshness.is_current


def test_later_message_supersedes() -> None:
    with _memory() as mem:
        mem.register_predicate("lives_in")
        mem.add("u1", "I live in Delhi", wait=True)
        mem.add("u1", "I moved to Bangalore", wait=True)
        assert mem.state("u1").values == {"lives_in": "Bangalore"}


def test_empty_message_is_skipped() -> None:
    with _memory() as mem:
        mem.register_predicate("lives_in")
        mem.add("u1", "   ", wait=True)
        state = mem.state("u1")
        assert state.values == {}
        assert state.freshness.is_current
        assert mem.jobs("u1")[0].status is JobStatus.DONE


def test_unknown_predicate_completes_without_facts() -> None:
    with _memory() as mem:
        mem.add("u1", "I live in Delhi", wait=True)
        state = mem.state("u1")
        assert state.values == {}
        assert state.freshness.is_current


def test_provider_error_requeues_the_job() -> None:
    with _memory(llm=_Boom()) as mem:
        mem.register_predicate("lives_in")
        mem.add("u1", "I live in Delhi")
        mem.flush()
        job = mem.jobs("u1")[0]
        assert job.status is JobStatus.QUEUED
        assert job.attempts == 1
        assert job.last_error == "down"
        assert mem.state("u1").freshness.is_current is False


def test_flush_without_provider_raises_when_jobs_exist() -> None:
    with Memory(":memory:", clock=_clock()) as mem:
        mem.add("u1", "I live in Delhi")
        with pytest.raises(RuntimeError, match="needs Memory"):
            mem.flush()
        with pytest.raises(RuntimeError, match="needs Memory"):
            mem.add("u1", "I moved to Bangalore", wait=True)


def test_flush_is_noop_when_the_queue_is_idle() -> None:
    with Memory(":memory:", clock=_clock()) as mem:
        mem.flush()


def test_add_wait_does_not_block_on_another_scope() -> None:
    hold = threading.Event()
    started = threading.Event()

    class Gated:
        model = "gated"

        def structured(
            self,
            messages: Sequence[Mapping[str, str]],
            schema: type[T],
            **kwargs: Any,
        ) -> T:
            if "hold" in last_user_text(messages):
                started.set()
                assert hold.wait(timeout=5)
            inner = FakeExtractor()
            return inner.structured(messages, schema, **kwargs)

    with Memory(":memory:", clock=_clock(), llm=Gated()) as mem:
        mem.register_predicate("lives_in")
        try:
            mem.add("u2", "please hold, I live in Delhi")
            assert started.wait(timeout=5)
            mem.add("u1", "I live in Delhi", wait=True)
            assert mem.state("u1").values == {"lives_in": "Delhi"}
        finally:
            hold.set()


def test_language_replace_set() -> None:
    with _memory() as mem:
        mem.register_predicate("lives_in")
        mem.register_predicate("uses_language", cardinality=Cardinality.MANY)
        mem.add("u1", "I moved to Bangalore last week and now only write Rust.", wait=True)
        assert mem.state("u1").values == {
            "lives_in": "Bangalore",
            "uses_language": ("Rust",),
        }


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


def _clock() -> FrozenClock:
    return FrozenClock(datetime(2026, 10, 18, 11, 0, 0, tzinfo=UTC))


def _memory(*, llm: LLMProvider | None = None) -> Memory:
    return Memory(":memory:", clock=_clock(), llm=llm or FakeExtractor())

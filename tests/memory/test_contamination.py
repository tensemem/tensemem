from datetime import UTC, datetime

from tensemem import FakeExtractor, Memory
from tensemem.core.clock import FrozenClock
from tensemem.core.models import ExtractedOp, ExtractionResult, FactStatus, OpKind
from tensemem.providers.llm.base import LLMProvider


def test_echoed_context_does_not_change_facts() -> None:
    fake = FakeExtractor()
    with _memory(llm=fake) as mem:
        mem.register_predicate("lives_in")
        mem.add("u1", "I live in Delhi", wait=True)
        calls = len(fake.calls)
        fact = mem.state("u1").facts[0]
        ctx = mem.context("u1")
        for _ in range(20):
            mem.add("u1", ctx.text, wait=True)
        state = mem.state("u1")
        assert len(fake.calls) == calls
        assert state.values == {"lives_in": "Delhi"}
        assert state.facts[0].id == fact.id
        assert state.facts[0].confidence == fact.confidence
        assert state.freshness.is_current


def test_invented_evidence_is_dropped() -> None:
    fake = FakeExtractor(
        {
            "hello there": ExtractionResult(
                ops=(_op("Delhi", OpKind.SET, evidence="I live in Delhi"),)
            )
        }
    )
    with _memory(llm=fake) as mem:
        mem.register_predicate("lives_in")
        mem.add("u1", "hello there", wait=True)
        assert mem.state("u1").values == {}


def test_user_text_beside_a_fence_still_extracts() -> None:
    with _memory() as mem:
        mem.register_predicate("lives_in")
        mem.add("u1", "I live in Delhi", wait=True)
        ctx = mem.context("u1")
        mem.add("u1", ctx.text + "I moved to Bangalore", wait=True)
        assert mem.state("u1").values == {"lives_in": "Bangalore"}


def test_confirmation_cannot_create_a_fact() -> None:
    fake = FakeExtractor({"yes": ExtractionResult(ops=(_op("Delhi", OpKind.SET, evidence="yes"),))})
    with _memory(llm=fake) as mem:
        mem.register_predicate("lives_in")
        mem.add("u1", "yes", wait=True)
        assert mem.state("u1").values == {}


def test_confirmation_reinforces_a_matching_fact() -> None:
    fake = FakeExtractor({"yes": ExtractionResult(ops=(_op("Delhi", OpKind.SET, evidence="yes"),))})
    with _memory(llm=fake) as mem:
        mem.register_predicate("lives_in")
        mem.add("u1", "I live in Delhi", wait=True)
        fact = mem.state("u1").facts[0]
        mem.add("u1", "yes", wait=True)
        state = mem.state("u1")
        assert state.values == {"lives_in": "Delhi"}
        assert state.facts[0].id == fact.id
        explained = mem.explain(fact.id)
        assert any(event.reason == "same_value" for event in explained.events)


def test_deny_restores_the_displaced_value() -> None:
    fake = FakeExtractor(
        {
            "I never lived in Bangalore": ExtractionResult(
                ops=(
                    _op(
                        "Bangalore",
                        OpKind.DENY,
                        evidence="I never lived in Bangalore",
                    ),
                )
            )
        }
    )
    with _memory(llm=fake) as mem:
        mem.register_predicate("lives_in")
        mem.add("u1", "I live in Delhi", wait=True)
        mem.add("u1", "I moved to Bangalore", wait=True)
        mem.add("u1", "I never lived in Bangalore", wait=True)
        assert mem.state("u1").values == {"lives_in": "Delhi"}
        history = mem.history("u1", predicate="lives_in")
        assert [fact.object for fact in history.facts] == ["Delhi"]
        assert history.facts[0].status is FactStatus.ACTIVE


def _op(city: str, kind: OpKind, *, evidence: str) -> ExtractedOp:
    return ExtractedOp(
        subject="user",
        predicate="lives_in",
        object=city,
        op=kind,
        evidence=evidence,
    )


def _memory(*, llm: LLMProvider | None = None) -> Memory:
    clock = FrozenClock(datetime(2026, 10, 18, 11, 0, 0, tzinfo=UTC))
    return Memory(":memory:", clock=clock, llm=llm or FakeExtractor())

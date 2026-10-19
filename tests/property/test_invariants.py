"""Property tests for the engine invariants in design §17.1."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from datetime import UTC, datetime

from hypothesis import assume, given
from hypothesis import strategies as st

from tensemem import FakeExtractor, Memory
from tensemem.core.clock import FrozenClock
from tensemem.core.models import Cardinality, FactStatus, FactView

_CITIES = ("Delhi", "Bangalore", "Pune", "Mumbai")
_LANGS = ("Python", "Rust", "Go")
_UTTERANCES = (
    "I live in Delhi",
    "I moved to Bangalore",
    "I live in Pune",
    "I write Python",
    "I write Go",
    "I now only write Rust",
    "thanks",
)

_city = st.sampled_from(_CITIES)
_lang = st.sampled_from(_LANGS)
_action = st.one_of(
    _city.map(lambda value: ("set_city", value)),
    _lang.map(lambda value: ("add_lang", value)),
    _lang.map(lambda value: ("remove_lang", value)),
)


@given(st.lists(_action, min_size=1, max_size=12))
def test_one_active_fact_per_one_slot(actions: list[tuple[str, str]]) -> None:
    with _handle() as (mem, clock):
        _apply(mem, clock, actions)
        _assert_slot_invariant(mem.history("u1").facts)


@given(_city, _lang)
def test_independent_predicates_commute(city: str, lang: str) -> None:
    first = _final_values([("set_city", city), ("add_lang", lang)])
    second = _final_values([("add_lang", lang), ("set_city", city)])
    assert first == second


@given(st.lists(_action, min_size=1, max_size=10))
def test_rebuild_replays_explicit_ops(actions: list[tuple[str, str]]) -> None:
    with _handle() as (mem, clock):
        _apply(mem, clock, actions)
        before = _signature(mem)
        mem.rebuild("u1")
        assert _signature(mem) == before
        _assert_slot_invariant(mem.history("u1").facts)


@given(st.lists(_action, min_size=1, max_size=8))
def test_forget_leaves_no_content(actions: list[tuple[str, str]]) -> None:
    with _handle() as (mem, clock):
        _apply(mem, clock, actions)
        mem.forget("u1")
        assert mem.state("u1").facts == ()
        assert mem.history("u1").facts == ()
        assert mem.stats("u1").episodes == 0
        assert mem.stats("u1").facts == 0


@given(st.lists(st.sampled_from(_UTTERANCES), min_size=1, max_size=6))
def test_watermark_is_monotonic_and_catches_up(texts: list[str]) -> None:
    with _handle(llm=True) as (mem, clock):
        last = 0
        for text in texts:
            clock.advance(seconds=1)
            mem.add("u1", text, wait=True)
            fresh = mem.state("u1").freshness
            assert fresh.as_of_seq >= last
            assert fresh.as_of_seq == fresh.latest_seq
            assert fresh.pending == 0
            assert fresh.failed == 0
            last = fresh.as_of_seq


@given(st.sampled_from(_UTTERANCES))
def test_watermark_does_not_pass_a_pending_episode(text: str) -> None:
    with _handle(llm=True) as (mem, clock):
        clock.advance(seconds=1)
        added = mem.add("u1", text, wait=False)
        fresh = mem.state("u1").freshness
        assert fresh.pending >= 1
        assert fresh.as_of_seq < added.seq
        assert fresh.as_of_seq <= fresh.latest_seq
        assert not fresh.is_current
        mem.flush()
        caught = mem.state("u1").freshness
        assert caught.as_of_seq >= added.seq
        assert caught.pending == 0


@given(st.lists(_city, min_size=2, max_size=6))
def test_correction_restores_superseded_then_survives_rebuild(cities: list[str]) -> None:
    unique = list(dict.fromkeys(cities))
    assume(len(unique) >= 2)
    with _handle() as (mem, clock):
        for city in unique:
            clock.advance(seconds=1)
            mem.set(user_id="u1", predicate="lives_in", value=city)
        history = [fact for fact in mem.history("u1", "lives_in").facts if fact.subject == "user"]
        active = next(fact for fact in history if fact.status is FactStatus.ACTIVE)
        displaced = [
            fact
            for fact in history
            if fact.status is FactStatus.SUPERSEDED
            and mem.explain(fact.id).superseded_by == active.id
        ]
        assume(len(displaced) == 1)
        mem.correct(active.id)
        assert mem.state("u1").values == {"lives_in": displaced[0].object}
        mem.rebuild("u1")
        assert all(fact.object != active.object for fact in mem.history("u1", "lives_in").facts)
        assert mem.state("u1").values == {"lives_in": displaced[0].object}


@given(_city)
def test_echoed_context_does_not_change_state(city: str) -> None:
    with _handle(llm=True) as (mem, clock):
        clock.advance(seconds=1)
        mem.add("u1", f"I live in {city}", wait=True)
        before = _fact_sig(mem.state("u1").facts)
        ctx = mem.context("u1")
        clock.advance(seconds=1)
        mem.add("u1", ctx.text, wait=True)
        assert _fact_sig(mem.state("u1").facts) == before


@given(st.lists(_city, min_size=1, max_size=8))
def test_supersession_chain_is_acyclic(cities: list[str]) -> None:
    with _handle() as (mem, clock):
        for city in cities:
            clock.advance(seconds=1)
            mem.set(user_id="u1", predicate="lives_in", value=city)
        facts = [fact for fact in mem.history("u1", "lives_in").facts if fact.subject == "user"]
        _assert_slot_invariant(facts)
        by_id = {fact.id: fact for fact in facts}
        for fact in facts:
            seen: set[str] = set()
            nxt = mem.explain(fact.id).superseded_by
            prev_seq = fact.recorded_seq
            while nxt is not None:
                assert nxt not in seen
                seen.add(nxt)
                nxt_fact = by_id.get(nxt)
                if nxt_fact is None:
                    break
                assert nxt_fact.recorded_seq >= prev_seq
                prev_seq = nxt_fact.recorded_seq
                nxt = mem.explain(nxt).superseded_by


class _Handle:
    def __init__(self, mem: Memory, clock: FrozenClock) -> None:
        self._mem = mem
        self._clock = clock

    def __enter__(self) -> tuple[Memory, FrozenClock]:
        return self._mem, self._clock

    def __exit__(self, *exc: object) -> None:
        self._mem.close()


def _handle(*, llm: bool = False) -> _Handle:
    clock = FrozenClock(datetime(2026, 10, 18, 11, 0, 0, tzinfo=UTC))
    mem = Memory(
        ":memory:",
        clock=clock,
        llm=FakeExtractor() if llm else None,
        start_worker=False,
    )
    mem.register_predicate("lives_in")
    mem.register_predicate("uses_language", cardinality=Cardinality.MANY)
    return _Handle(mem, clock)


def _apply(mem: Memory, clock: FrozenClock, actions: Sequence[tuple[str, str]]) -> None:
    for kind, value in actions:
        clock.advance(seconds=1)
        if kind == "set_city":
            mem.set(user_id="u1", predicate="lives_in", value=value)
        elif kind == "add_lang":
            mem.add_value(user_id="u1", predicate="uses_language", value=value)
        else:
            mem.remove_value(user_id="u1", predicate="uses_language", value=value)


def _final_values(actions: Sequence[tuple[str, str]]) -> dict[str, str | tuple[str, ...]]:
    with _handle() as (mem, clock):
        _apply(mem, clock, actions)
        return dict(mem.state("u1").values)


def _assert_slot_invariant(facts: Sequence[FactView]) -> None:
    active: dict[tuple[str, str, str], int] = defaultdict(int)
    for fact in facts:
        if fact.status is not FactStatus.ACTIVE:
            continue
        object_key = fact.object if fact.cardinality is Cardinality.MANY else ""
        active[(fact.subject, fact.predicate, object_key)] += 1
    assert all(count == 1 for count in active.values())


def _signature(mem: Memory) -> tuple[tuple[str, str, str, str], ...]:
    return tuple(
        sorted(
            (fact.subject, fact.predicate, fact.object, fact.status.value)
            for fact in mem.history("u1").facts
        )
    )


def _fact_sig(facts: Sequence[FactView]) -> tuple[tuple[str, str, str, float, str], ...]:
    return tuple(
        sorted(
            (
                fact.subject,
                fact.predicate,
                fact.object,
                round(fact.confidence, 6),
                fact.id,
            )
            for fact in facts
            if fact.status is FactStatus.ACTIVE
        )
    )

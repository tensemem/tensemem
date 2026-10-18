from datetime import UTC, datetime

from tensemem import Memory
from tensemem.core.clock import FrozenClock
from tensemem.core.models import ExtractedOp, Modality, OpKind, ValidPrecision
from tensemem.core.resolver import FactSnap, Snapshot, resolve
from tensemem.pipeline.policy import planned_predicate


def test_normalize_fills_iso_date() -> None:
    with _memory() as mem:
        mem.register_predicate("lives_in")
        incoming = mem.normalize(
            "u1",
            (_op(object="Bangalore", valid_from="2026-03-01", evidence="I moved in March"),),
            reference_time="2026-10-18T11:00:00.000000Z",
        )
        assert incoming[0].op.valid_from == "2026-03-01T00:00:00.000000Z"
        assert incoming[0].op.valid_precision is ValidPrecision.DAY


def test_normalize_falls_back_to_evidence_phrase() -> None:
    with _memory() as mem:
        mem.register_predicate("lives_in")
        incoming = mem.normalize(
            "u1",
            (_op(object="Bangalore", evidence="I moved last week"),),
            reference_time="2026-10-18",
        )
        assert incoming[0].op.valid_from == "2026-10-11T00:00:00.000000Z"
        assert incoming[0].op.valid_precision is ValidPrecision.DAY


def test_planned_lands_on_companion_predicate() -> None:
    with _memory() as mem:
        mem.register_predicate("lives_in")
        incoming = mem.normalize(
            "u1",
            (_op(object="Bangalore", modality=Modality.PLANNED, evidence="I'm going to move"),),
        )
        assert incoming[0].op.predicate == planned_predicate("lives_in")
        assert incoming[0].op.modality is Modality.ASSERTED
        mutations = resolve(incoming, Snapshot())
        assert mutations[0].kind == "insert_active"
        assert mutations[0].op.predicate == "plans_to_lives_in"


def test_planned_does_not_touch_the_real_slot() -> None:
    with _memory() as mem:
        mem.register_predicate("lives_in")
        mem.set(user_id="u1", predicate="lives_in", value="Delhi")
        incoming = mem.normalize(
            "u1",
            (
                _op(
                    object="Bangalore",
                    modality=Modality.PLANNED,
                    evidence="I might move next month",
                ),
            ),
        )
        mutations = resolve(
            incoming,
            Snapshot(
                facts=(
                    FactSnap(
                        id="f1",
                        subject="user",
                        predicate="lives_in",
                        object_norm="delhi",
                        confidence=0.9,
                    ),
                )
            ),
        )
        assert mutations[0].kind == "insert_active"
        assert mutations[0].op.predicate == "plans_to_lives_in"
        assert mem.state(user_id="u1").values == {"lives_in": "Delhi"}


def test_negated_set_becomes_retract() -> None:
    with _memory() as mem:
        mem.register_predicate("lives_in")
        incoming = mem.normalize(
            "u1",
            (
                _op(
                    object="Delhi",
                    modality=Modality.NEGATED,
                    evidence="I don't live in Delhi anymore",
                ),
            ),
        )
        assert incoming[0].op.op is OpKind.RETRACT
        assert incoming[0].op.modality is Modality.ASSERTED


def test_hypothetical_stays_for_the_resolver() -> None:
    with _memory() as mem:
        mem.register_predicate("lives_in")
        incoming = mem.normalize(
            "u1",
            (_op(object="Pune", modality=Modality.HYPOTHETICAL, evidence="if I lived in Pune"),),
        )
        assert incoming[0].op.modality is Modality.HYPOTHETICAL
        mutations = resolve(incoming, Snapshot())
        assert mutations[0].kind == "drop"
        assert mutations[0].reason == "hypothetical"


def test_low_confidence_is_left_for_the_resolver() -> None:
    with _memory() as mem:
        mem.register_predicate("lives_in")
        incoming = mem.normalize("u1", (_op(object="Pune", confidence=0.2, evidence="maybe Pune"),))
        assert incoming[0].op.confidence == 0.2
        assert resolve(incoming, Snapshot())[0].reason == "low_confidence"


def _op(
    *,
    object: str,
    evidence: str,
    valid_from: str | None = None,
    modality: Modality = Modality.ASSERTED,
    confidence: float = 0.95,
) -> ExtractedOp:
    return ExtractedOp(
        subject="user",
        predicate="lives_in",
        object=object,
        op=OpKind.SET,
        modality=modality,
        valid_from=valid_from,
        confidence=confidence,
        evidence=evidence,
    )


def _memory() -> Memory:
    return Memory(":memory:", clock=FrozenClock(datetime(2026, 10, 18, 11, 0, 0, tzinfo=UTC)))

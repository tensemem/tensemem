from tensemem.core.models import Cardinality, ExtractedOp, Modality, OpKind, ValidPrecision
from tensemem.core.resolver import (
    FactSnap,
    IncomingOp,
    RejectedClaim,
    Snapshot,
    resolve,
)


def test_set_with_no_active_fact_inserts() -> None:
    mutations = resolve([_set("Bangalore")], Snapshot())
    assert [m.kind for m in mutations] == ["insert_active"]
    assert mutations[0].reason == "no_active_fact"


def test_set_same_value_reinforces() -> None:
    mutations = resolve([_set("Delhi")], Snapshot(facts=(_fact("Delhi", id="f1"),)))
    assert mutations[0].kind == "reinforce"
    assert mutations[0].target_fact_id == "f1"


def test_set_newer_value_supersedes() -> None:
    mutations = resolve(
        [_set("Bangalore", valid_from="2026-06-01T00:00:00.000000Z")],
        Snapshot(
            facts=(
                _fact(
                    "Delhi",
                    id="f1",
                    valid_from="2026-01-01T00:00:00.000000Z",
                    valid_precision=ValidPrecision.DAY,
                ),
            )
        ),
    )
    assert mutations[0].kind == "supersede"
    assert mutations[0].target_fact_id == "f1"


def test_set_older_value_is_historical() -> None:
    mutations = resolve(
        [
            _set(
                "Mumbai",
                valid_from="2025-01-01T00:00:00.000000Z",
                valid_precision=ValidPrecision.DAY,
            )
        ],
        Snapshot(
            facts=(
                _fact(
                    "Delhi",
                    id="f1",
                    valid_from="2026-01-01T00:00:00.000000Z",
                    valid_precision=ValidPrecision.DAY,
                ),
            )
        ),
    )
    assert mutations[0].kind == "insert_historical"


def test_overlapping_month_and_day_supersede() -> None:
    mutations = resolve(
        [
            _set(
                "Bangalore",
                valid_from="2026-10-10T00:00:00.000000Z",
                valid_precision=ValidPrecision.DAY,
            )
        ],
        Snapshot(
            facts=(
                _fact(
                    "Delhi",
                    id="f1",
                    valid_from="2026-10-01T00:00:00.000000Z",
                    valid_precision=ValidPrecision.MONTH,
                ),
            )
        ),
    )
    assert mutations[0].kind == "supersede"


def test_unknown_dates_supersede() -> None:
    mutations = resolve([_set("Bangalore")], Snapshot(facts=(_fact("Delhi", id="f1"),)))
    assert mutations[0].kind == "supersede"


def test_low_confidence_conflict_is_candidate() -> None:
    mutations = resolve(
        [_set("Pune", confidence=0.6)],
        Snapshot(facts=(_fact("Delhi", id="f1"),)),
    )
    assert mutations[0].kind == "insert_candidate"


def test_below_min_confidence_is_dropped() -> None:
    mutations = resolve([_set("Pune", confidence=0.2)], Snapshot())
    assert mutations[0].kind == "drop"
    assert mutations[0].reason == "low_confidence"


def test_hypothetical_and_planned_are_dropped() -> None:
    hypo = resolve(
        [_incoming(_op(OpKind.SET, "Pune", modality=Modality.HYPOTHETICAL))],
        Snapshot(),
    )
    planned = resolve(
        [_incoming(_op(OpKind.SET, "Pune", modality=Modality.PLANNED))],
        Snapshot(),
    )
    assert hypo[0].reason == "hypothetical"
    assert planned[0].reason == "planned"


def test_confirmation_cannot_create_or_supersede() -> None:
    create = resolve(
        [_incoming(_op(OpKind.SET, "Delhi", is_confirmation=True))],
        Snapshot(),
    )
    supersede = resolve(
        [_incoming(_op(OpKind.SET, "Bangalore", is_confirmation=True))],
        Snapshot(facts=(_fact("Delhi", id="f1"),)),
    )
    reinforce = resolve(
        [_incoming(_op(OpKind.SET, "Delhi", is_confirmation=True))],
        Snapshot(facts=(_fact("Delhi", id="f1"),)),
    )
    assert create[0].reason == "confirmation_without_match"
    assert supersede[0].reason == "confirmation_without_match"
    assert reinforce[0].kind == "reinforce"


def test_rejected_claim_blocks_until_seq() -> None:
    claim = RejectedClaim(subject="user", predicate="lives_in", object_norm="pune", until_seq=10)
    blocked = resolve(
        [_set("Pune")],
        Snapshot(episode_seq=10, rejected_claims=(claim,)),
    )
    allowed = resolve(
        [_set("Pune")],
        Snapshot(episode_seq=11, rejected_claims=(claim,)),
    )
    assert blocked[0].reason == "rejected_claim"
    assert allowed[0].kind == "insert_active"


def test_retract_matching_active() -> None:
    mutations = resolve(
        [_incoming(_op(OpKind.RETRACT, "Delhi"))],
        Snapshot(facts=(_fact("Delhi", id="f1"),)),
    )
    assert mutations[0].kind == "retract"
    assert mutations[0].target_fact_id == "f1"


def test_add_is_per_value_on_many() -> None:
    rust = IncomingOp(
        op=_op(OpKind.ADD, "Rust", predicate="uses_language"),
        object_norm="rust",
        cardinality=Cardinality.MANY,
    )
    mutations = resolve(
        [rust],
        Snapshot(
            facts=(
                _fact(
                    "Python",
                    id="f1",
                    predicate="uses_language",
                    object_norm="python",
                ),
            )
        ),
    )
    assert mutations[0].kind == "insert_active"


def test_replace_set_retracts_other_values() -> None:
    rust = IncomingOp(
        op=_op(OpKind.REPLACE_SET, "Rust", predicate="uses_language"),
        object_norm="rust",
        cardinality=Cardinality.MANY,
    )
    mutations = resolve(
        [rust],
        Snapshot(
            facts=(
                _fact("Python", id="py", predicate="uses_language", object_norm="python"),
                _fact("Go", id="go", predicate="uses_language", object_norm="go"),
            )
        ),
    )
    kinds = [(m.kind, m.target_fact_id) for m in mutations]
    assert ("retract", "py") in kinds
    assert ("retract", "go") in kinds
    assert mutations[-1].kind == "insert_active"


def test_second_op_in_batch_sees_first() -> None:
    mutations = resolve(
        [_set("Delhi"), _set("Bangalore")],
        Snapshot(),
    )
    assert [m.kind for m in mutations] == ["insert_active", "supersede"]


def test_deny_rejects_matching_fact() -> None:
    mutations = resolve(
        [_incoming(_op(OpKind.DENY, "Pune"))],
        Snapshot(facts=(_fact("Pune", id="f1", object_norm="pune"),)),
    )
    assert mutations[0].kind == "reject"
    assert mutations[0].target_fact_id == "f1"


def test_deny_then_set_same_value_in_batch_is_dropped() -> None:
    mutations = resolve(
        [_incoming(_op(OpKind.DENY, "Pune")), _set("Pune")],
        Snapshot(episode_seq=5, facts=(_fact("Pune", id="f1", object_norm="pune"),)),
    )
    assert [m.kind for m in mutations] == ["reject", "drop"]
    assert mutations[1].reason == "rejected_claim"


def test_replace_set_confirmation_does_not_retract_others() -> None:
    rust = IncomingOp(
        op=_op(OpKind.REPLACE_SET, "Rust", predicate="uses_language", is_confirmation=True),
        object_norm="rust",
        cardinality=Cardinality.MANY,
    )
    mutations = resolve(
        [rust],
        Snapshot(
            facts=(_fact("Python", id="py", predicate="uses_language", object_norm="python"),)
        ),
    )
    assert [m.kind for m in mutations] == ["drop"]
    assert mutations[0].reason == "confirmation_without_match"


def test_replace_set_low_confidence_does_not_retract_others() -> None:
    rust = IncomingOp(
        op=_op(OpKind.REPLACE_SET, "Rust", predicate="uses_language", confidence=0.6),
        object_norm="rust",
        cardinality=Cardinality.MANY,
    )
    mutations = resolve(
        [rust],
        Snapshot(
            facts=(_fact("Python", id="py", predicate="uses_language", object_norm="python"),)
        ),
    )
    assert [m.kind for m in mutations] == ["insert_active"]


def test_blank_retract_clears_many_value() -> None:
    mutations = resolve(
        [
            IncomingOp(
                op=_op(OpKind.RETRACT, "", predicate="uses_language"),
                object_norm="",
                cardinality=Cardinality.MANY,
            )
        ],
        Snapshot(
            facts=(_fact("Python", id="py", predicate="uses_language", object_norm="python"),)
        ),
    )
    assert mutations[0].kind == "retract"
    assert mutations[0].target_fact_id == "py"


def test_two_subjects_keep_separate_pending_facts() -> None:
    wife = IncomingOp(
        op=_op(OpKind.SET, "Pune", subject="user.wife"),
        object_norm="pune",
        cardinality=Cardinality.ONE,
    )
    mutations = resolve([_set("Pune"), wife, _set("Bangalore")], Snapshot())
    assert [m.kind for m in mutations] == ["insert_active", "insert_active", "supersede"]
    # Only the user's pending city is replaced; the wife's Pune stays in preview.
    assert mutations[2].target_fact_id == "pending:user:lives_in:pune"


def _set(
    city: str,
    *,
    confidence: float = 0.95,
    valid_from: str | None = None,
    valid_precision: ValidPrecision = ValidPrecision.UNKNOWN,
) -> IncomingOp:
    return _incoming(
        _op(
            OpKind.SET,
            city,
            confidence=confidence,
            valid_from=valid_from,
            valid_precision=valid_precision,
        )
    )


def _incoming(op: ExtractedOp, *, cardinality: Cardinality = Cardinality.ONE) -> IncomingOp:
    return IncomingOp(op=op, object_norm=op.object.casefold(), cardinality=cardinality)


def _op(
    kind: OpKind,
    obj: str,
    *,
    subject: str = "user",
    predicate: str = "lives_in",
    confidence: float = 0.95,
    modality: Modality = Modality.ASSERTED,
    valid_from: str | None = None,
    valid_precision: ValidPrecision = ValidPrecision.UNKNOWN,
    is_confirmation: bool = False,
) -> ExtractedOp:
    return ExtractedOp(
        subject=subject,
        predicate=predicate,
        object=obj,
        op=kind,
        confidence=confidence,
        modality=modality,
        valid_from=valid_from,
        valid_precision=valid_precision,
        is_confirmation=is_confirmation,
        evidence="quote",
    )


def _fact(
    obj: str,
    *,
    id: str,
    predicate: str = "lives_in",
    object_norm: str | None = None,
    valid_from: str | None = None,
    valid_precision: ValidPrecision = ValidPrecision.UNKNOWN,
) -> FactSnap:
    return FactSnap(
        id=id,
        subject="user",
        predicate=predicate,
        object_norm=object_norm or obj.casefold(),
        confidence=0.9,
        valid_from=valid_from,
        valid_precision=valid_precision,
    )

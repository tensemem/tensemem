"""Deterministic decision table: typed ops become mutations (ADR 0002).

``resolve`` is a pure function. It does not touch the database. The pipeline
normalizes names and looks up cardinality before calling it;
``tensemem.storage.sqlite.facts.apply_mutations`` writes the result.
"""

from __future__ import annotations

from collections.abc import Iterable

from pydantic import BaseModel, ConfigDict, Field

from tensemem.core.models import (
    Cardinality,
    ExtractedOp,
    FactStatus,
    Modality,
    Mutation,
    OpKind,
    ValidPrecision,
)
from tensemem.core.temporal import is_newer_or_unknown

MIN_CONFIDENCE = 0.5
MIN_SUPERSEDE_CONFIDENCE = 0.75


class FactSnap(BaseModel):
    """One fact as the resolver sees it (usually an ACTIVE row)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    subject: str
    predicate: str
    object_norm: str
    confidence: float = Field(ge=0.0, le=1.0)
    valid_from: str | None = None
    valid_precision: ValidPrecision = ValidPrecision.UNKNOWN
    status: FactStatus = FactStatus.ACTIVE


class IncomingOp(BaseModel):
    """An extracted op plus the registry/normalizer answers resolve must not guess."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    op: ExtractedOp
    object_norm: str
    cardinality: Cardinality


class RejectedClaim(BaseModel):
    """A correction that blocks matching ops up to ``until_seq`` (ADR 0008)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    subject: str
    predicate: str
    object_norm: str
    until_seq: int = Field(ge=0)


class Snapshot(BaseModel):
    """Current facts and corrections the decision table may read."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    facts: tuple[FactSnap, ...] = ()
    rejected_claims: tuple[RejectedClaim, ...] = ()
    episode_seq: int = Field(ge=0, default=0)
    min_confidence: float = Field(default=MIN_CONFIDENCE, ge=0.0, le=1.0)
    min_supersede_confidence: float = Field(default=MIN_SUPERSEDE_CONFIDENCE, ge=0.0, le=1.0)


def resolve(ops: Iterable[IncomingOp], snapshot: Snapshot) -> tuple[Mutation, ...]:
    """Apply the decision table to ``ops``. Later ops see earlier ones in the same batch."""
    working = [fact for fact in snapshot.facts if fact.status is FactStatus.ACTIVE]
    rejected = list(snapshot.rejected_claims)
    mutations: list[Mutation] = []
    for incoming in ops:
        view = snapshot.model_copy(update={"rejected_claims": tuple(rejected)})
        batch = _resolve_one(incoming, working, view)
        mutations.extend(batch)
        working = _preview(working, batch, incoming)
        if any(m.kind == "reject" for m in batch):
            rejected.append(
                RejectedClaim(
                    subject=incoming.op.subject,
                    predicate=incoming.op.predicate,
                    object_norm=incoming.object_norm,
                    until_seq=snapshot.episode_seq,
                )
            )
    return tuple(mutations)


def _resolve_one(
    incoming: IncomingOp, active: list[FactSnap], snapshot: Snapshot
) -> list[Mutation]:
    op = incoming.op

    if op.modality is Modality.HYPOTHETICAL:
        return [_drop(op, "hypothetical")]
    if op.modality is Modality.PLANNED:
        return [_drop(op, "planned")]
    if _is_rejected(incoming, snapshot):
        return [_drop(op, "rejected_claim")]
    if op.confidence < snapshot.min_confidence:
        return [_drop(op, "low_confidence")]
    if op.op is OpKind.DENY:
        return _deny(incoming, active)
    if op.op is OpKind.REPLACE_SET:
        return _replace_set(incoming, active, snapshot)
    if op.op is OpKind.RETRACT:
        return _retract(incoming, active, match_empty=True)
    if op.op is OpKind.REMOVE:
        return _retract(incoming, active, match_empty=False)

    # SET and ADD share the same slot rules; MANY slots are per value.
    return _set_or_add(incoming, active, snapshot)


def _set_or_add(incoming: IncomingOp, active: list[FactSnap], snapshot: Snapshot) -> list[Mutation]:
    op = incoming.op
    current = _active_in_slot(incoming, active)

    if op.is_confirmation and (current is None or current.object_norm != incoming.object_norm):
        return [_drop(op, "confirmation_without_match")]

    if current is None:
        return [Mutation(kind="insert_active", op=op, reason="no_active_fact")]

    if current.object_norm == incoming.object_norm:
        return [Mutation(kind="reinforce", op=op, reason="same_value", target_fact_id=current.id)]

    if op.confidence < snapshot.min_supersede_confidence:
        return [Mutation(kind="insert_candidate", op=op, reason="below_supersede_confidence")]

    if is_newer_or_unknown(
        op.valid_from, op.valid_precision, current.valid_from, current.valid_precision
    ):
        return [Mutation(kind="supersede", op=op, reason="newer_value", target_fact_id=current.id)]
    return [Mutation(kind="insert_historical", op=op, reason="older_than_active")]


def _replace_set(
    incoming: IncomingOp, active: list[FactSnap], snapshot: Snapshot
) -> list[Mutation]:
    """Keep only this value for a MANY predicate: retract the others, then SET this one."""
    # Confirmations and weak guesses must not wipe the other values first.
    if incoming.op.is_confirmation or incoming.op.confidence < snapshot.min_supersede_confidence:
        return _set_or_add(incoming, active, snapshot)
    mutations: list[Mutation] = []
    for fact in _actives_for_predicate(incoming, active):
        if fact.object_norm != incoming.object_norm:
            mutations.append(
                Mutation(
                    kind="retract",
                    op=incoming.op,
                    reason="replace_set",
                    target_fact_id=fact.id,
                )
            )
    retracted = {mutation.target_fact_id for mutation in mutations}
    remaining = [fact for fact in active if fact.id not in retracted]
    mutations.extend(_set_or_add(incoming, remaining, snapshot))
    return mutations


def _retract(incoming: IncomingOp, active: list[FactSnap], *, match_empty: bool) -> list[Mutation]:
    object_blank = incoming.op.object.strip() == ""
    current = _active_in_slot(incoming, active, match_empty=match_empty and object_blank)
    if current is None:
        return [_drop(incoming.op, "nothing_to_retract")]
    if current.object_norm != incoming.object_norm and not (match_empty and object_blank):
        return [_drop(incoming.op, "retract_object_mismatch")]
    return [Mutation(kind="retract", op=incoming.op, reason="retract", target_fact_id=current.id)]


def _deny(incoming: IncomingOp, active: list[FactSnap]) -> list[Mutation]:
    match = next(
        (
            fact
            for fact in active
            if fact.subject == incoming.op.subject
            and fact.predicate == incoming.op.predicate
            and fact.object_norm == incoming.object_norm
        ),
        None,
    )
    if match is None:
        return [_drop(incoming.op, "nothing_to_deny")]
    return [Mutation(kind="reject", op=incoming.op, reason="deny", target_fact_id=match.id)]


def _active_in_slot(
    incoming: IncomingOp, active: list[FactSnap], *, match_empty: bool = False
) -> FactSnap | None:
    matches = [
        fact
        for fact in active
        if fact.subject == incoming.op.subject
        and fact.predicate == incoming.op.predicate
        and (
            incoming.cardinality is Cardinality.ONE
            or fact.object_norm == incoming.object_norm
            or match_empty
        )
    ]
    return matches[0] if matches else None


def _actives_for_predicate(incoming: IncomingOp, active: list[FactSnap]) -> list[FactSnap]:
    return [
        fact
        for fact in active
        if fact.subject == incoming.op.subject and fact.predicate == incoming.op.predicate
    ]


def _is_rejected(incoming: IncomingOp, snapshot: Snapshot) -> bool:
    return any(
        claim.subject == incoming.op.subject
        and claim.predicate == incoming.op.predicate
        and claim.object_norm == incoming.object_norm
        and claim.until_seq >= snapshot.episode_seq
        for claim in snapshot.rejected_claims
    )


def _drop(op: ExtractedOp, reason: str) -> Mutation:
    return Mutation(kind="drop", op=op, reason=reason)


def _preview(
    active: list[FactSnap], mutations: list[Mutation], incoming: IncomingOp
) -> list[FactSnap]:
    """Update the in-memory ACTIVE set so the next op in the batch sees this one."""
    gone = {m.target_fact_id for m in mutations if m.kind in {"supersede", "retract", "reject"}}
    remaining = [fact for fact in active if fact.id not in gone]
    if any(m.kind == "insert_active" or m.kind == "supersede" for m in mutations):
        remaining = [
            fact
            for fact in remaining
            if not (
                incoming.cardinality is Cardinality.ONE
                and fact.subject == incoming.op.subject
                and fact.predicate == incoming.op.predicate
            )
        ]
        remaining.append(
            FactSnap(
                id=(
                    f"pending:{incoming.op.subject}:{incoming.op.predicate}:{incoming.object_norm}"
                ),
                subject=incoming.op.subject,
                predicate=incoming.op.predicate,
                object_norm=incoming.object_norm,
                confidence=incoming.op.confidence,
                valid_from=incoming.op.valid_from,
                valid_precision=incoming.op.valid_precision,
            )
        )
    return remaining

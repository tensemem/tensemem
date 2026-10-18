"""Apply temporal fill and modality rewrites before ``resolve()``.

Confidence thresholds stay in the resolver. This step only prepares ops so
hedged or dated claims cannot silently overwrite a current slot.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence

from tensemem.core.models import ExtractedOp, Modality, OpKind, PredicateSpec
from tensemem.core.normalize import normalize_key
from tensemem.core.resolver import IncomingOp
from tensemem.core.temporal import resolve_valid_time
from tensemem.storage.sqlite.registry import register_predicate

_PLANS_PREFIX = "plans_to"
_RETRACT_FROM = frozenset({OpKind.SET, OpKind.ADD, OpKind.RETRACT})


def apply_policy(
    conn: sqlite3.Connection,
    incoming: Sequence[IncomingOp],
    *,
    reference_time: str,
    now: str,
) -> tuple[IncomingOp, ...]:
    """Fill valid time and rewrite planned / negated ops."""
    prepared: list[IncomingOp] = []
    for item in incoming:
        op = _with_time(item.op, reference_time)
        op = _with_modality(op)
        if op.modality is Modality.PLANNED:
            prepared.append(_rewrite_planned(conn, item, op, now=now))
        else:
            prepared.append(
                IncomingOp(op=op, object_norm=item.object_norm, cardinality=item.cardinality)
            )
    return tuple(prepared)


def planned_predicate(name: str) -> str:
    """Companion slot for a plan, after registry key normalization."""
    key = normalize_key(name)
    prefix = f"{_PLANS_PREFIX}_"
    if key.startswith(prefix):
        return key
    return normalize_key(f"{_PLANS_PREFIX}:{name}")


def _with_time(op: ExtractedOp, reference_time: str) -> ExtractedOp:
    resolved = resolve_valid_time(
        op.valid_from, reference_time=reference_time, evidence=op.evidence
    )
    return op.model_copy(
        update={"valid_from": resolved.valid_from, "valid_precision": resolved.valid_precision}
    )


def _with_modality(op: ExtractedOp) -> ExtractedOp:
    if op.modality is Modality.NEGATED and op.op in _RETRACT_FROM:
        return op.model_copy(update={"op": OpKind.RETRACT, "modality": Modality.ASSERTED})
    return op


def _rewrite_planned(
    conn: sqlite3.Connection,
    item: IncomingOp,
    op: ExtractedOp,
    *,
    now: str,
) -> IncomingOp:
    spec = PredicateSpec(
        name=planned_predicate(op.predicate),
        cardinality=item.cardinality,
        description=f"Planned value for {op.predicate}",
    )
    predicate = register_predicate(conn, spec, now=now)
    rewritten = op.model_copy(update={"predicate": predicate.name, "modality": Modality.ASSERTED})
    return IncomingOp(op=rewritten, object_norm=item.object_norm, cardinality=predicate.cardinality)

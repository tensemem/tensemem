"""Deterministic slot keys for the one-ACTIVE-fact-per-slot invariant.

A slot is ``(scope, subject, predicate)`` for ONE predicates, and that plus
``object_norm`` for MANY. The hash is what the partial unique index stores.
"""

from __future__ import annotations

import hashlib

from tensemem.core.models import Cardinality

_SEP = "\x1f"


def slot_key(
    *,
    scope_id: int,
    subject_id: int,
    predicate_id: int,
    cardinality: Cardinality,
    object_norm: str = "",
) -> str:
    """Return the storage key for one fact slot."""
    parts = [str(scope_id), str(subject_id), str(predicate_id)]
    if cardinality is Cardinality.MANY:
        parts.append(object_norm)
    payload = _SEP.join(parts).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()

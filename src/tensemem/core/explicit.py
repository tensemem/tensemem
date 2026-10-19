"""Parse ``explicit_op`` episode content written by ``Memory._commit``."""

from __future__ import annotations

from tensemem.core.models import ExtractedOp, OpKind
from tensemem.core.normalize import normalize_key


def parse_explicit_ops(content: str) -> tuple[ExtractedOp, ...]:
    """Turn ``SET user.lives_in=Delhi; ADD user.uses_language=Rust`` into ops.

    Unknown prefixes (``DENY``, ``NOTE``, free text) are skipped so correction
    episodes stay in the log without being re-applied as facts. Rejected claims
    are what block the denied value on rebuild.
    """
    ops: list[ExtractedOp] = []
    for chunk in content.split(";"):
        chunk = chunk.strip()
        if not chunk:
            continue
        kind_s, _, rest = chunk.partition(" ")
        try:
            kind = OpKind(kind_s)
        except ValueError:
            continue
        if kind is OpKind.DENY:
            continue
        subject_pred, sep, value = rest.partition("=")
        if not sep:
            continue
        subject, dot, predicate = subject_pred.rpartition(".")
        if not dot or not subject.strip() or not predicate.strip():
            continue
        ops.append(
            ExtractedOp(
                subject=subject.strip(),
                predicate=normalize_key(predicate),
                object=value,
                op=kind,
                evidence=chunk,
            )
        )
    return tuple(ops)

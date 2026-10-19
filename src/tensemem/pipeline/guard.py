"""Strip recalled context and drop ops that aren't quoted from the user (ADR 0007)."""

from __future__ import annotations

from collections.abc import Sequence

from tensemem.core.models import ExtractedOp
from tensemem.security.fence import strip as strip_fences

_MAX_OPS = 128


def user_span(content: str, tag: str | None) -> str:
    """Episode text with this database's fences removed."""
    return strip_fences(content, tag)


def keep_ops(ops: Sequence[ExtractedOp], span: str) -> tuple[ExtractedOp, ...]:
    """Drop ops whose evidence is missing from ``span``.

    Unique evidence strings are searched once. At most ``_MAX_OPS`` ops are kept.
    """
    cached: dict[str, bool] = {}
    kept: list[ExtractedOp] = []
    for op in ops:
        if len(kept) >= _MAX_OPS:
            break
        evidence = op.evidence
        if not evidence:
            continue
        hit = cached.get(evidence)
        if hit is None:
            hit = evidence in span
            cached[evidence] = hit
        if hit:
            kept.append(op)
    return tuple(kept)

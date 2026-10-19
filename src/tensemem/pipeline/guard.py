"""Strip recalled context and drop ops that aren't quoted from the user (ADR 0007)."""

from __future__ import annotations

from collections.abc import Sequence

from tensemem.core.models import ExtractedOp
from tensemem.security.fence import strip as strip_fences


def user_span(content: str, tag: str | None) -> str:
    """Episode text with this database's fences removed."""
    return strip_fences(content, tag)


def keep_ops(ops: Sequence[ExtractedOp], span: str) -> tuple[ExtractedOp, ...]:
    """Drop ops whose evidence is missing from ``span``."""
    return tuple(op for op in ops if op.evidence and op.evidence in span)

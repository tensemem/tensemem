"""Strip recalled context and drop ops that aren't quoted from the user (ADR 0007)."""

from __future__ import annotations

from collections.abc import Sequence

from tensemem.core.models import ExtractedOp
from tensemem.security.fence import strip as strip_fences

_CONFIRMATIONS = frozenset(
    {
        "yes",
        "yeah",
        "yep",
        "yup",
        "correct",
        "right",
        "still true",
        "that's right",
        "that is right",
        "thats right",
    }
)


def user_span(content: str, tag: str | None) -> str:
    """Episode text with this database's fences removed."""
    return strip_fences(content, tag)


def looks_like_confirmation(text: str) -> bool:
    """True when ``text`` is a bare yes/still-true phrase, not a new claim."""
    folded = " ".join(text.casefold().split()).strip(".,!?")
    return folded in _CONFIRMATIONS


def keep_ops(ops: Sequence[ExtractedOp], span: str) -> tuple[ExtractedOp, ...]:
    """Drop ops whose evidence is missing from ``span``. Mark bare confirmations."""
    confirm_span = looks_like_confirmation(span)
    kept: list[ExtractedOp] = []
    for op in ops:
        if not op.evidence or op.evidence not in span:
            continue
        if op.is_confirmation or confirm_span or looks_like_confirmation(op.evidence):
            op = op.model_copy(update={"is_confirmation": True})
        kept.append(op)
    return tuple(kept)

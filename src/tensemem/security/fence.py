"""Wrap recalled memory so extraction can ignore it later (ADR 0007)."""

from __future__ import annotations

import re

_OPEN = "<tensemem-context"
_CLOSE = "</tensemem-context>"
_ESC_OPEN = "<tensemem-context\u2060"
_ESC_CLOSE = "</tensemem-context\u2060>"
_BLOCK = re.compile(r"<tensemem-context\s+tag=\"[^\"]+\">.*?</tensemem-context>", re.DOTALL)


def wrap(text: str, tag: str) -> str:
    body = _encode(_OPEN, _ESC_OPEN, _encode(_CLOSE, _ESC_CLOSE, text.rstrip()))
    return f'{_OPEN} tag="{tag}">\n{body}\n{_CLOSE}\n'


def strip(text: str, tag: str | None = None) -> str:
    """Remove fenced spans. If ``tag`` is set, only that database's fences are removed."""
    if tag is None:
        return _BLOCK.sub("", text)
    pattern = re.compile(
        rf"<tensemem-context\s+tag=\"{re.escape(tag)}\">.*?</tensemem-context>",
        re.DOTALL,
    )
    return pattern.sub("", text)


def _encode(needle: str, replacement: str, text: str) -> str:
    return text.replace(needle, replacement)

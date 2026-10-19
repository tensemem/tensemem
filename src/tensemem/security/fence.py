"""Wrap recalled memory so extraction can ignore it later (ADR 0007)."""

from __future__ import annotations

_OPEN = "<tensemem-context"
_CLOSE = "</tensemem-context>"
_ESC_OPEN = "<tensemem-context\u2060"
_ESC_CLOSE = "</tensemem-context\u2060>"
_TAG_PREFIX = 'tag="'


def wrap(text: str, tag: str) -> str:
    body = _encode(_OPEN, _ESC_OPEN, _encode(_CLOSE, _ESC_CLOSE, text.rstrip()))
    return f'{_OPEN} tag="{tag}">\n{body}\n{_CLOSE}\n'


def strip(text: str, tag: str | None = None) -> str:
    """Remove fenced spans. If ``tag`` is set, only that database's fences are removed.

    Scans forward once so unmatched openings cost linear time in the input length.
    """
    parts: list[str] = []
    cursor = 0
    length = len(text)
    while cursor < length:
        start = text.find(_OPEN, cursor)
        if start < 0:
            parts.append(text[cursor:])
            break
        parts.append(text[cursor:start])
        parsed = _opening(text, start)
        if parsed is None:
            parts.append(text[start : start + 1])
            cursor = start + 1
            continue
        found_tag, body_at = parsed
        close = text.find(_CLOSE, body_at)
        if close < 0:
            parts.append(text[start:])
            break
        end = close + len(_CLOSE)
        if tag is None or found_tag == tag:
            cursor = end
            continue
        parts.append(text[start:end])
        cursor = end
    return "".join(parts)


def _opening(text: str, start: int) -> tuple[str, int] | None:
    """Return ``(tag, index_after_open)`` when ``start`` is a well-formed fence opener."""
    index = start + len(_OPEN)
    length = len(text)
    while index < length and text[index].isspace():
        index += 1
    if not text.startswith(_TAG_PREFIX, index):
        return None
    index += len(_TAG_PREFIX)
    quote = text.find('"', index)
    if quote < 0:
        return None
    found_tag = text[index:quote]
    index = quote + 1
    if index >= length or text[index] != ">":
        return None
    if not found_tag:
        return None
    return found_tag, index + 1


def _encode(needle: str, replacement: str, text: str) -> str:
    return text.replace(needle, replacement)

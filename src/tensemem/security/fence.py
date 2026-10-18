"""Wrap recalled memory so extraction can ignore it later (ADR 0007)."""

from __future__ import annotations

import re

_OPEN = re.compile(r"<tensemem-context\s+tag=\"([^\"]+)\">")
_BLOCK = re.compile(r"<tensemem-context\s+tag=\"[^\"]+\">.*?</tensemem-context>", re.DOTALL)


def wrap(text: str, tag: str) -> str:
    return f'<tensemem-context tag="{tag}">\n{text.rstrip()}\n</tensemem-context>\n'


def strip(text: str, tag: str | None = None) -> str:
    """Remove fenced spans. If ``tag`` is set, only that database's fences are removed."""
    if tag is None:
        return _BLOCK.sub("", text)
    pattern = re.compile(
        rf"<tensemem-context\s+tag=\"{re.escape(tag)}\">.*?</tensemem-context>",
        re.DOTALL,
    )
    return pattern.sub("", text)

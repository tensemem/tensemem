"""Pack ACTIVE facts into a Markdown context block (design §11)."""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from tensemem.core.models import FactView

_CHARS_PER_TOKEN = 4


def count_tokens(text: str) -> int:
    """Conservative token count: words, or ~4 characters, whichever is larger."""
    if not text:
        return 0
    words = len(text.split())
    chars = (len(text) + _CHARS_PER_TOKEN - 1) // _CHARS_PER_TOKEN
    return max(words, chars)


def render_facts(facts: Iterable[FactView], *, as_of: str) -> tuple[str, tuple[str, ...]]:
    """Render grouped ACTIVE facts, newest groups first. Returns (markdown, fact ids)."""
    groups = _groups(facts)
    lines = [f"## What I know about the user (as of {as_of})", ""]
    used: list[str] = []
    for group in groups:
        lines.append(_bullet(group))
        used.extend(fact.id for fact in group)
    body = "\n".join(lines).rstrip() + "\n"
    return body, tuple(used)


def pack_facts(
    facts: Iterable[FactView],
    *,
    as_of: str,
    max_tokens: int,
    query: str = "",
) -> tuple[str, tuple[str, ...]]:
    """Greedy pack by query match then recency, staying under ``max_tokens``."""
    ordered = sorted(
        _groups(facts),
        key=lambda group: (_relevance(group, query), _recency(group)),
        reverse=True,
    )
    chosen: list[tuple[FactView, ...]] = []
    for group in ordered:
        trial, _ = render_facts(_flatten([*chosen, group]), as_of=as_of)
        if count_tokens(trial) > max_tokens:
            continue
        chosen.append(group)
    text, ids = render_facts(_flatten(chosen), as_of=as_of)
    if count_tokens(text) > max_tokens:
        return "", ()
    return text, ids


def attach_hot_buffer(body: str, messages: Sequence[str], *, max_tokens: int) -> str:
    """Append unprocessed user messages, dropping the oldest until the budget fits."""
    kept = list(messages)
    while True:
        hot = render_hot_buffer(kept)
        if not hot:
            return body
        combined = f"{body.rstrip()}\n\n{hot}" if body.strip() else hot
        if count_tokens(combined) <= max_tokens:
            return combined
        if not kept:
            return body
        kept.pop(0)


def render_hot_buffer(messages: Sequence[str]) -> str:
    if not messages:
        return ""
    lines = ["## Said recently (not yet processed)", ""]
    lines.extend(f"- {_field(message)}" for message in messages)
    return "\n".join(lines).rstrip() + "\n"


def _groups(facts: Iterable[FactView]) -> list[tuple[FactView, ...]]:
    buckets: dict[tuple[str, str], list[FactView]] = {}
    for fact in facts:
        buckets.setdefault((fact.subject, fact.predicate), []).append(fact)
    groups = [tuple(items) for items in buckets.values()]
    groups.sort(key=_recency, reverse=True)
    return groups


def _flatten(groups: list[tuple[FactView, ...]]) -> list[FactView]:
    return [fact for group in groups for fact in group]


def _recency(group: tuple[FactView, ...]) -> int:
    return max(fact.recorded_seq for fact in group)


def _relevance(group: tuple[FactView, ...], query: str) -> int:
    if not query.strip():
        return 0
    words = [word for word in query.casefold().split() if word]
    blob = " ".join(f"{fact.subject} {fact.predicate} {fact.object}" for fact in group)
    folded = blob.casefold()
    return sum(1 for word in words if word in folded)


def _bullet(group: tuple[FactView, ...]) -> str:
    first = group[0]
    label = _field(first.predicate.replace("_", " "))
    objects = ", ".join(_field(fact.object) for fact in group)
    if first.subject == "user":
        return f"- {label}: {objects}"
    return f"- {_field(first.subject)} {label}: {objects}"


def _field(text: str) -> str:
    """Flatten and quote a fact field so it cannot introduce Markdown structure."""
    flat = " ".join(text.split()).replace("`", "'")
    return f"`{flat}`"

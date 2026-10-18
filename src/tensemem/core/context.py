"""Pack ACTIVE facts into a Markdown context block (design §11)."""

from __future__ import annotations

from collections.abc import Iterable

from tensemem.core.models import FactView


def count_tokens(text: str) -> int:
    """Heuristic token count: whitespace-separated words."""
    return len(text.split())


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
        if chosen and count_tokens(trial) > max_tokens:
            break
        chosen.append(group)
    text, ids = render_facts(_flatten(chosen), as_of=as_of)
    if count_tokens(text) > max_tokens:
        return "", ()
    return text, ids


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
    label = first.predicate.replace("_", " ")
    objects = ", ".join(fact.object for fact in group)
    if first.subject == "user":
        return f"- {label}: {objects}"
    return f"- {first.subject} {label}: {objects}"

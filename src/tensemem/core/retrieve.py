"""Score and pack context candidates (design §11)."""

from __future__ import annotations

import math
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from tensemem.core.clock import parse_instant
from tensemem.core.models import (
    ContextDebugItem,
    ContextFormat,
    FactStatus,
    FactView,
    SearchHit,
)

HALF_LIFE_DAYS = 90.0
CORE_SHARE = 0.30
HISTORY_PENALTY = 0.5
WEAK_FACT = 0.20

_TEMPORAL = re.compile(
    r"\b(before|previously|formerly|used to|when did|last year|last month|"
    r"last week|in the past|back when)\b",
    re.IGNORECASE,
)
_DETAIL = re.compile(
    r"\b(what did i say|conversation|remember|told you|we talked|last time|"
    r"mentioned|said that)\b",
    re.IGNORECASE,
)
_STOP = frozenset(
    {
        "a",
        "an",
        "the",
        "i",
        "me",
        "my",
        "we",
        "you",
        "is",
        "was",
        "were",
        "am",
        "are",
        "be",
        "did",
        "do",
        "does",
        "where",
        "what",
        "who",
        "how",
        "when",
        "why",
        "in",
        "on",
        "at",
        "to",
        "of",
        "for",
        "and",
        "or",
        "but",
        "not",
        "just",
        "only",
        "it",
        "its",
    }
)
_TOKEN = re.compile(r"[A-Za-z0-9_]+")


@dataclass(frozen=True)
class EpisodeHit:
    public_id: str
    content: str
    occurred_at: str
    rank: float | None = None


@dataclass(frozen=True)
class Scored:
    fact: FactView | None = None
    episode: EpisodeHit | None = None
    score: float = 0.0
    relevance: float = 0.0
    recency: float = 0.0
    reason: str = ""

    @property
    def kind(self) -> str:
        return "episode" if self.episode is not None else "fact"

    @property
    def item_id(self) -> str:
        if self.episode is not None:
            return self.episode.public_id
        assert self.fact is not None
        return self.fact.id


def fts_query(text: str) -> str | None:
    """Quoted OR query; empty after stopwords means no MATCH."""
    tokens = [token.casefold() for token in _TOKEN.findall(text)]
    kept = [token for token in tokens if token not in _STOP]
    if not kept:
        kept = tokens
    if not kept:
        return None
    return " OR ".join(f'"{token}"' for token in kept)


def query_terms(text: str) -> tuple[str, ...]:
    tokens = (token.casefold() for token in _TOKEN.findall(text))
    return tuple(token for token in tokens if token not in _STOP)


def wants_history(query: str, *, include_history: bool = False) -> bool:
    if include_history:
        return True
    if not query.strip():
        return False
    if _TEMPORAL.search(query) is not None:
        return True
    return _has_dates(query)


def wants_episodes(query: str, fact_relevance: float) -> bool:
    if not query.strip():
        return False
    if _DETAIL.search(query.casefold()) is not None:
        return True
    return fact_relevance < WEAK_FACT


def norm_bm25(rank: float) -> float:
    """Map SQLite BM25 (more negative is better) onto 0..1."""
    return 1.0 / (1.0 + math.exp(rank))


def cosine(left: Sequence[float], right: Sequence[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    norm_l = math.sqrt(sum(a * a for a in left))
    norm_r = math.sqrt(sum(b * b for b in right))
    if norm_l == 0.0 or norm_r == 0.0:
        return 0.0
    return max(0.0, min(1.0, dot / (norm_l * norm_r)))


def lexical_overlap(blob: str, terms: Sequence[str]) -> float:
    if not terms:
        return 0.0
    folded = blob.casefold()
    hits = sum(1 for term in terms if term in folded)
    return hits / len(terms)


def recency_score(recorded_at: str, now: str) -> float:
    try:
        days = (parse_instant(now) - parse_instant(recorded_at)).total_seconds() / 86400.0
    except ValueError:
        return 0.5
    return math.exp(-max(days, 0.0) / HALF_LIFE_DAYS)


def score_fact(
    fact: FactView,
    *,
    now: str,
    terms: Sequence[str],
    bm25: float | None = None,
    cosine_sim: float | None = None,
) -> Scored:
    lexical = lexical_overlap(f"{fact.subject} {fact.predicate} {fact.object}", terms)
    relevance = max(norm_bm25(bm25) if bm25 is not None else 0.0, cosine_sim or 0.0, lexical)
    recency = recency_score(fact.recorded_at, now)
    importance = 1.0 if fact.pinned else 0.4
    pinned = 1.0 if fact.pinned else 0.0
    raw = (
        0.45 * relevance
        + 0.20 * recency
        + 0.15 * importance
        + 0.10 * fact.confidence
        + 0.10 * pinned
    )
    if fact.status is not FactStatus.ACTIVE:
        raw *= HISTORY_PENALTY
        reason = "history"
    elif fact.pinned:
        reason = "pinned"
    elif relevance > 0:
        reason = "match"
    else:
        reason = "recency"
    return Scored(fact=fact, score=raw, relevance=relevance, recency=recency, reason=reason)


def score_episode(
    episode: EpisodeHit,
    *,
    now: str,
    terms: Sequence[str],
    cosine_sim: float | None = None,
) -> Scored:
    lexical = lexical_overlap(episode.content, terms)
    bm25 = norm_bm25(episode.rank) if episode.rank is not None else 0.0
    relevance = max(bm25, cosine_sim or 0.0, lexical)
    recency = recency_score(episode.occurred_at, now)
    raw = 0.40 * relevance + 0.25 * recency
    return Scored(
        episode=episode,
        score=raw,
        relevance=relevance,
        recency=recency,
        reason="episode",
    )


def pack_scored(
    items: Sequence[Scored],
    *,
    budget: int,
    count_tokens: Callable[[str], int],
    render: Callable[[Sequence[Scored]], str],
) -> tuple[tuple[Scored, ...], str]:
    """Greedy pack by score/tokens. Pinned facts get a reserved core share."""
    facts = [item for item in items if item.fact is not None]
    episodes = [item for item in items if item.episode is not None]
    pinned = [item for item in facts if item.fact is not None and item.fact.pinned]
    other = [item for item in facts if item.fact is not None and not item.fact.pinned]
    reserved = int(budget * CORE_SHARE) if pinned else 0
    chosen: list[Scored] = []
    body = ""
    if reserved:
        chosen, body = _fill(
            pinned, chosen, budget=reserved, count_tokens=count_tokens, render=render
        )
    packed = {id(item) for item in chosen}
    leftover = [item for item in pinned if id(item) not in packed]
    rest = sorted(other + leftover + episodes, key=lambda item: item.score, reverse=True)
    chosen, body = _fill(rest, chosen, budget=budget, count_tokens=count_tokens, render=render)
    return tuple(chosen), body


def to_search_hits(items: Sequence[Scored], *, limit: int) -> tuple[SearchHit, ...]:
    ranked = sorted(items, key=lambda item: item.score, reverse=True)[:limit]
    hits: list[SearchHit] = []
    for item in ranked:
        if item.fact is not None:
            fact = item.fact
            hits.append(
                SearchHit(
                    kind="fact",
                    id=fact.id,
                    text=f"{fact.subject} {fact.predicate} {fact.object}",
                    score=round(item.score, 6),
                    status=fact.status,
                    predicate=fact.predicate,
                )
            )
            continue
        assert item.episode is not None
        hits.append(
            SearchHit(
                kind="episode",
                id=item.episode.public_id,
                text=item.episode.content,
                score=round(item.score, 6),
            )
        )
    return tuple(hits)


def debug_items(items: Sequence[Scored]) -> tuple[ContextDebugItem, ...]:
    return tuple(
        ContextDebugItem(
            id=item.item_id,
            kind="episode" if item.episode is not None else "fact",
            score=round(item.score, 6),
            relevance=round(item.relevance, 6),
            recency=round(item.recency, 6),
            reason=item.reason,
        )
        for item in items
    )


def render_markdown(
    facts: Sequence[FactView],
    episodes: Sequence[EpisodeHit],
    *,
    as_of: str,
) -> str:
    lines = [f"## What I know about the user (as of {as_of})", ""]
    if facts:
        lines.extend(_fact_bullets(facts))
    else:
        lines.append("- (nothing stored yet)")
    if episodes:
        lines.extend(["", "## Possibly relevant past conversation", ""])
        lines.extend(_episode_bullets(episodes))
    return "\n".join(lines).rstrip() + "\n"


def render_json(
    facts: Sequence[FactView],
    episodes: Sequence[EpisodeHit],
    hot: Sequence[str],
    *,
    as_of: str,
) -> str:
    import json

    payload = {
        "as_of": as_of,
        "facts": [
            {
                "id": fact.id,
                "subject": fact.subject,
                "predicate": fact.predicate,
                "object": fact.object,
                "status": fact.status.value,
            }
            for fact in facts
        ],
        "episodes": [
            {
                "id": episode.public_id,
                "content": episode.content,
                "occurred_at": episode.occurred_at,
            }
            for episode in episodes
        ],
        "hot": list(hot),
    }
    return json.dumps(payload, indent=2) + "\n"


def render_xml(
    facts: Sequence[FactView],
    episodes: Sequence[EpisodeHit],
    hot: Sequence[str],
    *,
    as_of: str,
) -> str:
    parts = [f'<context as_of="{_xml(as_of)}">', "<facts>"]
    for fact in facts:
        parts.append(
            f'  <fact id="{_xml(fact.id)}" subject="{_xml(fact.subject)}" '
            f'predicate="{_xml(fact.predicate)}" status="{_xml(fact.status.value)}">'
            f"{_xml(fact.object)}</fact>"
        )
    parts.append("</facts>")
    parts.append("<episodes>")
    for episode in episodes:
        parts.append(
            f'  <episode id="{_xml(episode.public_id)}" occurred_at="{_xml(episode.occurred_at)}">'
            f"{_xml(episode.content)}</episode>"
        )
    parts.append("</episodes>")
    parts.append("<hot>")
    parts.extend(f"  <message>{_xml(message)}</message>" for message in hot)
    parts.append("</hot>")
    parts.append("</context>")
    return "\n".join(parts) + "\n"


def render_format(
    fmt: ContextFormat,
    facts: Sequence[FactView],
    episodes: Sequence[EpisodeHit],
    hot: Sequence[str],
    *,
    as_of: str,
) -> str:
    if fmt is ContextFormat.JSON:
        return render_json(facts, episodes, hot, as_of=as_of)
    if fmt is ContextFormat.XML:
        return render_xml(facts, episodes, hot, as_of=as_of)
    body = render_markdown(facts, episodes, as_of=as_of)
    if not hot:
        return body
    from tensemem.core.context import render_hot_buffer

    hot_block = render_hot_buffer(hot)
    return f"{body.rstrip()}\n\n{hot_block}" if body.strip() else hot_block


def _fill(
    candidates: Sequence[Scored],
    chosen: list[Scored],
    *,
    budget: int,
    count_tokens: Callable[[str], int],
    render: Callable[[Sequence[Scored]], str],
) -> tuple[list[Scored], str]:
    body = render(chosen)
    ordered = sorted(candidates, key=lambda item: item.score, reverse=True)
    for item in ordered:
        if item in chosen:
            continue
        trial = [*chosen, item]
        text = render(trial)
        if count_tokens(text) > budget:
            continue
        chosen = trial
        body = text
    if count_tokens(body) > budget:
        return [], ""
    return chosen, body


def _fact_bullets(facts: Sequence[FactView]) -> list[str]:
    buckets: dict[tuple[str, str], list[FactView]] = {}
    for fact in facts:
        buckets.setdefault((fact.subject, fact.predicate), []).append(fact)
    lines: list[str] = []
    for (subject, predicate), group in buckets.items():
        active = [fact for fact in group if fact.status is FactStatus.ACTIVE]
        past = [fact for fact in group if fact.status is not FactStatus.ACTIVE]
        shown = active or group
        label = _field(predicate.replace("_", " "))
        objects = ", ".join(_field(fact.object) for fact in shown)
        if subject == "user":
            prefix = f"- {label}: {objects}"
        else:
            prefix = f"- {_field(subject)} {label}: {objects}"
        if past and active:
            previous = ", ".join(_field(fact.object) for fact in past)
            prefix = f"{prefix} (previously {previous})"
        lines.append(prefix)
    return lines


def _episode_bullets(episodes: Sequence[EpisodeHit]) -> list[str]:
    lines: list[str] = []
    for episode in episodes:
        day = episode.occurred_at[:10]
        lines.append(f"- [{day}] {_field(episode.content)}")
    return lines


def _field(text: str) -> str:
    flat = " ".join(text.split()).replace("`", "'")
    return f"`{flat}`"


def _xml(text: str) -> str:
    return (
        text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
    )


def _has_dates(query: str) -> bool:
    try:
        from dateparser.search import search_dates
    except ImportError:
        return False
    try:
        found = search_dates(query, settings={"STRICT_PARSING": True})
    except (TypeError, ValueError):
        return False
    return bool(found)

"""Load, score, and pack retrieval candidates for one scope."""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence

from tensemem.core.context import count_tokens
from tensemem.core.models import (
    ContextDebugItem,
    ContextFormat,
    FactStatus,
    FactView,
    SearchHit,
)
from tensemem.core.retrieve import (
    Scored,
    cosine,
    debug_items,
    pack_scored,
    query_terms,
    render_format,
    score_episode,
    score_fact,
    to_search_hits,
    wants_episodes,
    wants_history,
)
from tensemem.storage.sqlite.embeddings import episode_vectors, fact_vectors
from tensemem.storage.sqlite.search import list_processed_episodes, search_episodes, search_facts
from tensemem.storage.sqlite.snapshot import list_facts

_HISTORY = (FactStatus.ACTIVE, FactStatus.SUPERSEDED, FactStatus.RETRACTED)
_ACTIVE = (FactStatus.ACTIVE,)


def assemble_search(
    conn: sqlite3.Connection,
    scope_id: int,
    query: str,
    *,
    now: str,
    limit: int,
    query_vector: Sequence[float] | None = None,
    embed_model: str | None = None,
) -> tuple[tuple[SearchHit, ...], tuple[ContextDebugItem, ...]]:
    scored = _candidates(
        conn,
        scope_id,
        query,
        now=now,
        include_history=True,
        query_vector=query_vector,
        embed_model=embed_model,
        force_episodes=bool(query.strip()),
    )
    hits = to_search_hits(scored, limit=limit)
    used = {hit.id for hit in hits}
    return hits, debug_items([item for item in scored if item.item_id in used])


def assemble_context(
    conn: sqlite3.Connection,
    scope_id: int,
    query: str,
    *,
    now: str,
    as_of: str,
    max_tokens: int,
    include_history: bool,
    fmt: ContextFormat,
    hot: Sequence[str],
    query_vector: Sequence[float] | None = None,
    embed_model: str | None = None,
) -> tuple[str, tuple[str, ...], tuple[ContextDebugItem, ...]]:
    scored = _candidates(
        conn,
        scope_id,
        query,
        now=now,
        include_history=include_history,
        query_vector=query_vector,
        embed_model=embed_model,
        force_episodes=False,
    )

    def render(items: Sequence[Scored]) -> str:
        facts = tuple(item.fact for item in items if item.fact is not None)
        episodes = tuple(item.episode for item in items if item.episode is not None)
        return render_format(fmt, facts, episodes, (), as_of=as_of)

    chosen, _ = pack_scored(scored, budget=max_tokens, count_tokens=count_tokens, render=render)
    facts = tuple(item.fact for item in chosen if item.fact is not None)
    episodes = tuple(item.episode for item in chosen if item.episode is not None)
    body = render_format(fmt, facts, episodes, hot, as_of=as_of)
    if count_tokens(body) > max_tokens and hot:
        body = render_format(fmt, facts, episodes, (), as_of=as_of)
        kept = list(hot)
        while kept:
            trial = render_format(fmt, facts, episodes, kept, as_of=as_of)
            if count_tokens(trial) <= max_tokens:
                break
            kept.pop(0)
        body = render_format(fmt, facts, episodes, kept, as_of=as_of)
        if count_tokens(body) > max_tokens:
            body = render_format(fmt, facts, episodes, (), as_of=as_of)
    if count_tokens(body) > max_tokens:
        return "", (), ()
    ids = tuple(fact.id for fact in facts)
    return body, ids, debug_items(chosen)


def _candidates(
    conn: sqlite3.Connection,
    scope_id: int,
    query: str,
    *,
    now: str,
    include_history: bool,
    query_vector: Sequence[float] | None,
    embed_model: str | None,
    force_episodes: bool,
) -> list[Scored]:
    terms = query_terms(query)
    statuses = _HISTORY if wants_history(query, include_history=include_history) else _ACTIVE
    facts = list_facts(conn, scope_id, statuses=statuses)
    ranks = {fact.id: rank for fact, rank in search_facts(conn, scope_id, query, statuses=statuses)}
    if wants_history(query, include_history=include_history):
        facts = _with_slot_history(conn, scope_id, facts, ranks)
    vectors = fact_vectors(conn, scope_id, embed_model) if embed_model else {}
    scored: list[Scored] = []
    best_rel = 0.0
    for fact in facts:
        sim = (
            cosine(query_vector, vectors[fact.id])
            if query_vector is not None and fact.id in vectors
            else None
        )
        item = score_fact(fact, now=now, terms=terms, bm25=ranks.get(fact.id), cosine_sim=sim)
        best_rel = max(best_rel, item.relevance)
        scored.append(item)
    if force_episodes or wants_episodes(query, best_rel):
        scored.extend(
            _episode_scores(
                conn,
                scope_id,
                query,
                now=now,
                terms=terms,
                query_vector=query_vector,
                embed_model=embed_model,
            )
        )
    return scored


def _with_slot_history(
    conn: sqlite3.Connection,
    scope_id: int,
    facts: list[FactView],
    ranks: dict[str, float],
) -> list[FactView]:
    slots = {(fact.subject, fact.predicate) for fact in facts if fact.id in ranks or fact.pinned}
    if not slots:
        slots = {(fact.subject, fact.predicate) for fact in facts}
    extra = list_facts(conn, scope_id, statuses=_HISTORY)
    known = {fact.id for fact in facts}
    merged = list(facts)
    for fact in extra:
        if fact.id in known:
            continue
        if (fact.subject, fact.predicate) in slots:
            merged.append(fact)
    return merged


def _episode_scores(
    conn: sqlite3.Connection,
    scope_id: int,
    query: str,
    *,
    now: str,
    terms: Sequence[str],
    query_vector: Sequence[float] | None,
    embed_model: str | None,
) -> list[Scored]:
    hits = search_episodes(conn, scope_id, query) if query.strip() else ()
    if not hits:
        hits = list_processed_episodes(conn, scope_id)
    vectors = episode_vectors(conn, scope_id, embed_model) if embed_model else {}
    scored: list[Scored] = []
    for episode in hits:
        sim = (
            cosine(query_vector, vectors[episode.public_id])
            if query_vector is not None and episode.public_id in vectors
            else None
        )
        scored.append(score_episode(episode, now=now, terms=terms, cosine_sim=sim))
    return scored

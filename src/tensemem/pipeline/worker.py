"""Lease extract jobs, run the pipeline, complete or fail (Day 17).

The LLM call happens outside the write transaction so a slow provider does not
block ``set()`` / ``add()``. Consecutive due jobs in one scope share one extract
call. Fenced recalled context is stripped first; leftover empty messages are
skipped without a provider call. Extracted ops need a verbatim quote from that
unfenced user text (ADR 0007).
"""

from __future__ import annotations

import sqlite3
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass

from tensemem.core.errors import StaleLeaseError
from tensemem.core.models import (
    EpisodeStatus,
    FactSource,
    JobKind,
    JobView,
    Mutation,
    Scope,
)
from tensemem.core.resolver import IncomingOp, resolve
from tensemem.pipeline.extractor import extract
from tensemem.pipeline.guard import keep_ops, user_span
from tensemem.pipeline.normalize import normalize_ops
from tensemem.pipeline.policy import apply_policy
from tensemem.pipeline.prompt import PROMPT_VERSION
from tensemem.pipeline.snapshot import ExtractSnapshot, load_extract_snapshot
from tensemem.providers.embed.base import Embedder
from tensemem.providers.llm.base import LLMProvider, ProviderError
from tensemem.security.scrub import scrub
from tensemem.storage.base import SqliteBackend
from tensemem.storage.sqlite.embeddings import (
    enqueue_episode_embed,
    enqueue_fact_embeds,
    upsert_embedding,
)
from tensemem.storage.sqlite.entities import (
    ensure_subject_entity,
    resolve_entity,
    subject_label,
)
from tensemem.storage.sqlite.episodes import get_episode
from tensemem.storage.sqlite.facts import ApplyContext, apply_mutations
from tensemem.storage.sqlite.jobs import complete, fail, lease_batch, lease_next
from tensemem.storage.sqlite.meta import get_fence_tag
from tensemem.storage.sqlite.registry import get_predicate
from tensemem.storage.sqlite.scopes import get_scope_by_id
from tensemem.storage.sqlite.snapshot import load_snapshot

_ERROR_LIMIT = 500
EXTRACT_BATCH = 8
Emit = Callable[[str, Mapping[str, object]], None]


@dataclass(frozen=True)
class _Item:
    job: JobView
    token: str
    content: str
    episode_id: int
    reference_time: str


@dataclass(frozen=True)
class _Leased:
    items: tuple[_Item, ...]
    scope: Scope
    snapshot: ExtractSnapshot
    combined: str
    reference_time: str


@dataclass(frozen=True)
class _Claim:
    leased: _Leased | None
    progressed: bool


def qualifies(content: str) -> bool:
    """True when the episode has characters worth sending to the extractor."""
    return any(ch.isalnum() for ch in content)


def process_one(
    db: SqliteBackend,
    provider: LLMProvider | None,
    *,
    embedder: Embedder | None = None,
    prefer_scope_id: int | None = None,
    batch_size: int = EXTRACT_BATCH,
    emit: Emit | None = None,
) -> bool:
    """Lease and finish one extract batch or embed job. False if nothing was due."""
    if provider is not None and _process_extract(
        db,
        provider,
        prefer_scope_id=prefer_scope_id,
        batch_size=batch_size,
        enqueue_embed=embedder is not None,
        emit=emit,
    ):
        return True
    if embedder is not None:
        return _process_embed(db, embedder, prefer_scope_id=prefer_scope_id, emit=emit)
    return False


def _process_extract(
    db: SqliteBackend,
    provider: LLMProvider,
    *,
    prefer_scope_id: int | None,
    batch_size: int,
    enqueue_embed: bool,
    emit: Emit | None,
) -> bool:
    claim = db.transaction(
        lambda conn: _claim(
            conn, now=db.now(), prefer_scope_id=prefer_scope_id, batch_size=batch_size
        )
    )
    if not claim.progressed:
        return False
    leased = claim.leased
    if leased is None:
        return True
    try:
        result = extract(
            provider,
            leased.snapshot,
            [{"role": "user", "content": leased.combined}],
        )
    except Exception as exc:
        _fail(db, leased, exc, emit=emit)
        return True
    ops = keep_ops(result.ops, leased.combined)

    def write(conn: sqlite3.Connection) -> None:
        incoming = normalize_ops(conn, leased.scope, ops, now=db.now())
        incoming = apply_policy(conn, incoming, reference_time=leased.reference_time, now=db.now())
        _apply_extracted(
            conn,
            leased.scope,
            incoming,
            episode_id=leased.items[-1].episode_id,
            now=db.now(),
            enqueue_embed=enqueue_embed,
        )
        for item in leased.items:
            complete(
                conn,
                item.job.id,
                now=db.now(),
                lease_until=item.token,
                episode_status=EpisodeStatus.PROCESSED,
            )

    try:
        db.transaction(write)
    except StaleLeaseError:
        return True
    except Exception as exc:
        _fail(db, leased, exc, emit=emit)
        return True
    if emit is not None:
        emit(
            "extraction",
            {
                "scope_id": leased.scope.id,
                "jobs": len(leased.items),
                "ops": len(ops),
            },
        )
    return True


def _claim(
    conn: sqlite3.Connection,
    *,
    now: str,
    prefer_scope_id: int | None,
    batch_size: int,
) -> _Claim:
    jobs = lease_batch(
        conn,
        now=now,
        prefer_scope_id=prefer_scope_id,
        limit=batch_size,
        kind=JobKind.EXTRACT,
    )
    if not jobs:
        return _Claim(leased=None, progressed=False)
    items: list[_Item] = []
    tag = get_fence_tag(conn)
    for job in jobs:
        token = job.lease_until
        if token is None:
            return _Claim(leased=None, progressed=False)
        if job.kind is not JobKind.EXTRACT or job.episode_id is None:
            complete(conn, job.id, now=now, lease_until=token, episode_status=EpisodeStatus.SKIPPED)
            continue
        episode = get_episode(conn, job.episode_id)
        if episode is None:
            fail(conn, job.id, "missing episode", now=now, lease_until=token)
            continue
        content = scrub(user_span(str(episode["content"]), tag))
        if not qualifies(content):
            complete(conn, job.id, now=now, lease_until=token, episode_status=EpisodeStatus.SKIPPED)
            continue
        items.append(
            _Item(
                job=job,
                token=token,
                content=content,
                episode_id=job.episode_id,
                reference_time=str(episode["occurred_at"]),
            )
        )
    if not items:
        return _Claim(leased=None, progressed=True)
    scope = get_scope_by_id(conn, items[0].job.scope_id)
    if scope is None:
        for item in items:
            fail(conn, item.job.id, "missing scope", now=now, lease_until=item.token)
        return _Claim(leased=None, progressed=True)
    reference_time = items[-1].reference_time
    snapshot = load_extract_snapshot(conn, scope, reference_time=reference_time)
    combined = "\n".join(item.content for item in items)
    return _Claim(
        leased=_Leased(
            items=tuple(items),
            scope=scope,
            snapshot=snapshot,
            combined=combined,
            reference_time=reference_time,
        ),
        progressed=True,
    )


def _fail(
    db: SqliteBackend, leased: _Leased, exc: BaseException, *, emit: Emit | None = None
) -> None:
    error = str(exc) or type(exc).__name__
    message = error[:_ERROR_LIMIT]
    print(f"tensemem extract: {type(exc).__name__}: {message}", file=sys.stderr)
    provider_error = isinstance(exc, ProviderError)
    for item in leased.items:

        def write(conn: sqlite3.Connection, held: _Item = item) -> None:
            fail(
                conn,
                held.job.id,
                message,
                now=db.now(),
                lease_until=held.token,
                provider_error=provider_error,
            )

        try:
            db.transaction(write)
        except StaleLeaseError:
            continue
    if emit is not None:
        emit(
            "job_failed",
            {
                "scope_id": leased.scope.id,
                "jobs": len(leased.items),
                "error": message,
            },
        )


def _apply_extracted(
    conn: sqlite3.Connection,
    scope: Scope,
    incoming: tuple[IncomingOp, ...],
    *,
    episode_id: int | None,
    now: str,
    enqueue_embed: bool = False,
) -> None:
    if episode_id is None or not incoming:
        return
    prepared = [_context(conn, scope, item, episode_id=episode_id, now=now) for item in incoming]
    ops = [item[0] for item in prepared]
    contexts = [item[1] for item in prepared]
    snapshot = load_snapshot(conn, scope, episode_seq=episode_id)
    mutations = resolve(ops, snapshot)
    results = apply_mutations(
        conn,
        [(mutation, _context_for(mutation, ops, contexts)) for mutation in mutations],
        now=now,
    )
    if enqueue_embed:
        enqueue_fact_embeds(conn, scope_id=scope.id, now=now, results=results)
        episode = get_episode(conn, episode_id)
        if episode is not None:
            enqueue_episode_embed(
                conn,
                scope_id=scope.id,
                now=now,
                episode_id=episode_id,
                text=str(episode["content"]),
            )


def _process_embed(
    db: SqliteBackend,
    embedder: Embedder,
    *,
    prefer_scope_id: int | None,
    emit: Emit | None = None,
) -> bool:
    def claim(conn: sqlite3.Connection) -> JobView | None:
        return lease_next(conn, now=db.now(), prefer_scope_id=prefer_scope_id, kind=JobKind.EMBED)

    job = db.transaction(claim)
    if job is None:
        return False
    token = job.lease_until
    if token is None or job.owner_kind is None or job.owner_id is None:
        return True
    try:
        vectors = embedder.embed([job.embed_text or ""])
        vector = vectors[0]
    except Exception as exc:
        error = (str(exc) or type(exc).__name__)[:_ERROR_LIMIT]

        def failed(conn: sqlite3.Connection) -> None:
            fail(conn, job.id, error, now=db.now(), lease_until=token)

        try:
            db.transaction(failed)
        except StaleLeaseError:
            return True
        if emit is not None:
            emit("job_failed", {"job_id": job.id, "kind": "embed", "error": error})
        return True

    def write(conn: sqlite3.Connection) -> None:
        upsert_embedding(
            conn,
            owner_kind=job.owner_kind or "fact",
            owner_id=job.owner_id or 0,
            model=embedder.model,
            vector=vector,
        )
        complete(conn, job.id, now=db.now(), lease_until=token)

    try:
        db.transaction(write)
    except StaleLeaseError:
        return True
    return True


def _context(
    conn: sqlite3.Connection,
    scope: Scope,
    item: IncomingOp,
    *,
    episode_id: int,
    now: str,
) -> tuple[IncomingOp, ApplyContext]:
    op = item.op
    predicate = get_predicate(conn, op.predicate)
    if predicate is None:
        msg = f"unknown predicate: {op.predicate}"
        raise LookupError(msg)
    subject_id = ensure_subject_entity(conn, scope.id, op.subject, now=now)
    canonical = subject_label(conn, subject_id)
    if op.subject != canonical:
        op = op.model_copy(update={"subject": canonical})
        item = IncomingOp(op=op, object_norm=item.object_norm, cardinality=item.cardinality)
    object_entity_id = None
    if op.object.strip():
        object_entity_id = resolve_entity(conn, op.object, scope_id=scope.id)
    ctx = ApplyContext(
        scope_id=scope.id,
        episode_id=episode_id,
        recorded_seq=episode_id,
        subject_id=subject_id,
        predicate_id=predicate.id,
        object_norm=item.object_norm,
        cardinality=item.cardinality,
        object_entity_id=object_entity_id,
        source=FactSource.EXTRACTED,
        extractor_version=PROMPT_VERSION,
    )
    return item, ctx


def _context_for(
    mutation: Mutation,
    incoming: list[IncomingOp],
    contexts: list[ApplyContext],
) -> ApplyContext:
    for item, ctx in zip(incoming, contexts, strict=True):
        if item.op is mutation.op:
            return ctx
    for item, ctx in zip(incoming, contexts, strict=True):
        if item.op.predicate == mutation.op.predicate and item.op.subject == mutation.op.subject:
            return ctx
    return contexts[0]

"""Lease extract jobs, run the pipeline, complete or fail (Day 17).

The LLM call happens outside the write transaction so a slow provider does not
block ``set()`` / ``add()``. Fenced recalled context is stripped first; leftover
empty messages are skipped without a provider call. Extracted ops need a
verbatim quote from that unfenced user text (ADR 0007).
"""

from __future__ import annotations

import sqlite3
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
from tensemem.providers.llm.base import LLMProvider, ProviderError
from tensemem.storage.sqlite.database import SqliteDatabase
from tensemem.storage.sqlite.entities import (
    ensure_subject_entity,
    resolve_entity,
    subject_label,
)
from tensemem.storage.sqlite.episodes import get_episode
from tensemem.storage.sqlite.facts import ApplyContext, apply_mutations
from tensemem.storage.sqlite.jobs import complete, fail, lease_next
from tensemem.storage.sqlite.meta import get_fence_tag
from tensemem.storage.sqlite.registry import get_predicate
from tensemem.storage.sqlite.scopes import get_scope_by_id
from tensemem.storage.sqlite.snapshot import load_snapshot

_ERROR_LIMIT = 500


@dataclass(frozen=True)
class _Leased:
    job: JobView
    token: str
    scope: Scope
    content: str
    reference_time: str
    snapshot: ExtractSnapshot


@dataclass(frozen=True)
class _Claim:
    leased: _Leased | None
    progressed: bool


def qualifies(content: str) -> bool:
    """True when the episode has characters worth sending to the extractor."""
    return any(ch.isalnum() for ch in content)


def process_one(db: SqliteDatabase, provider: LLMProvider) -> bool:
    """Lease and finish at most one job. False if nothing was due."""
    claim = db.transaction(lambda conn: _claim(conn, now=db.now()))
    if not claim.progressed:
        return False
    leased = claim.leased
    if leased is None:
        return True
    try:
        result = extract(
            provider,
            leased.snapshot,
            [{"role": "user", "content": leased.content}],
        )
    except Exception as exc:
        _fail(db, leased, exc)
        return True
    ops = keep_ops(result.ops, leased.content)

    def write(conn: sqlite3.Connection) -> None:
        incoming = normalize_ops(conn, leased.scope, ops, now=db.now())
        incoming = apply_policy(conn, incoming, reference_time=leased.reference_time, now=db.now())
        _apply_extracted(
            conn, leased.scope, incoming, episode_id=leased.job.episode_id, now=db.now()
        )
        complete(
            conn,
            leased.job.id,
            now=db.now(),
            lease_until=leased.token,
            episode_status=EpisodeStatus.PROCESSED,
        )

    try:
        db.transaction(write)
    except StaleLeaseError:
        return True
    except Exception as exc:
        _fail(db, leased, exc)
    return True


def _claim(conn: sqlite3.Connection, *, now: str) -> _Claim:
    job = lease_next(conn, now=now)
    if job is None:
        return _Claim(leased=None, progressed=False)
    token = job.lease_until
    if token is None:
        return _Claim(leased=None, progressed=False)
    if job.kind is not JobKind.EXTRACT or job.episode_id is None:
        complete(conn, job.id, now=now, lease_until=token, episode_status=EpisodeStatus.SKIPPED)
        return _Claim(leased=None, progressed=True)
    episode = get_episode(conn, job.episode_id)
    if episode is None:
        fail(conn, job.id, "missing episode", now=now, lease_until=token)
        return _Claim(leased=None, progressed=True)
    content = user_span(str(episode["content"]), get_fence_tag(conn))
    if not qualifies(content):
        complete(conn, job.id, now=now, lease_until=token, episode_status=EpisodeStatus.SKIPPED)
        return _Claim(leased=None, progressed=True)
    scope = get_scope_by_id(conn, job.scope_id)
    if scope is None:
        fail(conn, job.id, "missing scope", now=now, lease_until=token)
        return _Claim(leased=None, progressed=True)
    occurred = str(episode["occurred_at"])
    snapshot = load_extract_snapshot(conn, scope, reference_time=occurred)
    return _Claim(
        leased=_Leased(
            job=job,
            token=token,
            scope=scope,
            content=content,
            reference_time=occurred,
            snapshot=snapshot,
        ),
        progressed=True,
    )


def _fail(db: SqliteDatabase, leased: _Leased, exc: BaseException) -> None:
    error = str(exc) or type(exc).__name__
    message = error[:_ERROR_LIMIT]
    provider_error = isinstance(exc, ProviderError)

    def write(conn: sqlite3.Connection) -> None:
        fail(
            conn,
            leased.job.id,
            message,
            now=db.now(),
            lease_until=leased.token,
            provider_error=provider_error,
        )

    try:
        db.transaction(write)
    except StaleLeaseError:
        return


def _apply_extracted(
    conn: sqlite3.Connection,
    scope: Scope,
    incoming: tuple[IncomingOp, ...],
    *,
    episode_id: int | None,
    now: str,
) -> None:
    if episode_id is None or not incoming:
        return
    prepared = [_context(conn, scope, item, episode_id=episode_id, now=now) for item in incoming]
    ops = [item[0] for item in prepared]
    contexts = [item[1] for item in prepared]
    snapshot = load_snapshot(conn, scope, episode_seq=episode_id)
    mutations = resolve(ops, snapshot)
    apply_mutations(
        conn,
        [(mutation, _context_for(mutation, ops, contexts)) for mutation in mutations],
        now=now,
    )


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

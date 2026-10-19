"""Sync Memory API: typed writes plus optional extract worker (design §12.1)."""

from __future__ import annotations

import sqlite3
import threading
import time
from collections.abc import Sequence
from pathlib import Path

from tensemem.core.clock import Clock, utc_now
from tensemem.core.context import count_tokens, pack_facts
from tensemem.core.errors import UnknownFactError, UnknownPredicateError
from tensemem.core.models import (
    AddResult,
    Cardinality,
    ContextResult,
    EpisodeKind,
    EpisodeStatus,
    ExplainResult,
    ExtractedOp,
    FactSet,
    FactSource,
    JobKind,
    JobView,
    Mutation,
    OnStale,
    OpKind,
    Predicate,
    PredicateSpec,
    Scope,
    ScopeKey,
    StaleMemoryError,
)
from tensemem.core.normalize import normalize_key, normalize_value
from tensemem.core.ontology import Ontology
from tensemem.core.resolver import IncomingOp, resolve
from tensemem.pipeline.normalize import normalize_ops
from tensemem.pipeline.policy import apply_policy
from tensemem.pipeline.snapshot import ExtractSnapshot, load_extract_snapshot
from tensemem.pipeline.worker import process_one
from tensemem.providers.llm.base import LLMProvider
from tensemem.security.fence import strip as strip_fences
from tensemem.security.fence import wrap as wrap_fence
from tensemem.storage.sqlite import SqliteDatabase
from tensemem.storage.sqlite.entities import (
    SELF_NAME,
    ensure_subject_entity,
    resolve_entity,
    subject_label,
)
from tensemem.storage.sqlite.episodes import advance_watermark, insert_episode
from tensemem.storage.sqlite.facts import (
    ApplyContext,
    apply_mutations,
    get_fact,
    mark_rejected,
    restore_displaced,
)
from tensemem.storage.sqlite.jobs import dismiss as dismiss_job
from tensemem.storage.sqlite.jobs import enqueue, has_due_or_leased, list_jobs
from tensemem.storage.sqlite.jobs import retry as retry_job
from tensemem.storage.sqlite.meta import get_fence_tag
from tensemem.storage.sqlite.reads import forget_scope, read_explain, read_history, read_state
from tensemem.storage.sqlite.registry import get_predicate, register_predicate
from tensemem.storage.sqlite.scopes import get_or_create_scope, get_scope, get_scope_by_id
from tensemem.storage.sqlite.snapshot import load_fact_view, load_snapshot, to_fact_view

_WORKER_IDLE = 0.05


class Memory:
    """Sync memory handle. Writes go through resolve() then apply() in one transaction."""

    def __init__(
        self,
        path: str | Path = "tensemem.db",
        *,
        clock: Clock = utc_now,
        llm: LLMProvider | None = None,
    ) -> None:
        self._db = SqliteDatabase(path, clock=clock)
        self._llm = llm
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._worker: threading.Thread | None = None
        if llm is not None:
            self._worker = threading.Thread(
                target=self._run_worker,
                name="tensemem-extract-worker",
                daemon=True,
            )
            self._worker.start()

    def close(self) -> None:
        self._stop.set()
        self._wake.set()
        if self._worker is not None:
            self._worker.join(timeout=2)
            self._worker = None
        self._db.close()

    def __enter__(self) -> Memory:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def register_predicate(
        self,
        name: str,
        *,
        cardinality: Cardinality = Cardinality.ONE,
        aliases: Sequence[str] = (),
        description: str = "",
    ) -> Predicate:
        spec = PredicateSpec(
            name=name,
            cardinality=cardinality,
            aliases=tuple(aliases),
            description=description,
        )
        return self._db.transaction(lambda conn: register_predicate(conn, spec, now=self._db.now()))

    def seed(self, ontology: Ontology) -> None:
        """Optionally load predicates and entities from an app-owned ontology."""
        self._db.seed(ontology)

    def add(
        self,
        user_id: str,
        content: str,
        *,
        agent_id: str = "",
        namespace: str = "default",
        wait: bool = False,
        timeout: float = 10.0,
    ) -> AddResult:
        """Store a user message and an extract job in one transaction.

        With ``wait=True``, drain the worker until this job leaves the queue.
        """
        if wait and self._llm is None:
            msg = "add(wait=True) needs Memory(..., llm=...)"
            raise RuntimeError(msg)
        key = ScopeKey(user_id=user_id, agent_id=agent_id, namespace=namespace)

        def write(conn: sqlite3.Connection) -> AddResult:
            now = self._db.now()
            scope = get_or_create_scope(conn, key, now=now)
            seq, public_id = insert_episode(
                conn,
                scope_id=scope.id,
                content=content,
                now=now,
                kind=EpisodeKind.MESSAGE,
                status=EpisodeStatus.PENDING,
            )
            job_id = enqueue(conn, kind=JobKind.EXTRACT, scope_id=scope.id, now=now, episode_id=seq)
            return AddResult(seq=seq, episode_ids=(public_id,), job_id=str(job_id))

        result = self._db.transaction(write)
        self._wake.set()
        if wait:
            self.flush(timeout=timeout)
        return result

    def flush(self, timeout: float = 10.0) -> None:
        """Run due extract jobs until the queue is idle or ``timeout`` seconds elapse."""
        if not self._has_work():
            return
        if self._llm is None:
            msg = "flush() needs Memory(..., llm=...)"
            raise RuntimeError(msg)
        deadline = time.monotonic() + timeout
        while True:
            if process_one(self._db, self._llm):
                if time.monotonic() >= deadline:
                    break
                continue
            if not self._has_work():
                return
            if time.monotonic() >= deadline:
                break
            remaining = deadline - time.monotonic()
            self._wake.wait(timeout=min(_WORKER_IDLE, max(remaining, 0.0)))
            self._wake.clear()
        if self._has_work():
            msg = f"extract jobs still pending after {timeout}s"
            raise TimeoutError(msg)

    def _has_work(self) -> bool:
        # Same connection as lease/complete so flush cannot race the worker
        # on a shared-cache in-memory database.
        return self._db.write(lambda conn: has_due_or_leased(conn, self._db.now()))

    def _run_worker(self) -> None:
        provider = self._llm
        if provider is None:
            return
        while not self._stop.is_set():
            try:
                worked = process_one(self._db, provider)
            except RuntimeError:
                return
            except Exception:
                worked = False
            if worked:
                continue
            self._wake.wait(timeout=_WORKER_IDLE)
            self._wake.clear()

    def jobs(
        self,
        user_id: str | None = None,
        *,
        agent_id: str = "",
        namespace: str = "default",
    ) -> tuple[JobView, ...]:
        """List outbox rows, optionally for one scope."""
        if user_id is None:
            return self._db.read(lambda conn: list_jobs(conn))
        key = ScopeKey(user_id=user_id, agent_id=agent_id, namespace=namespace)

        def load(conn: sqlite3.Connection) -> tuple[JobView, ...]:
            scope = get_scope(conn, key)
            if scope is None:
                return ()
            return list_jobs(conn, scope_id=scope.id)

        return self._db.read(load)

    def dismiss_job(self, job_id: str) -> JobView:
        """Mark a DEAD job dismissed so later jobs in the scope can run."""
        return self._db.transaction(lambda conn: dismiss_job(conn, job_id))

    def retry_job(self, job_id: str) -> JobView:
        """Requeue a DEAD job."""
        return self._db.transaction(lambda conn: retry_job(conn, job_id, now=self._db.now()))

    def set(
        self,
        user_id: str,
        predicate: str,
        value: str,
        *,
        agent_id: str = "",
        namespace: str = "default",
        subject: str = SELF_NAME,
    ) -> AddResult:
        return self._commit(
            user_id,
            (_op(subject, predicate, value, OpKind.SET),),
            agent_id=agent_id,
            namespace=namespace,
        )

    def add_value(
        self,
        user_id: str,
        predicate: str,
        value: str,
        *,
        agent_id: str = "",
        namespace: str = "default",
        subject: str = SELF_NAME,
    ) -> AddResult:
        return self._commit(
            user_id,
            (_op(subject, predicate, value, OpKind.ADD),),
            agent_id=agent_id,
            namespace=namespace,
        )

    def remove_value(
        self,
        user_id: str,
        predicate: str,
        value: str,
        *,
        agent_id: str = "",
        namespace: str = "default",
        subject: str = SELF_NAME,
    ) -> AddResult:
        return self._commit(
            user_id,
            (_op(subject, predicate, value, OpKind.REMOVE),),
            agent_id=agent_id,
            namespace=namespace,
        )

    def replace_values(
        self,
        user_id: str,
        predicate: str,
        values: str | Sequence[str],
        *,
        agent_id: str = "",
        namespace: str = "default",
        subject: str = SELF_NAME,
    ) -> AddResult:
        items = (values,) if isinstance(values, str) else tuple(values)
        if not items:
            msg = "replace_values needs at least one value"
            raise ValueError(msg)
        first, *rest = items
        ops = [_op(subject, predicate, first, OpKind.REPLACE_SET)]
        ops.extend(_op(subject, predicate, value, OpKind.ADD) for value in rest)
        return self._commit(user_id, tuple(ops), agent_id=agent_id, namespace=namespace)

    def retract(
        self,
        user_id: str,
        predicate: str,
        value: str = "",
        *,
        agent_id: str = "",
        namespace: str = "default",
        subject: str = SELF_NAME,
    ) -> AddResult:
        return self._commit(
            user_id,
            (_op(subject, predicate, value, OpKind.RETRACT),),
            agent_id=agent_id,
            namespace=namespace,
        )

    def state(
        self,
        user_id: str,
        *,
        agent_id: str = "",
        namespace: str = "default",
    ) -> FactSet:
        key = ScopeKey(user_id=user_id, agent_id=agent_id, namespace=namespace)
        return self._db.read(lambda conn: read_state(conn, get_scope(conn, key)))

    def extract_snapshot(
        self,
        user_id: str,
        *,
        reference_time: str | None = None,
        agent_id: str = "",
        namespace: str = "default",
    ) -> ExtractSnapshot:
        """Registry plus ACTIVE facts for the extractor prompt."""
        key = ScopeKey(user_id=user_id, agent_id=agent_id, namespace=namespace)
        as_of = reference_time or self._db.now()[:10]
        return self._db.read(
            lambda conn: load_extract_snapshot(conn, get_scope(conn, key), reference_time=as_of)
        )

    def normalize(
        self,
        user_id: str,
        ops: Sequence[ExtractedOp],
        *,
        reference_time: str | None = None,
        agent_id: str = "",
        namespace: str = "default",
    ) -> tuple[IncomingOp, ...]:
        """Map extractor ops onto registry names, fill valid time, apply modality policy."""
        key = ScopeKey(user_id=user_id, agent_id=agent_id, namespace=namespace)

        def write(conn: sqlite3.Connection) -> tuple[IncomingOp, ...]:
            now = self._db.now()
            scope = get_or_create_scope(conn, key, now=now)
            incoming = normalize_ops(conn, scope, ops, now=now)
            return apply_policy(conn, incoming, reference_time=reference_time or now, now=now)

        return self._db.transaction(write)

    def context(
        self,
        user_id: str,
        query: str = "",
        *,
        max_tokens: int = 300,
        min_seq: int | None = None,
        on_stale: OnStale | str = OnStale.FLAG,
        fence: bool = True,
        agent_id: str = "",
        namespace: str = "default",
    ) -> ContextResult:
        """Render current facts for a prompt. Does not wait for the extract worker."""
        key = ScopeKey(user_id=user_id, agent_id=agent_id, namespace=namespace)
        as_of = self._db.now()[:10]
        policy = OnStale(on_stale)

        def load(conn: sqlite3.Connection) -> ContextResult:
            facts = read_state(conn, get_scope(conn, key))
            if (
                min_seq is not None
                and facts.freshness.as_of_seq < min_seq
                and policy is OnStale.RAISE
            ):
                raise StaleMemoryError(min_seq=min_seq, freshness=facts.freshness)
            tag = get_fence_tag(conn) or ""
            reserve = count_tokens(wrap_fence("", tag)) if fence else 0
            if fence and reserve > max_tokens:
                return ContextResult(
                    text="",
                    facts_used=(),
                    token_count=0,
                    freshness=facts.freshness,
                )
            body_budget = max(max_tokens - reserve, 0)
            body, ids = pack_facts(facts.facts, as_of=as_of, max_tokens=body_budget, query=query)
            text = wrap_fence(body, tag) if fence else body
            return ContextResult(
                text=text,
                facts_used=ids,
                token_count=count_tokens(text),
                freshness=facts.freshness,
            )

        return self._db.read(load)

    def fence(self, text: str) -> str:
        """Wrap custom-rendered memory in this database's contamination fence."""
        tag = self._db.read(get_fence_tag) or ""
        return wrap_fence(text, tag)

    def unfence(self, text: str) -> str:
        """Strip this database's fenced spans from ``text``."""
        tag = self._db.read(get_fence_tag) or ""
        return strip_fences(text, tag)

    def history(
        self,
        user_id: str,
        predicate: str | None = None,
        *,
        agent_id: str = "",
        namespace: str = "default",
    ) -> FactSet:
        key = ScopeKey(user_id=user_id, agent_id=agent_id, namespace=namespace)
        name = None if predicate is None else normalize_key(predicate)
        return self._db.read(lambda conn: read_history(conn, get_scope(conn, key), predicate=name))

    def explain(self, fact_id: str) -> ExplainResult:
        def load(conn: sqlite3.Connection) -> ExplainResult:
            row = load_fact_view(conn, fact_id)
            if row is None:
                raise UnknownFactError(f"unknown fact: {fact_id}")
            return read_explain(conn, row)

        return self._db.read(load)

    def correct(
        self,
        fact_id: str,
        replacement: str | None = None,
        note: str | None = None,
    ) -> AddResult:
        def write(conn: sqlite3.Connection) -> AddResult:
            fact = get_fact(conn, fact_id)
            if fact is None:
                raise UnknownFactError(f"unknown fact: {fact_id}")
            scope = get_scope_by_id(conn, int(fact["scope_id"]))
            if scope is None:
                raise UnknownFactError(f"unknown fact: {fact_id}")
            now = self._db.now()
            content = note or f"DENY {fact_id}"
            seq, public_id = insert_episode(conn, scope_id=scope.id, content=content, now=now)
            mark_rejected(conn, fact, episode_id=seq, recorded_seq=seq, now=now)
            restore_displaced(conn, int(fact["id"]), episode_id=seq, now=now)
            if replacement is not None:
                row = load_fact_view(conn, fact_id)
                if row is None:
                    raise UnknownFactError(f"unknown fact: {fact_id}")
                view = to_fact_view(row)
                op = _op(view.subject, view.predicate, replacement, OpKind.SET)
                _apply_ops(conn, scope, (op,), episode_id=seq, now=now)
            advance_watermark(conn, scope.id)
            return AddResult(seq=seq, episode_ids=(public_id,))

        return self._db.transaction(write)

    def forget(
        self,
        user_id: str,
        *,
        agent_id: str = "",
        namespace: str = "default",
    ) -> None:
        key = ScopeKey(user_id=user_id, agent_id=agent_id, namespace=namespace)

        def wipe(conn: sqlite3.Connection) -> None:
            scope = get_scope(conn, key)
            if scope is not None:
                forget_scope(conn, scope.id)

        self._db.transaction(wipe)

    def _commit(
        self,
        user_id: str,
        ops: tuple[ExtractedOp, ...],
        *,
        agent_id: str,
        namespace: str,
    ) -> AddResult:
        key = ScopeKey(user_id=user_id, agent_id=agent_id, namespace=namespace)
        content = "; ".join(f"{op.op.value} {op.subject}.{op.predicate}={op.object}" for op in ops)

        def write(conn: sqlite3.Connection) -> AddResult:
            now = self._db.now()
            scope = get_or_create_scope(conn, key, now=now)
            seq, public_id = insert_episode(conn, scope_id=scope.id, content=content, now=now)
            _apply_ops(conn, scope, ops, episode_id=seq, now=now)
            advance_watermark(conn, scope.id)
            return AddResult(seq=seq, episode_ids=(public_id,))

        return self._db.transaction(write)


def _apply_ops(
    conn: sqlite3.Connection,
    scope: Scope,
    ops: tuple[ExtractedOp, ...],
    *,
    episode_id: int,
    now: str,
) -> None:
    prepared = [_prepare(conn, scope, op, episode_id=episode_id, now=now) for op in ops]
    incoming = [item[0] for item in prepared]
    contexts = [item[1] for item in prepared]
    snapshot = load_snapshot(conn, scope, episode_seq=episode_id)
    mutations = resolve(incoming, snapshot)
    apply_mutations(
        conn,
        [(mutation, _context_for(mutation, incoming, contexts)) for mutation in mutations],
        now=now,
    )


def _op(subject: str, predicate: str, value: str, kind: OpKind) -> ExtractedOp:
    return ExtractedOp(
        subject=_canonical_subject(subject),
        predicate=normalize_key(predicate),
        object=value,
        op=kind,
        evidence=f"{kind.value} {value}".strip(),
    )


def _canonical_subject(subject: str) -> str:
    if normalize_value(subject) in {SELF_NAME, "self"}:
        return SELF_NAME
    return subject.strip()


def _prepare(
    conn: sqlite3.Connection,
    scope: Scope,
    op: ExtractedOp,
    *,
    episode_id: int,
    now: str,
) -> tuple[IncomingOp, ApplyContext]:
    predicate = get_predicate(conn, op.predicate)
    if predicate is None:
        raise UnknownPredicateError(f"unknown predicate: {op.predicate}")
    subject_id = ensure_subject_entity(conn, scope.id, op.subject, now=now)
    canonical = subject_label(conn, subject_id)
    if op.subject != canonical:
        op = op.model_copy(update={"subject": canonical})
    object_norm = normalize_value(op.object) if op.object.strip() else ""
    object_entity_id = None
    if op.object.strip():
        object_entity_id = resolve_entity(conn, op.object, scope_id=scope.id)
    incoming = IncomingOp(op=op, object_norm=object_norm, cardinality=predicate.cardinality)
    ctx = ApplyContext(
        scope_id=scope.id,
        episode_id=episode_id,
        recorded_seq=episode_id,
        subject_id=subject_id,
        predicate_id=predicate.id,
        object_norm=object_norm,
        cardinality=predicate.cardinality,
        object_entity_id=object_entity_id,
        source=FactSource.EXPLICIT,
    )
    return incoming, ctx


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

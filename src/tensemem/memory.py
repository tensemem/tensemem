"""Sync and async Memory API: typed writes plus optional extract worker (design §12.1)."""

from __future__ import annotations

import asyncio
import sqlite3
import threading
import time
from collections.abc import Mapping, Sequence
from contextlib import suppress
from pathlib import Path

from tensemem.core.clock import Clock, utc_now
from tensemem.core.context import attach_hot_buffer, count_tokens, pack_facts
from tensemem.core.errors import UnknownFactError, UnknownPredicateError
from tensemem.core.explicit import parse_explicit_ops
from tensemem.core.models import (
    AddResult,
    Cardinality,
    ContextDebugItem,
    ContextFormat,
    ContextResult,
    EpisodeKind,
    EpisodeStatus,
    ExplainResult,
    ExtractedOp,
    FactSet,
    FactSource,
    Freshness,
    JobKind,
    JobStatus,
    JobView,
    MemoryStats,
    Mutation,
    OnStale,
    OpKind,
    Predicate,
    PredicateSpec,
    Scope,
    ScopeKey,
    SearchResult,
    StaleMemoryError,
)
from tensemem.core.normalize import normalize_key, normalize_value
from tensemem.core.ontology import Ontology
from tensemem.core.resolver import IncomingOp, resolve
from tensemem.hooks import Hook
from tensemem.hooks import emit as emit_hooks
from tensemem.pipeline.normalize import normalize_ops
from tensemem.pipeline.policy import apply_policy
from tensemem.pipeline.snapshot import ExtractSnapshot, load_extract_snapshot
from tensemem.pipeline.worker import EXTRACT_BATCH, process_one
from tensemem.providers.embed.base import Embedder
from tensemem.providers.llm.base import LLMProvider
from tensemem.security.fence import strip as strip_fences
from tensemem.security.fence import wrap as wrap_fence
from tensemem.storage.sqlite import SqliteDatabase
from tensemem.storage.sqlite.embeddings import enqueue_fact_embeds
from tensemem.storage.sqlite.entities import (
    SELF_NAME,
    ensure_subject_entity,
    resolve_entity,
    subject_label,
)
from tensemem.storage.sqlite.episodes import (
    advance_watermark,
    insert_episode,
    list_episodes,
    list_hot_buffer,
)
from tensemem.storage.sqlite.export import dump_scope, parse_jsonl
from tensemem.storage.sqlite.facts import (
    ApplyContext,
    apply_mutations,
    get_fact,
    mark_rejected,
    restore_displaced,
)
from tensemem.storage.sqlite.jobs import dismiss as dismiss_job
from tensemem.storage.sqlite.jobs import enqueue, get_job, has_due_or_leased, list_jobs
from tensemem.storage.sqlite.jobs import retry as retry_job
from tensemem.storage.sqlite.meta import get_fence_tag
from tensemem.storage.sqlite.reads import (
    forget_scope,
    read_explain,
    read_history,
    read_state,
    wipe_projection,
)
from tensemem.storage.sqlite.registry import get_predicate, register_predicate
from tensemem.storage.sqlite.retrieve import assemble_context, assemble_search
from tensemem.storage.sqlite.scopes import get_or_create_scope, get_scope, get_scope_by_id
from tensemem.storage.sqlite.snapshot import (
    freshness_for,
    load_fact_view,
    load_snapshot,
    to_fact_view,
)
from tensemem.storage.sqlite.stats import load_stats

_WORKER_IDLE = 0.05


class Memory:
    """Sync memory handle. Writes go through resolve() then apply() in one transaction."""

    def __init__(
        self,
        path: str | Path = "tensemem.db",
        *,
        clock: Clock = utc_now,
        llm: LLMProvider | None = None,
        embedder: Embedder | None = None,
        batch_size: int = EXTRACT_BATCH,
        start_worker: bool = True,
        hooks: Sequence[Hook] | None = None,
    ) -> None:
        self._db = SqliteDatabase(path, clock=clock)
        self._llm = llm
        self._embedder = embedder
        self._batch_size = batch_size
        self._hooks: list[Hook] = list(hooks or ())
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._worker: threading.Thread | None = None
        if (llm is not None or embedder is not None) and start_worker:
            self._worker = threading.Thread(
                target=self._run_worker,
                name="tensemem-extract-worker",
                daemon=True,
            )
            self._worker.start()

    def halt(self) -> None:
        """Stop the extract loop. Does not close the database."""
        self._stop.set()
        self._wake.set()

    def has_provider(self) -> bool:
        return self._llm is not None

    def has_worker(self) -> bool:
        return self._llm is not None or self._embedder is not None

    def embed_query(self, query: str) -> tuple[list[float] | None, str | None]:
        if self._embedder is None or not query.strip():
            return None, None
        try:
            return self._embedder.embed([query])[0], self._embedder.model
        except Exception:
            return None, None

    def stopped(self) -> bool:
        return self._stop.is_set()

    def close(self) -> None:
        self.halt()
        if self._worker is not None:
            self._worker.join()
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
        pinned: bool = False,
    ) -> Predicate:
        spec = PredicateSpec(
            name=name,
            cardinality=cardinality,
            aliases=tuple(aliases),
            description=description,
            pinned=pinned,
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
        self._emit(
            "add",
            {"user_id": user_id, "seq": result.seq, "job_id": result.job_id or ""},
        )
        self._wake.set()
        if wait:
            self.flush(timeout=timeout, job_id=result.job_id)
        return result

    def flush(self, timeout: float = 10.0, *, job_id: str | None = None) -> None:
        """Run due extract jobs until the queue is idle or ``timeout`` seconds elapse.

        Pass ``job_id`` to return as soon as that job leaves QUEUED/LEASED, even
        if another scope still has work.
        """
        if not self.waiting_for(job_id):
            return
        if self._llm is None and self._embedder is None:
            msg = "flush() needs Memory(..., llm=...) or embedder="
            raise RuntimeError(msg)
        prefer = self.scope_for_job(job_id) if job_id is not None else None
        deadline = time.monotonic() + timeout
        while True:
            if job_id is not None and not self.waiting_for(job_id):
                return
            if self.process_extract(prefer_scope_id=prefer):
                if time.monotonic() >= deadline:
                    break
                continue
            if not self.waiting_for(job_id):
                return
            if time.monotonic() >= deadline:
                break
            remaining = deadline - time.monotonic()
            self._wake.wait(timeout=min(_WORKER_IDLE, max(remaining, 0.0)))
            self._wake.clear()
        if self.waiting_for(job_id):
            msg = f"extract jobs still pending after {timeout}s"
            raise TimeoutError(msg)

    def waiting_for(self, job_id: str | None) -> bool:
        if job_id is None:
            return self._has_work()
        return self._job_pending(job_id)

    def _has_work(self) -> bool:
        # Same connection as lease/complete so flush cannot race the worker
        # on a shared-cache in-memory database.
        return self._db.write(lambda conn: has_due_or_leased(conn, self._db.now()))

    def _job_pending(self, job_id: str) -> bool:
        def pending(conn: sqlite3.Connection) -> bool:
            job = get_job(conn, job_id)
            return job is not None and job.status in {JobStatus.QUEUED, JobStatus.LEASED}

        return self._db.write(pending)

    def scope_for_job(self, job_id: str) -> int | None:
        job = self._db.write(lambda conn: get_job(conn, job_id))
        return None if job is None else job.scope_id

    def process_extract(self, *, prefer_scope_id: int | None = None) -> bool:
        if self._llm is None and self._embedder is None:
            return False
        return process_one(
            self._db,
            self._llm,
            embedder=self._embedder,
            prefer_scope_id=prefer_scope_id,
            batch_size=self._batch_size,
            emit=self._emit,
        )

    def _run_worker(self) -> None:
        if self._llm is None and self._embedder is None:
            return
        while not self._stop.is_set():
            try:
                worked = self.process_extract()
            except Exception as extra:
                if self._stop.is_set() or (
                    isinstance(extra, RuntimeError) and "is closed" in str(extra)
                ):
                    return
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

    def dismiss_dead_jobs(
        self,
        user_id: str | None = None,
        *,
        agent_id: str = "",
        namespace: str = "default",
    ) -> tuple[JobView, ...]:
        """Dismiss every DEAD job, optionally for one scope."""
        listed = self.jobs(user_id, agent_id=agent_id, namespace=namespace)
        dead = [job for job in listed if job.status is JobStatus.DEAD]
        return tuple(self.dismiss_job(job.id) for job in dead)

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
        wait: float = 0.0,
        on_stale: OnStale | str = OnStale.FLAG,
        fence: bool = True,
        include_history: bool = False,
        fmt: ContextFormat | str = ContextFormat.MARKDOWN,
        agent_id: str = "",
        namespace: str = "default",
    ) -> ContextResult:
        """Render current facts for a prompt.

        With ``wait>0``, drain this scope's extract jobs until ``min_seq`` is
        applied (or until the scope is current when ``min_seq`` is omitted).
        A non-empty ``query`` uses FTS (and optional embeddings) so the right
        slot wins over whatever was written last.
        """
        key = ScopeKey(user_id=user_id, agent_id=agent_id, namespace=namespace)
        policy = OnStale(on_stale)
        layout = ContextFormat(fmt)
        query_vector, embed_model = self.embed_query(query)

        def pack() -> tuple[ContextResult, int | None]:
            return self.pack_context(
                key,
                query=query,
                max_tokens=max_tokens,
                fence=fence,
                include_history=include_history,
                fmt=layout,
                query_vector=query_vector,
                embed_model=embed_model,
            )

        packed, scope_id = pack()
        if caught_up(packed.freshness, min_seq):
            return packed
        if wait <= 0:
            return stale_or_raise(packed, min_seq=min_seq, policy=policy)
        if self._llm is None:
            msg = "context(wait=...) needs Memory(..., llm=...)"
            raise RuntimeError(msg)
        self._wake.set()
        deadline = time.monotonic() + wait
        while time.monotonic() < deadline:
            if self.process_extract(prefer_scope_id=scope_id):
                packed, scope_id = pack()
                if caught_up(packed.freshness, min_seq):
                    return packed
                continue
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            self._wake.wait(timeout=min(_WORKER_IDLE, remaining))
            self._wake.clear()
            packed, scope_id = pack()
            if caught_up(packed.freshness, min_seq):
                return packed
        packed, _ = pack()
        if caught_up(packed.freshness, min_seq):
            return packed
        return stale_or_raise(packed, min_seq=min_seq, policy=policy)

    def pack_context(
        self,
        key: ScopeKey,
        *,
        query: str,
        max_tokens: int,
        fence: bool,
        include_history: bool = False,
        fmt: ContextFormat = ContextFormat.MARKDOWN,
        query_vector: Sequence[float] | None = None,
        embed_model: str | None = None,
    ) -> tuple[ContextResult, int | None]:
        as_of = self._db.now()[:10]
        now = self._db.now()

        def load(conn: sqlite3.Connection) -> tuple[ContextResult, int | None]:
            scope = get_scope(conn, key)
            facts = read_state(conn, scope)
            tag = get_fence_tag(conn) or ""
            reserve = count_tokens(wrap_fence("", tag)) if fence else 0
            if fence and reserve > max_tokens:
                return (
                    ContextResult(
                        text="",
                        facts_used=(),
                        token_count=0,
                        freshness=facts.freshness,
                    ),
                    None if scope is None else scope.id,
                )
            body_budget = max(max_tokens - reserve, 0)
            pending = () if scope is None else list_hot_buffer(conn, scope.id)
            if scope is None or (
                not query.strip() and not include_history and fmt is ContextFormat.MARKDOWN
            ):
                body, ids = pack_facts(
                    facts.facts, as_of=as_of, max_tokens=body_budget, query=query
                )
                body = attach_hot_buffer(body, pending, max_tokens=body_budget)
                debug = tuple(
                    ContextDebugItem(id=fact_id, kind="fact", reason="recency") for fact_id in ids
                )
            else:
                body, ids, debug = assemble_context(
                    conn,
                    scope.id,
                    query,
                    now=now,
                    as_of=as_of,
                    max_tokens=body_budget,
                    include_history=include_history,
                    fmt=fmt,
                    hot=pending,
                    query_vector=query_vector,
                    embed_model=embed_model,
                )
            text = wrap_fence(body, tag) if fence else body
            return (
                ContextResult(
                    text=text,
                    facts_used=ids,
                    token_count=count_tokens(text),
                    freshness=facts.freshness,
                    debug=debug,
                ),
                None if scope is None else scope.id,
            )

        return self._db.read(load)

    def search(
        self,
        user_id: str,
        query: str,
        *,
        limit: int = 10,
        agent_id: str = "",
        namespace: str = "default",
    ) -> SearchResult:
        """Ranked facts and episodes for ``query`` (FTS, optional embeddings)."""
        key = ScopeKey(user_id=user_id, agent_id=agent_id, namespace=namespace)
        now = self._db.now()
        query_vector, embed_model = self.embed_query(query)

        def load(conn: sqlite3.Connection) -> SearchResult:
            scope = get_scope(conn, key)
            if scope is None:
                return SearchResult(hits=(), freshness=freshness_for(conn, None))
            hits, debug = assemble_search(
                conn,
                scope.id,
                query,
                now=now,
                limit=limit,
                query_vector=query_vector,
                embed_model=embed_model,
            )
            return SearchResult(hits=hits, freshness=freshness_for(conn, scope), debug=debug)

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
            row = load_fact_view(conn, fact_id)
            if row is None:
                raise UnknownFactError(f"unknown fact: {fact_id}")
            scope = get_scope_by_id(conn, int(fact["scope_id"]))
            if scope is None:
                raise UnknownFactError(f"unknown fact: {fact_id}")
            view = to_fact_view(row)
            now = self._db.now()
            pieces = [f"DENY {view.subject}.{view.predicate}={view.object}"]
            if replacement is not None:
                pieces.append(f"SET {view.subject}.{view.predicate}={replacement}")
            if note:
                pieces.append(f"NOTE {note}")
            seq, public_id = insert_episode(
                conn, scope_id=scope.id, content="; ".join(pieces), now=now
            )
            mark_rejected(conn, fact, episode_id=seq, recorded_seq=seq, now=now)
            restore_displaced(conn, int(fact["id"]), episode_id=seq, now=now)
            if replacement is not None:
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
        self._emit("forget", {"user_id": user_id})

    def backup(self, dest: str | Path) -> None:
        """Copy the open database to ``dest`` (SQLite online backup)."""
        self._db.backup_to(dest)
        self._emit("backup", {"dest": str(dest)})

    def stats(
        self,
        user_id: str | None = None,
        *,
        agent_id: str = "",
        namespace: str = "default",
    ) -> MemoryStats:
        """Queue depth, fact counts, and a character/4 token estimate."""
        if user_id is None:
            return self._db.read(lambda conn: load_stats(conn, None))
        key = ScopeKey(user_id=user_id, agent_id=agent_id, namespace=namespace)
        return self._db.read(lambda conn: load_stats(conn, get_scope(conn, key)))

    def export_jsonl(
        self,
        user_id: str,
        *,
        agent_id: str = "",
        namespace: str = "default",
    ) -> str:
        """Predicates plus episodes for ``user_id``, one JSON object per line."""
        key = ScopeKey(user_id=user_id, agent_id=agent_id, namespace=namespace)

        def dump(conn: sqlite3.Connection) -> str:
            scope = get_scope(conn, key)
            if scope is None:
                return ""
            return dump_scope(conn, scope)

        return self._db.read(dump)

    def import_jsonl(
        self,
        user_id: str,
        source: str | Path,
        *,
        agent_id: str = "",
        namespace: str = "default",
    ) -> int:
        """Replay a JSONL dump via ``register_predicate``, ``set``/``add``, and ``add()``.

        Public ids are new. Corrections survive a bit-copy ``backup()``, not this
        portable replay, unless the dump still contains the denied value only as
        a later episode the resolver would drop.
        """
        text = Path(source).read_text(encoding="utf-8") if _looks_like_path(source) else str(source)
        applied = 0
        for record in parse_jsonl(text):
            kind = str(record.get("type", ""))
            if kind == "predicate":
                name = str(record.get("name", "")).strip()
                if not name:
                    continue
                self.register_predicate(
                    name,
                    cardinality=Cardinality(str(record.get("cardinality", "ONE"))),
                    description=str(record.get("description", "")),
                    pinned=bool(record.get("pinned", False)),
                )
                applied += 1
            elif kind == "episode":
                content = str(record.get("content", ""))
                if str(record.get("kind")) == EpisodeKind.EXPLICIT_OP.value:
                    ops = parse_explicit_ops(content)
                    if ops:
                        self._commit(user_id, ops, agent_id=agent_id, namespace=namespace)
                        applied += 1
                elif content.strip():
                    self.add(user_id, content, agent_id=agent_id, namespace=namespace)
                    applied += 1
        self._emit("import", {"user_id": user_id, "records": applied})
        return applied

    def rebuild(
        self,
        user_id: str,
        *,
        agent_id: str = "",
        namespace: str = "default",
        wait: bool = False,
        timeout: float = 30.0,
    ) -> int:
        """Wipe the fact projection and replay episodes. Returns the new version.

        Explicit ops are applied in the same transaction. Message episodes are
        re-queued for extract. Rejected claims stay, so corrections survive.
        """
        key = ScopeKey(user_id=user_id, agent_id=agent_id, namespace=namespace)

        def replay(conn: sqlite3.Connection) -> int:
            scope = get_scope(conn, key)
            if scope is None:
                return 0
            now = self._db.now()
            episodes = list_episodes(conn, scope.id)
            wipe_projection(conn, scope.id)
            scope = get_scope(conn, key)
            if scope is None:
                return 0
            for episode in episodes:
                kind = EpisodeKind(str(episode["kind"]))
                seq = int(episode["id"])
                if kind is EpisodeKind.EXPLICIT_OP:
                    ops = parse_explicit_ops(str(episode["content"]))
                    if ops:
                        _apply_ops(
                            conn,
                            scope,
                            ops,
                            episode_id=seq,
                            now=now,
                            enqueue_embed=self._embedder is not None,
                        )
                elif kind is EpisodeKind.MESSAGE:
                    enqueue(
                        conn,
                        kind=JobKind.EXTRACT,
                        scope_id=scope.id,
                        now=now,
                        episode_id=seq,
                    )
            advance_watermark(conn, scope.id)
            refreshed = get_scope(conn, key)
            return 1 if refreshed is None else refreshed.projection_version

        version = self._db.transaction(replay)
        self._emit("rebuild", {"user_id": user_id, "projection_version": version})
        if wait and version > 0 and self._llm is not None:
            self.flush(timeout=timeout)
        elif self._embedder is not None:
            self._wake.set()
        return version

    def on(self, hook: Hook) -> None:
        """Register an extra ``hook(event, payload)`` callback."""
        self._hooks.append(hook)

    def _emit(self, name: str, payload: Mapping[str, object]) -> None:
        emit_hooks(self._hooks, name, payload)

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
            _apply_ops(
                conn,
                scope,
                ops,
                episode_id=seq,
                now=now,
                enqueue_embed=self._embedder is not None,
            )
            advance_watermark(conn, scope.id)
            return AddResult(seq=seq, episode_ids=(public_id,))

        result = self._db.transaction(write)
        self._emit("commit", {"user_id": user_id, "seq": result.seq, "ops": len(ops)})
        if self._embedder is not None:
            self._wake.set()
        return result


def _looks_like_path(source: str | Path) -> bool:
    if isinstance(source, Path):
        return True
    if "\n" in source or source.lstrip().startswith("{"):
        return False
    try:
        return Path(source).is_file()
    except OSError:
        return False


def caught_up(freshness: Freshness, min_seq: int | None) -> bool:
    if min_seq is not None:
        return freshness.as_of_seq >= min_seq
    return freshness.is_current


def stale_or_raise(packed: ContextResult, *, min_seq: int | None, policy: OnStale) -> ContextResult:
    if policy is OnStale.RAISE:
        needed = packed.freshness.latest_seq if min_seq is None else min_seq
        raise StaleMemoryError(min_seq=needed, freshness=packed.freshness)
    return packed


def _apply_ops(
    conn: sqlite3.Connection,
    scope: Scope,
    ops: tuple[ExtractedOp, ...],
    *,
    episode_id: int,
    now: str,
    enqueue_embed: bool = False,
) -> None:
    prepared = [_prepare(conn, scope, op, episode_id=episode_id, now=now) for op in ops]
    incoming = [item[0] for item in prepared]
    contexts = [item[1] for item in prepared]
    snapshot = load_snapshot(conn, scope, episode_seq=episode_id)
    mutations = resolve(incoming, snapshot)
    results = apply_mutations(
        conn,
        [(mutation, _context_for(mutation, incoming, contexts)) for mutation in mutations],
        now=now,
    )
    if enqueue_embed:
        enqueue_fact_embeds(conn, scope_id=scope.id, now=now, results=results)


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


class AsyncMemory:
    """Async handle. Extract work runs on an ``asyncio`` task via the writer thread."""

    def __init__(
        self,
        path: str | Path = "tensemem.db",
        *,
        clock: Clock = utc_now,
        llm: LLMProvider | None = None,
        embedder: Embedder | None = None,
        batch_size: int = EXTRACT_BATCH,
        hooks: Sequence[Hook] | None = None,
    ) -> None:
        self._sync = Memory(
            path,
            clock=clock,
            llm=llm,
            embedder=embedder,
            batch_size=batch_size,
            start_worker=False,
            hooks=hooks,
        )
        self._task: asyncio.Task[None] | None = None
        self._wake = asyncio.Event()

    async def __aenter__(self) -> AsyncMemory:
        self._ensure_worker()
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()

    async def close(self) -> None:
        self._sync.halt()
        self._wake.set()
        if self._task is not None:
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        await asyncio.to_thread(self._sync.close)

    def _ensure_worker(self) -> None:
        if self._task is not None or not self._sync.has_worker():
            return
        self._task = asyncio.get_running_loop().create_task(self._run_worker())

    async def _run_worker(self) -> None:
        while not self._sync.stopped():
            try:
                worked = await asyncio.to_thread(self._sync.process_extract)
            except Exception as extra:
                if self._sync.stopped() or (
                    isinstance(extra, RuntimeError) and "is closed" in str(extra)
                ):
                    return
                worked = False
            if worked:
                continue
            with suppress(TimeoutError):
                await asyncio.wait_for(self._wake.wait(), timeout=_WORKER_IDLE)
            self._wake.clear()

    async def register_predicate(
        self,
        name: str,
        *,
        cardinality: Cardinality = Cardinality.ONE,
        aliases: Sequence[str] = (),
        description: str = "",
    ) -> Predicate:
        return await asyncio.to_thread(
            self._sync.register_predicate,
            name,
            cardinality=cardinality,
            aliases=aliases,
            description=description,
        )

    async def seed(self, ontology: Ontology) -> None:
        await asyncio.to_thread(self._sync.seed, ontology)

    async def add(
        self,
        user_id: str,
        content: str,
        *,
        agent_id: str = "",
        namespace: str = "default",
        wait: bool = False,
        timeout: float = 10.0,
    ) -> AddResult:
        if wait and not self._sync.has_provider():
            msg = "add(wait=True) needs AsyncMemory(..., llm=...)"
            raise RuntimeError(msg)
        self._ensure_worker()
        result = await asyncio.to_thread(
            self._sync.add,
            user_id,
            content,
            agent_id=agent_id,
            namespace=namespace,
            wait=False,
        )
        self._wake.set()
        if wait:
            await self.flush(timeout=timeout, job_id=result.job_id)
        return result

    async def flush(self, timeout: float = 10.0, *, job_id: str | None = None) -> None:
        if not await asyncio.to_thread(self._sync.waiting_for, job_id):
            return
        if not self._sync.has_worker():
            msg = "flush() needs AsyncMemory(..., llm=...) or embedder="
            raise RuntimeError(msg)
        self._ensure_worker()
        prefer = (
            None if job_id is None else await asyncio.to_thread(self._sync.scope_for_job, job_id)
        )
        deadline = time.monotonic() + timeout
        while True:
            if job_id is not None and not await asyncio.to_thread(self._sync.waiting_for, job_id):
                return
            if await asyncio.to_thread(self._sync.process_extract, prefer_scope_id=prefer):
                if time.monotonic() >= deadline:
                    break
                continue
            if not await asyncio.to_thread(self._sync.waiting_for, job_id):
                return
            if time.monotonic() >= deadline:
                break
            remaining = deadline - time.monotonic()
            await asyncio.sleep(min(_WORKER_IDLE, max(remaining, 0.0)))
        if await asyncio.to_thread(self._sync.waiting_for, job_id):
            msg = f"extract jobs still pending after {timeout}s"
            raise TimeoutError(msg)

    async def context(
        self,
        user_id: str,
        query: str = "",
        *,
        max_tokens: int = 300,
        min_seq: int | None = None,
        wait: float = 0.0,
        on_stale: OnStale | str = OnStale.FLAG,
        fence: bool = True,
        include_history: bool = False,
        fmt: ContextFormat | str = ContextFormat.MARKDOWN,
        agent_id: str = "",
        namespace: str = "default",
    ) -> ContextResult:
        key = ScopeKey(user_id=user_id, agent_id=agent_id, namespace=namespace)
        policy = OnStale(on_stale)
        layout = ContextFormat(fmt)
        query_vector, embed_model = await asyncio.to_thread(self._sync.embed_query, query)
        packed, scope_id = await asyncio.to_thread(
            self._sync.pack_context,
            key,
            query=query,
            max_tokens=max_tokens,
            fence=fence,
            include_history=include_history,
            fmt=layout,
            query_vector=query_vector,
            embed_model=embed_model,
        )
        if caught_up(packed.freshness, min_seq):
            return packed
        if wait <= 0:
            return stale_or_raise(packed, min_seq=min_seq, policy=policy)
        if not self._sync.has_provider():
            msg = "context(wait=...) needs AsyncMemory(..., llm=...)"
            raise RuntimeError(msg)
        self._ensure_worker()
        self._wake.set()
        deadline = time.monotonic() + wait
        while time.monotonic() < deadline:
            if await asyncio.to_thread(self._sync.process_extract, prefer_scope_id=scope_id):
                packed, scope_id = await asyncio.to_thread(
                    self._sync.pack_context,
                    key,
                    query=query,
                    max_tokens=max_tokens,
                    fence=fence,
                    include_history=include_history,
                    fmt=layout,
                    query_vector=query_vector,
                    embed_model=embed_model,
                )
                if caught_up(packed.freshness, min_seq):
                    return packed
                continue
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            await asyncio.sleep(min(_WORKER_IDLE, remaining))
            packed, scope_id = await asyncio.to_thread(
                self._sync.pack_context,
                key,
                query=query,
                max_tokens=max_tokens,
                fence=fence,
                include_history=include_history,
                fmt=layout,
                query_vector=query_vector,
                embed_model=embed_model,
            )
            if caught_up(packed.freshness, min_seq):
                return packed
        packed, _ = await asyncio.to_thread(
            self._sync.pack_context,
            key,
            query=query,
            max_tokens=max_tokens,
            fence=fence,
            include_history=include_history,
            fmt=layout,
            query_vector=query_vector,
            embed_model=embed_model,
        )
        if caught_up(packed.freshness, min_seq):
            return packed
        return stale_or_raise(packed, min_seq=min_seq, policy=policy)

    async def search(
        self,
        user_id: str,
        query: str,
        *,
        limit: int = 10,
        agent_id: str = "",
        namespace: str = "default",
    ) -> SearchResult:
        return await asyncio.to_thread(
            self._sync.search,
            user_id,
            query,
            limit=limit,
            agent_id=agent_id,
            namespace=namespace,
        )

    async def set(
        self,
        user_id: str,
        predicate: str,
        value: str,
        *,
        agent_id: str = "",
        namespace: str = "default",
        subject: str = SELF_NAME,
    ) -> AddResult:
        return await asyncio.to_thread(
            self._sync.set,
            user_id,
            predicate,
            value,
            agent_id=agent_id,
            namespace=namespace,
            subject=subject,
        )

    async def state(
        self,
        user_id: str,
        *,
        agent_id: str = "",
        namespace: str = "default",
    ) -> FactSet:
        return await asyncio.to_thread(
            self._sync.state, user_id, agent_id=agent_id, namespace=namespace
        )

    async def history(
        self,
        user_id: str,
        predicate: str | None = None,
        *,
        agent_id: str = "",
        namespace: str = "default",
    ) -> FactSet:
        return await asyncio.to_thread(
            self._sync.history,
            user_id,
            predicate,
            agent_id=agent_id,
            namespace=namespace,
        )

    async def jobs(
        self,
        user_id: str | None = None,
        *,
        agent_id: str = "",
        namespace: str = "default",
    ) -> tuple[JobView, ...]:
        return await asyncio.to_thread(
            self._sync.jobs, user_id, agent_id=agent_id, namespace=namespace
        )

    async def explain(self, fact_id: str) -> ExplainResult:
        return await asyncio.to_thread(self._sync.explain, fact_id)

    async def fence(self, text: str) -> str:
        return await asyncio.to_thread(self._sync.fence, text)

    async def unfence(self, text: str) -> str:
        return await asyncio.to_thread(self._sync.unfence, text)

    async def backup(self, dest: str | Path) -> None:
        await asyncio.to_thread(self._sync.backup, dest)

    async def stats(
        self,
        user_id: str | None = None,
        *,
        agent_id: str = "",
        namespace: str = "default",
    ) -> MemoryStats:
        return await asyncio.to_thread(
            self._sync.stats, user_id, agent_id=agent_id, namespace=namespace
        )

    async def export_jsonl(
        self,
        user_id: str,
        *,
        agent_id: str = "",
        namespace: str = "default",
    ) -> str:
        return await asyncio.to_thread(
            self._sync.export_jsonl, user_id, agent_id=agent_id, namespace=namespace
        )

    async def import_jsonl(
        self,
        user_id: str,
        source: str | Path,
        *,
        agent_id: str = "",
        namespace: str = "default",
    ) -> int:
        return await asyncio.to_thread(
            self._sync.import_jsonl,
            user_id,
            source,
            agent_id=agent_id,
            namespace=namespace,
        )

    async def rebuild(
        self,
        user_id: str,
        *,
        agent_id: str = "",
        namespace: str = "default",
        wait: bool = False,
        timeout: float = 30.0,
    ) -> int:
        return await asyncio.to_thread(
            self._sync.rebuild,
            user_id,
            agent_id=agent_id,
            namespace=namespace,
            wait=wait,
            timeout=timeout,
        )

    async def dismiss_dead_jobs(
        self,
        user_id: str | None = None,
        *,
        agent_id: str = "",
        namespace: str = "default",
    ) -> tuple[JobView, ...]:
        return await asyncio.to_thread(
            self._sync.dismiss_dead_jobs, user_id, agent_id=agent_id, namespace=namespace
        )

    def on(self, hook: Hook) -> None:
        self._sync.on(hook)

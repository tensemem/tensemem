"""Deterministic Memory API: typed writes, no LLM (design §12.1)."""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence
from pathlib import Path

from tensemem.core.clock import Clock, utc_now
from tensemem.core.context import count_tokens, pack_facts
from tensemem.core.errors import UnknownFactError, UnknownPredicateError
from tensemem.core.models import (
    AddResult,
    Cardinality,
    ContextResult,
    ExplainResult,
    ExtractedOp,
    FactSet,
    FactSource,
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
from tensemem.core.resolver import IncomingOp, resolve
from tensemem.security.fence import strip as strip_fences
from tensemem.security.fence import wrap as wrap_fence
from tensemem.storage.sqlite import SqliteDatabase
from tensemem.storage.sqlite.entities import (
    SELF_NAME,
    ensure_subject_entity,
    resolve_entity,
    subject_label,
)
from tensemem.storage.sqlite.episodes import insert_episode, set_applied_seq
from tensemem.storage.sqlite.facts import (
    ApplyContext,
    apply_mutations,
    get_fact,
    mark_rejected,
    restore_displaced,
)
from tensemem.storage.sqlite.meta import get_fence_tag
from tensemem.storage.sqlite.reads import forget_scope, read_explain, read_history, read_state
from tensemem.storage.sqlite.registry import get_predicate, register_predicate
from tensemem.storage.sqlite.scopes import get_or_create_scope, get_scope, get_scope_by_id
from tensemem.storage.sqlite.snapshot import load_fact_view, load_snapshot, to_fact_view


class Memory:
    """Sync memory handle. Writes go through resolve() then apply() in one transaction."""

    def __init__(
        self,
        path: str | Path = "tensemem.db",
        *,
        clock: Clock = utc_now,
    ) -> None:
        self._db = SqliteDatabase(path, clock=clock)

    def close(self) -> None:
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
        """Render current facts for a prompt. Waiting for a worker comes later."""
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
            set_applied_seq(conn, scope.id, seq)
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
            set_applied_seq(conn, scope.id, seq)
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

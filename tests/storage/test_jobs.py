from __future__ import annotations

import sqlite3
from datetime import timedelta

import pytest

from tensemem.core.backoff import MAX_ATTEMPTS
from tensemem.core.clock import format_instant, parse_instant
from tensemem.core.errors import StaleLeaseError, UnknownJobError
from tensemem.core.models import (
    EpisodeKind,
    EpisodeStatus,
    JobKind,
    JobStatus,
    JobView,
    Scope,
    ScopeKey,
)
from tensemem.storage.sqlite import SqliteDatabase
from tensemem.storage.sqlite.episodes import insert_episode
from tensemem.storage.sqlite.jobs import (
    CIRCUIT_THRESHOLD,
    complete,
    dismiss,
    enqueue,
    fail,
    get_job,
    lease_next,
    retry,
)
from tensemem.storage.sqlite.scopes import get_or_create_scope


def test_enqueue_is_idempotent_per_episode(db: SqliteDatabase) -> None:
    first = _ingest(db, "u1", "I live in Delhi")
    again = db.transaction(
        lambda conn: enqueue(
            conn,
            kind=JobKind.EXTRACT,
            scope_id=first["scope_id"],
            now=db.now(),
            episode_id=first["seq"],
        )
    )
    assert again == first["job_id"]


def test_one_lease_per_scope_and_in_order(db: SqliteDatabase) -> None:
    first = _ingest(db, "u1", "one")
    second = _ingest(db, "u1", "two")
    other = _ingest(db, "u2", "other")

    a = db.transaction(lambda conn: lease_next(conn, now=db.now()))
    b = db.transaction(lambda conn: lease_next(conn, now=db.now()))
    assert a is not None
    assert b is not None
    assert {a.id, b.id} == {str(first["job_id"]), str(other["job_id"])}
    assert db.transaction(lambda conn: lease_next(conn, now=db.now())) is None

    _complete(db, str(first["job_id"]))
    nxt = db.transaction(lambda conn: lease_next(conn, now=db.now()))
    assert nxt is not None
    assert nxt.id == str(second["job_id"])


def test_expired_lease_can_be_reclaimed(db: SqliteDatabase) -> None:
    job = _ingest(db, "u1", "hello")
    leased = db.transaction(lambda conn: lease_next(conn, now=db.now(), lease_seconds=1))
    assert leased is not None
    later = "2026-10-18T09:00:02.000000Z"
    again = db.transaction(lambda conn: lease_next(conn, now=later))
    assert again is not None
    assert again.id == str(job["job_id"])
    assert again.status is JobStatus.LEASED
    assert again.attempts == 1


def test_fail_backs_off_then_goes_dead(db: SqliteDatabase) -> None:
    job = _ingest(db, "u1", "hello")
    after_one = _fail_once(db, str(job["job_id"]), db.now(), jitter=1.0)
    assert after_one.status is JobStatus.QUEUED
    assert after_one.attempts == 1
    assert after_one.next_run_at > db.now()
    assert db.transaction(lambda conn: lease_next(conn, now=db.now())) is None

    current = after_one
    for step in range(2, MAX_ATTEMPTS + 1):
        current = _fail_once(db, str(job["job_id"]), current.next_run_at, jitter=1.0)
        assert current.attempts == step
    assert current.status is JobStatus.DEAD
    assert _scope(db, "u1").applied_seq == 0


def test_complete_advances_watermark(db: SqliteDatabase) -> None:
    job = _ingest(db, "u1", "hello")
    db.transaction(lambda conn: lease_next(conn, now=db.now()))
    _complete(db, str(job["job_id"]))
    assert _scope(db, "u1").applied_seq == job["seq"]


def test_dismiss_unblocks_the_scope(db: SqliteDatabase) -> None:
    first = _ingest(db, "u1", "one")
    second = _ingest(db, "u1", "two")
    dead = _fail_until_dead(db, str(first["job_id"]))
    assert dead.status is JobStatus.DEAD
    assert db.transaction(lambda conn: lease_next(conn, now=dead.next_run_at)) is None

    db.transaction(lambda conn: dismiss(conn, str(first["job_id"])))
    nxt = db.transaction(lambda conn: lease_next(conn, now=dead.next_run_at))
    assert nxt is not None
    assert nxt.id == str(second["job_id"])
    assert _scope(db, "u1").applied_seq == first["seq"]


def test_retry_requeues_without_lowering_watermark(db: SqliteDatabase) -> None:
    job = _ingest(db, "u1", "hello")
    dead = _fail_until_dead(db, str(job["job_id"]))
    retried = db.transaction(lambda conn: retry(conn, str(job["job_id"]), now=dead.next_run_at))
    assert retried.status is JobStatus.QUEUED
    assert retried.attempts == 0
    assert _scope(db, "u1").applied_seq == 0


def test_circuit_opens_after_repeated_provider_failures(db: SqliteDatabase) -> None:
    job = _ingest(db, "u1", "hello")
    now = db.now()
    for _ in range(CIRCUIT_THRESHOLD):
        failed = _fail_once(db, str(job["job_id"]), now, jitter=0.0, provider_error=True)
        now = failed.next_run_at
    assert db.transaction(lambda conn: lease_next(conn, now=now)) is None


def test_unknown_job_and_dismiss_guard(db: SqliteDatabase) -> None:
    job = _ingest(db, "u1", "hello")
    with pytest.raises(UnknownJobError, match="unknown job"):
        db.transaction(lambda conn: complete(conn, "999", now=db.now(), lease_until="x"))
    with pytest.raises(ValueError, match="not DEAD"):
        db.transaction(lambda conn: dismiss(conn, str(job["job_id"])))


def test_stale_complete_is_rejected(db: SqliteDatabase) -> None:
    job = _ingest(db, "u1", "hello")
    first = db.transaction(lambda conn: lease_next(conn, now=db.now(), lease_seconds=1))
    assert first is not None
    token = first.lease_until
    assert token is not None
    later = "2026-10-18T09:00:02.000000Z"
    again = db.transaction(lambda conn: lease_next(conn, now=later))
    assert again is not None

    def stale(conn: sqlite3.Connection) -> JobView:
        return complete(conn, str(job["job_id"]), now=later, lease_until=token)

    with pytest.raises(StaleLeaseError, match="stale lease"):
        db.transaction(stale)
    held = db.transaction(lambda conn: get_job(conn, str(job["job_id"])))
    assert held is not None
    assert held.status is JobStatus.LEASED
    assert held.lease_until == again.lease_until


def test_fail_uses_random_jitter_by_default(
    db: SqliteDatabase, monkeypatch: pytest.MonkeyPatch
) -> None:
    job = _ingest(db, "u1", "hello")
    monkeypatch.setattr("tensemem.storage.sqlite.jobs.random.random", lambda: 0.5)
    failed = _fail_once(db, str(job["job_id"]), db.now())
    assert failed.status is JobStatus.QUEUED
    assert failed.next_run_at == "2026-10-18T09:00:00.500000Z"


def test_expired_leases_count_toward_dead(db: SqliteDatabase) -> None:
    job = _ingest(db, "u1", "hello")
    now = db.now()
    for _ in range(MAX_ATTEMPTS):
        leased = _lease(db, now, lease_seconds=1)
        assert leased is not None
        now = _later(now, 2)
    assert _lease(db, now) is None
    dead = db.transaction(lambda conn: get_job(conn, str(job["job_id"])))
    assert dead is not None
    assert dead.status is JobStatus.DEAD
    assert dead.attempts == MAX_ATTEMPTS
    assert _scope(db, "u1").applied_seq == 0


def _complete(db: SqliteDatabase, job_id: str, *, now: str | None = None) -> JobView:
    stamp = now or db.now()

    def write(conn: sqlite3.Connection) -> JobView:
        job = get_job(conn, job_id)
        assert job is not None
        assert job.lease_until is not None
        return complete(conn, job_id, now=stamp, lease_until=job.lease_until)

    return db.transaction(write)


def _lease(db: SqliteDatabase, now: str, *, lease_seconds: float = 60) -> JobView | None:
    return db.transaction(lambda conn: lease_next(conn, now=now, lease_seconds=lease_seconds))


def _later(now: str, seconds: float) -> str:
    return format_instant(parse_instant(now) + timedelta(seconds=seconds))


def _ingest(db: SqliteDatabase, user_id: str, content: str) -> dict[str, int]:
    def write(conn: sqlite3.Connection) -> dict[str, int]:
        now = db.now()
        scope = get_or_create_scope(conn, ScopeKey(user_id=user_id), now=now)
        seq, _public = insert_episode(
            conn,
            scope_id=scope.id,
            content=content,
            now=now,
            kind=EpisodeKind.MESSAGE,
            status=EpisodeStatus.PENDING,
        )
        job_id = enqueue(conn, kind=JobKind.EXTRACT, scope_id=scope.id, now=now, episode_id=seq)
        return {"scope_id": scope.id, "seq": seq, "job_id": job_id}

    return db.transaction(write)


def _fail_once(
    db: SqliteDatabase,
    job_id: str,
    now: str,
    *,
    jitter: float | None = None,
    provider_error: bool = False,
) -> JobView:
    def write(conn: sqlite3.Connection) -> JobView:
        leased = lease_next(conn, now=now)
        assert leased is not None
        assert leased.lease_until is not None
        return fail(
            conn,
            job_id,
            "boom",
            now=now,
            lease_until=leased.lease_until,
            jitter=jitter,
            provider_error=provider_error,
        )

    return db.transaction(write)


def _fail_until_dead(db: SqliteDatabase, job_id: str) -> JobView:
    now = db.now()
    current = _fail_once(db, job_id, now, jitter=0.0)
    while current.status is not JobStatus.DEAD:
        current = _fail_once(db, job_id, current.next_run_at, jitter=0.0)
    return current


def _scope(db: SqliteDatabase, user_id: str) -> Scope:
    return db.transaction(
        lambda conn: get_or_create_scope(conn, ScopeKey(user_id=user_id), now=db.now())
    )

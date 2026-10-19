"""Durable SQLite outbox: enqueue, lease, complete, fail, dismiss (Day 16).

Functions never commit; callers own the transaction. Jobs in one scope run
in episode order, one at a time, so the freshness watermark stays a prefix.
"""

from __future__ import annotations

import json
import random
import sqlite3
from datetime import timedelta

from tensemem.core.backoff import LEASE_SECONDS, MAX_ATTEMPTS, backoff_seconds
from tensemem.core.clock import format_instant, parse_instant
from tensemem.core.errors import StaleLeaseError, UnknownJobError
from tensemem.core.ids import new_ulid
from tensemem.core.models import EpisodeStatus, JobKind, JobStatus, JobView
from tensemem.storage.sqlite.episodes import advance_watermark, set_episode_status

CIRCUIT_THRESHOLD = 5
CIRCUIT_COOLDOWN_SECONDS = 30.0
_CIRCUIT_FAILURES = "circuit.failures"
_CIRCUIT_OPEN_UNTIL = "circuit.open_until"


def enqueue(
    conn: sqlite3.Connection,
    *,
    kind: JobKind,
    scope_id: int,
    now: str,
    episode_id: int | None = None,
    payload: dict[str, object] | None = None,
) -> int:
    """Insert a QUEUED job. Reuse the row when the idempotency key already exists."""
    body = dict(payload or {})
    if episode_id is not None:
        body.setdefault("episode_id", episode_id)
    key = _idempotency_key(kind, scope_id, episode_id)
    existing = conn.execute("SELECT id FROM jobs WHERE idempotency_key = ?", (key,)).fetchone()
    if existing is not None:
        return int(existing["id"])
    row = conn.execute(
        """
        INSERT INTO jobs(kind, scope_id, payload, status, next_run_at, idempotency_key, created_at)
        VALUES (?, ?, ?, 'QUEUED', ?, ?, ?)
        RETURNING id
        """,
        (kind.value, scope_id, json.dumps(body, separators=(",", ":")), now, key, now),
    ).fetchone()
    return int(row["id"])


def lease_next(
    conn: sqlite3.Connection,
    *,
    now: str,
    lease_seconds: float = LEASE_SECONDS,
) -> JobView | None:
    """Claim the next ready job, or None if the circuit is open or nothing is due."""
    if _circuit_open(conn, now):
        return None
    _expire_leases(conn, now)
    row = conn.execute(
        """
        SELECT j.id FROM jobs j
        WHERE j.status = 'QUEUED'
          AND j.next_run_at <= ?
          AND NOT EXISTS (
            SELECT 1 FROM jobs held
            WHERE held.scope_id = j.scope_id AND held.status = 'LEASED'
          )
          AND NOT EXISTS (
            SELECT 1 FROM jobs earlier
            WHERE earlier.scope_id = j.scope_id
              AND earlier.id < j.id
              AND earlier.status IN ('QUEUED', 'LEASED', 'DEAD')
          )
        ORDER BY j.id
        LIMIT 1
        """,
        (now,),
    ).fetchone()
    if row is None:
        return None
    until = _add_seconds(now, lease_seconds)
    conn.execute(
        "UPDATE jobs SET status = 'LEASED', lease_until = ? WHERE id = ?",
        (until, int(row["id"])),
    )
    job = get_job(conn, str(row["id"]))
    if job is None:
        return None
    return job


def complete(
    conn: sqlite3.Connection,
    job_id: str,
    *,
    now: str,
    lease_until: str,
    episode_status: EpisodeStatus = EpisodeStatus.PROCESSED,
) -> JobView:
    """Mark the job done, finish its episode, and advance the watermark."""
    job = _require_job(conn, job_id)
    _update_held_lease(
        conn,
        job_id=job.id,
        lease_until=lease_until,
        now=now,
        sql="UPDATE jobs SET status = 'DONE', lease_until = NULL, last_error = NULL",
    )
    if job.episode_id is not None:
        set_episode_status(conn, job.episode_id, episode_status)
        advance_watermark(conn, job.scope_id)
    record_provider_success(conn)
    return _require_job(conn, job_id)


def fail(
    conn: sqlite3.Connection,
    job_id: str,
    error: str,
    *,
    now: str,
    lease_until: str,
    provider_error: bool = False,
    jitter: float | None = None,
) -> JobView:
    """Backoff and requeue, or mark DEAD after ``MAX_ATTEMPTS``."""
    job = _require_job(conn, job_id)
    attempts = job.attempts + 1
    frac = random.random() if jitter is None else jitter
    if attempts >= MAX_ATTEMPTS:
        _update_held_lease(
            conn,
            job_id=job.id,
            lease_until=lease_until,
            now=now,
            sql="UPDATE jobs SET status = 'DEAD', attempts = ?, last_error = ?, lease_until = NULL",
            params=(attempts, error),
        )
        if provider_error:
            record_provider_failure(conn, now=now)
        if job.episode_id is not None:
            set_episode_status(conn, job.episode_id, EpisodeStatus.FAILED)
            advance_watermark(conn, job.scope_id)
        return _require_job(conn, job_id)
    nxt = _add_seconds(now, backoff_seconds(attempts, jitter=frac))
    _update_held_lease(
        conn,
        job_id=job.id,
        lease_until=lease_until,
        now=now,
        sql=(
            "UPDATE jobs SET status = 'QUEUED', attempts = ?, last_error = ?, "
            "next_run_at = ?, lease_until = NULL"
        ),
        params=(attempts, error, nxt),
    )
    if provider_error:
        record_provider_failure(conn, now=now)
    return _require_job(conn, job_id)


def dismiss(conn: sqlite3.Connection, job_id: str) -> JobView:
    """Finish a DEAD job so later work in the scope can run."""
    job = _require_job(conn, job_id)
    if job.status is not JobStatus.DEAD:
        msg = f"job {job_id} is {job.status.value}, not DEAD"
        raise ValueError(msg)
    conn.execute(
        """
        UPDATE jobs
        SET status = 'DONE', last_error = 'dismissed', lease_until = NULL
        WHERE id = ?
        """,
        (int(job.id),),
    )
    if job.episode_id is not None:
        set_episode_status(conn, job.episode_id, EpisodeStatus.DISMISSED)
        advance_watermark(conn, job.scope_id)
    return _require_job(conn, job_id)


def retry(conn: sqlite3.Connection, job_id: str, *, now: str) -> JobView:
    """Put a DEAD job back on the queue. The watermark never included it."""
    job = _require_job(conn, job_id)
    if job.status is not JobStatus.DEAD:
        msg = f"job {job_id} is {job.status.value}, not DEAD"
        raise ValueError(msg)
    conn.execute(
        """
        UPDATE jobs
        SET status = 'QUEUED', attempts = 0, next_run_at = ?, last_error = NULL, lease_until = NULL
        WHERE id = ?
        """,
        (now, int(job.id)),
    )
    if job.episode_id is not None:
        set_episode_status(conn, job.episode_id, EpisodeStatus.PENDING)
    return _require_job(conn, job_id)


def get_job(conn: sqlite3.Connection, job_id: str) -> JobView | None:
    row = conn.execute("SELECT * FROM jobs WHERE id = ?", (int(job_id),)).fetchone()
    return None if row is None else _to_job(row)


def list_jobs(conn: sqlite3.Connection, *, scope_id: int | None = None) -> tuple[JobView, ...]:
    if scope_id is None:
        rows = conn.execute("SELECT * FROM jobs ORDER BY id").fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM jobs WHERE scope_id = ? ORDER BY id", (scope_id,)
        ).fetchall()
    return tuple(_to_job(row) for row in rows)


def has_due_or_leased(conn: sqlite3.Connection, now: str) -> bool:
    """True when the worker can still make progress at ``now``."""
    row = conn.execute(
        """
        SELECT 1 FROM jobs
        WHERE status = 'LEASED'
           OR (status = 'QUEUED' AND next_run_at <= ?)
        LIMIT 1
        """,
        (now,),
    ).fetchone()
    return row is not None


def record_provider_success(conn: sqlite3.Connection) -> None:
    _meta_set(conn, _CIRCUIT_FAILURES, "0")
    conn.execute("DELETE FROM meta WHERE key = ?", (_CIRCUIT_OPEN_UNTIL,))


def record_provider_failure(conn: sqlite3.Connection, *, now: str) -> None:
    current = int(_meta_get(conn, _CIRCUIT_FAILURES) or "0") + 1
    _meta_set(conn, _CIRCUIT_FAILURES, str(current))
    if current >= CIRCUIT_THRESHOLD:
        _meta_set(conn, _CIRCUIT_OPEN_UNTIL, _add_seconds(now, CIRCUIT_COOLDOWN_SECONDS))


def _circuit_open(conn: sqlite3.Connection, now: str) -> bool:
    until = _meta_get(conn, _CIRCUIT_OPEN_UNTIL)
    return until is not None and until > now


def _expire_leases(conn: sqlite3.Connection, now: str) -> None:
    rows = conn.execute(
        "SELECT * FROM jobs WHERE status = 'LEASED' AND lease_until < ?",
        (now,),
    ).fetchall()
    for row in rows:
        _expire_one(conn, _to_job(row), now)


def _expire_one(conn: sqlite3.Connection, job: JobView, now: str) -> None:
    token = job.lease_until
    if token is None:
        return
    attempts = job.attempts + 1
    if attempts >= MAX_ATTEMPTS:
        cur = conn.execute(
            """
            UPDATE jobs
            SET status = 'DEAD', attempts = ?, last_error = ?, lease_until = NULL
            WHERE id = ? AND status = 'LEASED' AND lease_until = ? AND lease_until < ?
            """,
            (attempts, "lease expired", int(job.id), token, now),
        )
        if cur.rowcount == 1 and job.episode_id is not None:
            set_episode_status(conn, job.episode_id, EpisodeStatus.FAILED)
            advance_watermark(conn, job.scope_id)
        return
    nxt = _add_seconds(now, backoff_seconds(attempts, jitter=0.0))
    conn.execute(
        """
        UPDATE jobs
        SET status = 'QUEUED', attempts = ?, last_error = ?, next_run_at = ?, lease_until = NULL
        WHERE id = ? AND status = 'LEASED' AND lease_until = ? AND lease_until < ?
        """,
        (attempts, "lease expired", nxt, int(job.id), token, now),
    )


def _update_held_lease(
    conn: sqlite3.Connection,
    *,
    job_id: str,
    lease_until: str,
    now: str,
    sql: str,
    params: tuple[object, ...] = (),
) -> None:
    cur = conn.execute(
        f"{sql} WHERE id = ? AND status = 'LEASED' AND lease_until = ? AND lease_until > ?",
        (*params, int(job_id), lease_until, now),
    )
    if cur.rowcount != 1:
        raise StaleLeaseError(f"stale lease for job {job_id}")


def _require_job(conn: sqlite3.Connection, job_id: str) -> JobView:
    job = get_job(conn, job_id)
    if job is None:
        raise UnknownJobError(f"unknown job: {job_id}")
    return job


def _to_job(row: sqlite3.Row) -> JobView:
    payload = json.loads(row["payload"])
    episode_id = payload.get("episode_id")
    return JobView(
        id=str(row["id"]),
        kind=JobKind(row["kind"]),
        scope_id=int(row["scope_id"]),
        status=JobStatus(row["status"]),
        attempts=int(row["attempts"]),
        next_run_at=str(row["next_run_at"]),
        lease_until=None if row["lease_until"] is None else str(row["lease_until"]),
        last_error=None if row["last_error"] is None else str(row["last_error"]),
        episode_id=None if episode_id is None else int(episode_id),
    )


def _idempotency_key(kind: JobKind, scope_id: int, episode_id: int | None) -> str:
    if episode_id is None:
        return f"{kind.value}:{scope_id}:{new_ulid()}"
    return f"{kind.value}:{scope_id}:{episode_id}"


def _add_seconds(now: str, seconds: float) -> str:
    return format_instant(parse_instant(now) + timedelta(seconds=seconds))


def _meta_get(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return None if row is None else str(row["value"])


def _meta_set(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        """
        INSERT INTO meta(key, value) VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (key, value),
    )

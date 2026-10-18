"""Episode log writes. Functions never commit; callers own the transaction."""

from __future__ import annotations

import hashlib
import sqlite3

from tensemem.core.ids import new_ulid
from tensemem.core.models import EpisodeKind, EpisodeRole, EpisodeStatus


def insert_episode(
    conn: sqlite3.Connection,
    *,
    scope_id: int,
    content: str,
    now: str,
    kind: EpisodeKind = EpisodeKind.EXPLICIT_OP,
    role: EpisodeRole = EpisodeRole.USER,
    status: EpisodeStatus = EpisodeStatus.PROCESSED,
) -> tuple[int, str]:
    """Append an episode and return ``(seq, public_id)``. ``seq`` is ``episodes.id``."""
    public_id = new_ulid()
    digest = hashlib.sha256(f"{public_id}\n{content}".encode()).hexdigest()
    row = conn.execute(
        """
        INSERT INTO episodes (
          public_id, scope_id, kind, role, content, occurred_at, ingested_at,
          content_hash, status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        RETURNING id
        """,
        (
            public_id,
            scope_id,
            kind.value,
            role.value,
            content,
            now,
            now,
            digest,
            status.value,
        ),
    ).fetchone()
    return int(row["id"]), public_id


def set_episode_status(conn: sqlite3.Connection, episode_id: int, status: EpisodeStatus) -> None:
    conn.execute("UPDATE episodes SET status = ? WHERE id = ?", (status.value, episode_id))


def set_applied_seq(conn: sqlite3.Connection, scope_id: int, seq: int) -> None:
    conn.execute("UPDATE scopes SET applied_seq = ? WHERE id = ?", (seq, scope_id))


def advance_watermark(conn: sqlite3.Connection, scope_id: int) -> int:
    """Set ``applied_seq`` to the contiguous terminal prefix. Never decreases.

    FAILED jobs stay off the watermark so a retry cannot sit behind a pending
    episode. DISMISSED, PROCESSED, and SKIPPED count as terminal.
    """
    row = conn.execute(
        """
        SELECT MIN(id) AS n FROM episodes
        WHERE scope_id = ? AND status IN ('PENDING', 'FAILED')
        """,
        (scope_id,),
    ).fetchone()
    if row["n"] is None:
        latest = conn.execute(
            "SELECT COALESCE(MAX(id), 0) AS n FROM episodes WHERE scope_id = ?",
            (scope_id,),
        ).fetchone()
        seq = int(latest["n"])
    else:
        seq = int(row["n"]) - 1
    current = conn.execute("SELECT applied_seq FROM scopes WHERE id = ?", (scope_id,)).fetchone()
    applied = 0 if current is None else int(current["applied_seq"])
    if seq > applied:
        set_applied_seq(conn, scope_id, seq)
        return seq
    return applied

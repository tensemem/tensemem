"""Episode log writes. Functions never commit; callers own the transaction."""

from __future__ import annotations

import hashlib
import sqlite3

from tensemem.core.ids import new_ulid
from tensemem.core.models import EpisodeKind, EpisodeRole, EpisodeStatus
from tensemem.security.scrub import scrub

_HOT_LIMIT = 8


def insert_episode(
    conn: sqlite3.Connection,
    *,
    scope_id: int,
    content: str,
    now: str,
    kind: EpisodeKind = EpisodeKind.EXPLICIT_OP,
    role: EpisodeRole = EpisodeRole.USER,
    status: EpisodeStatus = EpisodeStatus.PROCESSED,
    occurred_at: str | None = None,
) -> tuple[int, str]:
    """Append an episode and return ``(seq, public_id)``. ``seq`` is ``episodes.id``."""
    public_id = new_ulid()
    content = scrub(content)
    digest = hashlib.sha256(f"{public_id}\n{content}".encode()).hexdigest()
    when = occurred_at or now
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
            when,
            now,
            digest,
            status.value,
        ),
    ).fetchone()
    episode_id = int(row["id"])
    index_episode(conn, episode_id, content)
    return episode_id, public_id


def index_episode(conn: sqlite3.Connection, episode_id: int, content: str) -> None:
    conn.execute("INSERT INTO episodes_fts(rowid, content) VALUES (?, ?)", (episode_id, content))


def unindex_episode(conn: sqlite3.Connection, episode_id: int, content: str) -> None:
    conn.execute(
        "INSERT INTO episodes_fts(episodes_fts, rowid, content) VALUES ('delete', ?, ?)",
        (episode_id, content),
    )


def list_hot_buffer(
    conn: sqlite3.Connection, scope_id: int, *, limit: int = _HOT_LIMIT
) -> tuple[str, ...]:
    """Newest-first unprocessed user messages, returned oldest-first for display."""
    rows = conn.execute(
        """
        SELECT content FROM episodes
        WHERE scope_id = ?
          AND role = 'user'
          AND kind = 'message'
          AND status IN ('PENDING', 'FAILED')
        ORDER BY id DESC
        LIMIT ?
        """,
        (scope_id, limit),
    ).fetchall()
    newest_first = [str(row["content"]) for row in rows]
    return tuple(reversed(newest_first))


def get_episode(conn: sqlite3.Connection, episode_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM episodes WHERE id = ?", (episode_id,)).fetchone()


def list_episodes(conn: sqlite3.Connection, scope_id: int) -> tuple[sqlite3.Row, ...]:
    rows = conn.execute(
        "SELECT * FROM episodes WHERE scope_id = ? ORDER BY id",
        (scope_id,),
    ).fetchall()
    return tuple(rows)


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

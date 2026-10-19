"""Aggregate counts for ``Memory.stats()``."""

from __future__ import annotations

import sqlite3

from tensemem.core.models import MemoryStats, Scope


def empty_stats() -> MemoryStats:
    """Zero counts for a scope that does not exist yet."""
    return MemoryStats(
        scopes=0,
        episodes=0,
        facts=0,
        queue_depth=0,
        pending_episodes=0,
        failed_episodes=0,
        rejected_claims=0,
        estimated_tokens=0,
    )


def load_stats(conn: sqlite3.Connection, scope: Scope | None) -> MemoryStats:
    """Database-wide counts, or one scope when ``scope`` is set."""
    scoped = scope is not None
    if scope is None:
        params: tuple[object, ...] = ()
        where = ""
        scope_sql = "SELECT COUNT(*) FROM scopes"
    else:
        params = (scope.id,)
        where = " WHERE scope_id = ?"
        scope_sql = "SELECT COUNT(*) FROM scopes WHERE id = ?"
    scopes = _one(conn, scope_sql, params)
    episodes = _one(conn, f"SELECT COUNT(*) FROM episodes{where}", params)
    facts = _one(conn, f"SELECT COUNT(*) FROM facts{where}", params)
    pending = _one(
        conn,
        f"SELECT COUNT(*) FROM episodes{where}{_and(scoped)} status = 'PENDING'",
        params,
    )
    failed = _one(
        conn,
        f"SELECT COUNT(*) FROM episodes{where}{_and(scoped)} status = 'FAILED'",
        params,
    )
    rejected = _one(conn, f"SELECT COUNT(*) FROM rejected_claims{where}", params)
    facts_by_status = _group(
        conn, f"SELECT status, COUNT(*) FROM facts{where} GROUP BY status", params
    )
    jobs_by_status = _group(
        conn, f"SELECT status, COUNT(*) FROM jobs{where} GROUP BY status", params
    )
    episode_chars = _one(
        conn, f"SELECT COALESCE(SUM(LENGTH(content)), 0) FROM episodes{where}", params
    )
    fact_chars = _one(
        conn, f"SELECT COALESCE(SUM(LENGTH(object_text)), 0) FROM facts{where}", params
    )
    corrections = _group(
        conn,
        (
            f"SELECT COALESCE(extractor_version, 'unknown'), COUNT(*) FROM facts{where}"
            f"{_and(scoped)} status = 'REJECTED' GROUP BY 1"
        ),
        params,
    )
    if scope is not None:
        version = scope.projection_version
    else:
        version = max(_one(conn, "SELECT COALESCE(MAX(projection_version), 1) FROM scopes"), 1)
    return MemoryStats(
        scopes=scopes,
        episodes=episodes,
        facts=facts,
        facts_by_status=facts_by_status,
        jobs_by_status=jobs_by_status,
        queue_depth=jobs_by_status.get("QUEUED", 0) + jobs_by_status.get("LEASED", 0),
        pending_episodes=pending,
        failed_episodes=failed,
        rejected_claims=rejected,
        estimated_tokens=(episode_chars + fact_chars) // 4,
        corrections_by_extractor=corrections,
        projection_version=version,
    )


def _and(scoped: bool) -> str:
    return " AND" if scoped else " WHERE"


def _one(conn: sqlite3.Connection, sql: str, params: tuple[object, ...] = ()) -> int:
    row = conn.execute(sql, params).fetchone()
    return 0 if row is None else int(row[0])


def _group(conn: sqlite3.Connection, sql: str, params: tuple[object, ...] = ()) -> dict[str, int]:
    return {str(row[0]): int(row[1]) for row in conn.execute(sql, params).fetchall()}

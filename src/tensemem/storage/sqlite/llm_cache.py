"""LLM response cache rows. Functions never commit."""

from __future__ import annotations

import sqlite3


def get_cached(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute("SELECT response FROM llm_cache WHERE key = ?", (key,)).fetchone()
    return None if row is None else str(row["response"])


def put_cached(conn: sqlite3.Connection, key: str, response: str, now: str) -> None:
    conn.execute(
        """
        INSERT INTO llm_cache(key, response, created_at)
        VALUES (?, ?, ?)
        ON CONFLICT(key) DO UPDATE SET
          response = excluded.response,
          created_at = excluded.created_at
        """,
        (key, response, now),
    )

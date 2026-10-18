"""Key/value rows in ``meta``. Functions never commit."""

from __future__ import annotations

import secrets
import sqlite3

FENCE_TAG_KEY = "fence_tag"


def get_fence_tag(conn: sqlite3.Connection) -> str | None:
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (FENCE_TAG_KEY,)).fetchone()
    return None if row is None else str(row["value"])


def ensure_fence_tag(conn: sqlite3.Connection) -> str:
    conn.execute(
        "INSERT OR IGNORE INTO meta(key, value) VALUES (?, ?)",
        (FENCE_TAG_KEY, secrets.token_hex(8)),
    )
    tag = get_fence_tag(conn)
    if tag is None:
        msg = "fence tag was not stored"
        raise RuntimeError(msg)
    return tag

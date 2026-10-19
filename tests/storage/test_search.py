import sqlite3
from datetime import UTC, datetime

from tensemem import Memory
from tensemem.core.clock import FrozenClock
from tensemem.core.models import EpisodeKind, ScopeKey
from tensemem.storage.sqlite import SqliteDatabase
from tensemem.storage.sqlite.episodes import insert_episode
from tensemem.storage.sqlite.scopes import get_or_create_scope
from tensemem.storage.sqlite.search import search_episodes


def test_episode_insert_is_searchable(db: SqliteDatabase) -> None:
    def write(conn: sqlite3.Connection) -> int:
        now = db.now()
        scope = get_or_create_scope(conn, ScopeKey(user_id="u1"), now=now)
        insert_episode(
            conn,
            scope_id=scope.id,
            content="We picked Koramangala for dinner",
            now=now,
            kind=EpisodeKind.MESSAGE,
        )
        return scope.id

    scope_id = db.transaction(write)
    episodes = db.read(lambda conn: search_episodes(conn, scope_id, "Koramangala dinner"))
    assert episodes
    assert "Koramangala" in episodes[0].content


def test_fact_fts_matches_live_to_lives_in() -> None:
    clock = FrozenClock(datetime(2026, 10, 18, 11, 0, 0, tzinfo=UTC))
    with Memory(":memory:", clock=clock) as mem:
        mem.register_predicate("lives_in")
        mem.set(user_id="u1", predicate="lives_in", value="Bangalore")
        hits = mem.search("u1", "live")
        assert hits.hits
        assert hits.hits[0].predicate == "lives_in"

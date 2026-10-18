from tensemem.core.models import ExtractionResult
from tensemem.providers.llm import CachedProvider, FakeExtractor, MemoryCache, SqliteCache
from tensemem.storage.sqlite import SqliteDatabase


def test_memory_cache_skips_second_call() -> None:
    inner = FakeExtractor()
    cached = CachedProvider(inner, MemoryCache())
    messages = [{"role": "user", "content": "I live in Delhi"}]
    first = cached.structured(messages, ExtractionResult)
    second = cached.structured(messages, ExtractionResult)
    assert first == second
    assert len(inner.calls) == 1


def test_sqlite_cache_round_trip() -> None:
    with SqliteDatabase(":memory:") as db:
        inner = FakeExtractor()
        cached = CachedProvider(inner, SqliteCache(db))
        messages = [{"role": "user", "content": "I live in Pune"}]
        first = cached.structured(messages, ExtractionResult)
        other = FakeExtractor()
        again = CachedProvider(other, SqliteCache(db)).structured(messages, ExtractionResult)
        assert first == again
        assert other.calls == []
        assert first.ops[0].object == "Pune"

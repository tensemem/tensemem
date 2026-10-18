"""Wrap any LLMProvider with a response cache."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Protocol, TypeVar

from pydantic import BaseModel

from tensemem.providers.llm.base import LLMProvider, prompt_key
from tensemem.storage.sqlite.database import SqliteDatabase
from tensemem.storage.sqlite.llm_cache import get_cached, put_cached

T = TypeVar("T", bound=BaseModel)


class CacheStore(Protocol):
    def get(self, key: str) -> str | None: ...

    def put(self, key: str, response: str) -> None: ...


class MemoryCache:
    def __init__(self) -> None:
        self._rows: dict[str, str] = {}

    def get(self, key: str) -> str | None:
        return self._rows.get(key)

    def put(self, key: str, response: str) -> None:
        self._rows[key] = response


class SqliteCache:
    def __init__(self, db: SqliteDatabase) -> None:
        self._db = db

    def get(self, key: str) -> str | None:
        return self._db.read(lambda conn: get_cached(conn, key))

    def put(self, key: str, response: str) -> None:
        now = self._db.now()
        self._db.transaction(lambda conn: put_cached(conn, key, response, now))


class CachedProvider:
    """Return a stored response when the prompt hash matches."""

    def __init__(self, inner: LLMProvider, store: CacheStore) -> None:
        self._inner = inner
        self._store = store

    @property
    def model(self) -> str:
        return self._inner.model

    def structured(
        self,
        messages: Sequence[Mapping[str, str]],
        schema: type[T],
        **kwargs: Any,
    ) -> T:
        key = prompt_key(self.model, messages, schema, extras=kwargs or None)
        hit = self._store.get(key)
        if hit is not None:
            return schema.model_validate_json(hit)
        result = self._inner.structured(messages, schema, **kwargs)
        self._store.put(key, result.model_dump_json())
        return result

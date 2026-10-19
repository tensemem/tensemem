"""OpenAI embeddings. Optional extra: ``tensemem[openai]``."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, cast

from tensemem.providers.llm.base import ProviderError, attr, load_optional


class OpenAIEmbedder:
    def __init__(
        self,
        model: str = "text-embedding-3-small",
        *,
        client: object | None = None,
        api_key: str | None = None,
        dim: int = 1536,
    ) -> None:
        self.model = model
        self.dim = dim
        self._client = client
        self._api_key = api_key

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        client = self._client if self._client is not None else _client(self._api_key)
        create = attr(client, "embeddings.create")
        if create is None:
            raise ProviderError("openai client has no embeddings.create")
        response = create(model=self.model, input=list(texts))
        vectors = _vectors(response)
        if len(vectors) != len(texts):
            raise ProviderError("openai embedder returned the wrong number of vectors")
        return vectors


def _vectors(response: object) -> list[list[float]]:
    data = getattr(response, "data", None)
    if not isinstance(data, list):
        return []
    out: list[list[float]] = []
    for row in cast(list[object], data):
        embedding = getattr(row, "embedding", None)
        if not isinstance(embedding, list):
            raise ProviderError("openai embedder returned a non-vector")
        numbers = cast(list[object], embedding)
        values = [float(value) for value in numbers if isinstance(value, int | float)]
        if len(values) != len(numbers):
            raise ProviderError("openai embedder returned a non-vector")
        out.append(values)
    return out


def _client(api_key: str | None) -> Any:
    cls = load_optional("openai", "OpenAI", "openai")
    return cls(api_key=api_key) if api_key else cls()

"""Local ONNX embeddings. Optional extra: ``tensemem[local]``."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Protocol

from tensemem.providers.llm.base import load_optional


class _Engine(Protocol):
    def embed(self, texts: Sequence[str]) -> Iterable[Sequence[float]]: ...


class FastEmbedProvider:
    def __init__(self, model: str = "BAAI/bge-small-en-v1.5", dim: int = 384) -> None:
        self.model = model
        self.dim = dim
        self._engine: _Engine | None = None

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        engine = self._engine
        if engine is None:
            cls = load_optional("fastembed", "TextEmbedding", "local")
            engine = cls(model_name=self.model)
            self._engine = engine
        return [list(vector) for vector in engine.embed(list(texts))]

"""Deterministic embedder for tests. Same tokens land near each other."""

from __future__ import annotations

import hashlib
from collections.abc import Sequence


class FakeEmbedder:
    model = "fake"
    dim = 8

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [_vector(text, self.dim) for text in texts]


def _vector(text: str, dim: int) -> list[float]:
    values = [0.0] * dim
    for token in text.casefold().replace("_", " ").split():
        digest = hashlib.sha256(token.encode()).digest()
        values[digest[0] % dim] += 1.0
    return values

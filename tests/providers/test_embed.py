from types import SimpleNamespace

import pytest

from tensemem.providers.embed import FakeEmbedder, FastEmbedProvider, OpenAIEmbedder
from tensemem.providers.llm.base import ProviderError, load_optional


def test_fake_embedder_is_deterministic_and_token_sensitive() -> None:
    embedder = FakeEmbedder()
    left, right, other = embedder.embed(["lives in Bangalore", "lives in Bangalore", "writes Rust"])
    assert left == right
    assert left != other
    assert embedder.dim == 8


def test_fastembed_requires_extra(monkeypatch: pytest.MonkeyPatch) -> None:
    def missing(module_name: str, class_name: str, extra: str) -> object:
        raise ProviderError(f"{class_name} needs tensemem[{extra}]")

    monkeypatch.setattr("tensemem.providers.embed.fastembed.load_optional", missing)
    with pytest.raises(ProviderError, match="local"):
        FastEmbedProvider().embed(["hello"])


def test_openai_embedder_uses_injected_client() -> None:
    response = SimpleNamespace(
        data=[
            SimpleNamespace(embedding=[0.1, 0.2]),
            SimpleNamespace(embedding=[0.3, 0.4]),
        ]
    )

    def create(**kwargs: object) -> SimpleNamespace:
        del kwargs
        return response

    client = SimpleNamespace(embeddings=SimpleNamespace(create=create))
    embedder = OpenAIEmbedder(client=client, dim=2)
    assert embedder.embed(["a", "b"]) == [[0.1, 0.2], [0.3, 0.4]]


def test_load_optional_mentions_extra() -> None:
    with pytest.raises(ProviderError, match="local"):
        load_optional("tensemem_missing_fastembed", "TextEmbedding", "local")

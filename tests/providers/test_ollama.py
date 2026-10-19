from types import SimpleNamespace

import pytest

from tensemem.core.models import ExtractionResult
from tensemem.providers.llm import OllamaProvider, ProviderError


def test_ollama_parses_injected_client() -> None:
    expected = ExtractionResult(ops=())
    provider = OllamaProvider(client=_ollama_client(expected.model_dump_json()))
    result = provider.structured([{"role": "user", "content": "hi"}], ExtractionResult)
    assert result == expected


def test_ollama_empty_chat_raises() -> None:
    provider = OllamaProvider(client=_ollama_client(""))
    with pytest.raises(ProviderError, match="empty"):
        provider.structured([{"role": "user", "content": "hi"}], ExtractionResult)


def test_ollama_unusable_payload_raises() -> None:
    provider = OllamaProvider(client=_ollama_client("not-json"))
    with pytest.raises(ProviderError, match="unusable"):
        provider.structured([{"role": "user", "content": "hi"}], ExtractionResult)


def test_ollama_missing_chat_raises() -> None:
    provider = OllamaProvider(client=SimpleNamespace())
    with pytest.raises(ProviderError, match="chat"):
        provider.structured([{"role": "user", "content": "hi"}], ExtractionResult)


def _ollama_client(content: object) -> object:
    def chat(**_kw: object) -> object:
        return SimpleNamespace(message=SimpleNamespace(content=content))

    return SimpleNamespace(chat=chat)

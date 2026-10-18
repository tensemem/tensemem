from types import SimpleNamespace

import pytest

from tensemem.core.models import ExtractionResult
from tensemem.providers.llm import OpenAIProvider, ProviderError
from tensemem.providers.llm.base import load_optional


def test_openai_parses_injected_client() -> None:
    expected = ExtractionResult(ops=())
    provider = OpenAIProvider(client=_openai_client(expected))
    result = provider.structured([{"role": "user", "content": "hi"}], ExtractionResult)
    assert result == expected


def test_openai_empty_parse_raises() -> None:
    provider = OpenAIProvider(client=_openai_client(None))
    with pytest.raises(ProviderError, match="empty"):
        provider.structured([{"role": "user", "content": "hi"}], ExtractionResult)


def test_missing_extra_is_explicit() -> None:
    with pytest.raises(ProviderError, match=r"tensemem\[openai\]"):
        load_optional("tensemem_no_such_pkg", "OpenAI", "openai")


def test_openai_missing_parse_raises() -> None:
    provider = OpenAIProvider(client=SimpleNamespace())
    with pytest.raises(ProviderError, match="parse"):
        provider.structured([{"role": "user", "content": "hi"}], ExtractionResult)


def _openai_client(parsed: object) -> object:
    completion = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(parsed=parsed))])

    def parse(**_kw: object) -> object:
        return completion

    return SimpleNamespace(
        beta=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(parse=parse)))
    )

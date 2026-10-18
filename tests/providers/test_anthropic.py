from types import SimpleNamespace

import pytest

from tensemem.core.models import ExtractionResult
from tensemem.providers.llm import AnthropicProvider, ProviderError


def test_anthropic_parses_and_lifts_system() -> None:
    expected = ExtractionResult(ops=())
    seen: dict[str, object] = {}

    def parse(**kwargs: object) -> object:
        seen.update(kwargs)
        return SimpleNamespace(parsed_output=expected)

    provider = AnthropicProvider(client=SimpleNamespace(messages=SimpleNamespace(parse=parse)))
    result = provider.structured(
        [
            {"role": "system", "content": "extract facts"},
            {"role": "user", "content": "I live in Delhi"},
        ],
        ExtractionResult,
    )
    assert result == expected
    assert seen["system"] == "extract facts"
    messages = seen["messages"]
    assert isinstance(messages, list)
    assert messages == [{"role": "user", "content": "I live in Delhi"}]


def test_anthropic_empty_parse_raises() -> None:
    def parse(**_kw: object) -> object:
        return SimpleNamespace(parsed_output=None)

    provider = AnthropicProvider(client=SimpleNamespace(messages=SimpleNamespace(parse=parse)))
    with pytest.raises(ProviderError, match="empty"):
        provider.structured([{"role": "user", "content": "hi"}], ExtractionResult)

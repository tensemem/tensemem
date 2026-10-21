from types import SimpleNamespace

import pytest

from tensemem.core.models import ExtractionResult
from tensemem.providers.llm import LiteLLMProvider, ProviderError


def test_litellm_parses_injected_complete() -> None:
    expected = ExtractionResult(ops=())
    seen: dict[str, object] = {}

    def complete(**kwargs: object) -> object:
        seen.update(kwargs)
        return _completion(expected.model_dump_json())

    provider = LiteLLMProvider(complete=complete)
    result = provider.structured([{"role": "user", "content": "hi"}], ExtractionResult)
    assert result == expected
    assert seen["model"] == "openai/gpt-4o-mini"
    assert seen["timeout"] is not None
    assert seen["request_timeout"] is not None
    format_ = seen["response_format"]
    assert isinstance(format_, dict)
    assert format_["type"] == "json_schema"


def test_litellm_gemini_sets_low_reasoning() -> None:
    seen: dict[str, object] = {}

    def complete(**kwargs: object) -> object:
        seen.update(kwargs)
        return _completion(ExtractionResult(ops=()).model_dump_json())

    provider = LiteLLMProvider(model="gemini/gemini-3.8-flash", complete=complete)
    provider.structured([{"role": "user", "content": "hi"}], ExtractionResult)
    assert seen["reasoning_effort"] == "low"


def test_litellm_prefers_parsed_field() -> None:
    expected = ExtractionResult(ops=())

    def complete(**_kwargs: object) -> object:
        return _completion(None, parsed=expected)

    provider = LiteLLMProvider(complete=complete)
    result = provider.structured([{"role": "user", "content": "hi"}], ExtractionResult)
    assert result == expected


def test_litellm_empty_complete_raises() -> None:
    def complete(**_kwargs: object) -> object:
        return _completion("")

    provider = LiteLLMProvider(complete=complete)
    with pytest.raises(ProviderError, match="empty"):
        provider.structured([{"role": "user", "content": "hi"}], ExtractionResult)


def test_litellm_unusable_payload_raises() -> None:
    def complete(**_kwargs: object) -> object:
        return _completion("not-json")

    provider = LiteLLMProvider(complete=complete)
    with pytest.raises(ProviderError, match="unusable"):
        provider.structured([{"role": "user", "content": "hi"}], ExtractionResult)


def test_litellm_non_callable_raises() -> None:
    provider = LiteLLMProvider(complete=object())
    with pytest.raises(ProviderError, match="callable"):
        provider.structured([{"role": "user", "content": "hi"}], ExtractionResult)


def _completion(content: object, *, parsed: object | None = None) -> object:
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content, parsed=parsed))]
    )

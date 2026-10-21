import json

import pytest

from tensemem.core.models import ExtractionResult
from tensemem.providers.llm.base import ProviderError
from tensemem.providers.llm.gemini import GeminiProvider


def test_gemini_parses_generate_content(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "not-a-real-secret")
    seen: list[str] = []

    def post(
        url: str, payload: bytes, headers: dict[str, str], timeout: float
    ) -> tuple[int, bytes]:
        seen.append(url)
        assert timeout == 45.0
        assert headers["x-goog-api-key"] == "not-a-real-secret"
        body = json.loads(payload)
        assert body["generationConfig"]["responseMimeType"] == "application/json"
        assert "responseSchema" in body["generationConfig"]
        return 200, _ok(ExtractionResult(ops=()).model_dump_json())

    provider = GeminiProvider(model="gemini/gemini-3.6-flash", post=post)
    result = provider.structured([{"role": "user", "content": "hi"}], ExtractionResult)
    assert result.ops == ()
    assert seen[0].endswith("/gemini-3.6-flash:generateContent")


def test_gemini_falls_back_after_503(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "not-a-real-secret")
    seen: list[str] = []

    def post(
        url: str, payload: bytes, headers: dict[str, str], timeout: float
    ) -> tuple[int, bytes]:
        del payload, headers, timeout
        seen.append(url)
        if "gemini-3.8-flash" in url:
            return 503, b'{"error":{"message":"high demand"}}'
        return 200, _ok('{"ops":[]}')

    provider = GeminiProvider(
        model="gemini-3.8-flash",
        fallbacks=("gemini-3.6-flash",),
        post=post,
    )
    result = provider.structured([{"role": "user", "content": "hi"}], ExtractionResult)
    assert result.ops == ()
    assert any("gemini-3.8-flash" in url for url in seen)
    assert seen[-1].endswith("/gemini-3.6-flash:generateContent")


def test_gemini_ignores_thought_and_extra_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "not-a-real-secret")
    messy = {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {"thought": True, "text": "planning the extract"},
                        {
                            "text": (
                                '```json\n{"ops":[{"subject":"user","predicate":"lives_in",'
                                '"value":"Mumbai","op":"set","extra":"drop-me"}]}\n```'
                            )
                        },
                    ]
                }
            }
        ]
    }

    def post(
        url: str, payload: bytes, headers: dict[str, str], timeout: float
    ) -> tuple[int, bytes]:
        del url, payload, headers, timeout
        return 200, json.dumps(messy).encode()

    provider = GeminiProvider(post=post)
    result = provider.structured([{"role": "user", "content": "hi"}], ExtractionResult)
    assert len(result.ops) == 1
    assert result.ops[0].predicate == "lives_in"
    assert result.ops[0].object == "Mumbai"
    assert result.ops[0].op.value == "SET"
    assert result.ops[0].new_predicate is not None
    assert result.ops[0].evidence == "hi"


def test_gemini_missing_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

    def missing(*_args: object) -> tuple[int, bytes]:
        return 200, b"{}"

    provider = GeminiProvider(post=missing)
    with pytest.raises(ProviderError, match="GEMINI_API_KEY"):
        provider.structured([{"role": "user", "content": "hi"}], ExtractionResult)


def _ok(text: str) -> bytes:
    return json.dumps({"candidates": [{"content": {"parts": [{"text": text}]}}]}).encode()

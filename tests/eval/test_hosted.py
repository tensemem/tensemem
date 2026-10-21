from collections.abc import Mapping, Sequence
from typing import Any, TypeVar

import pytest
from pydantic import BaseModel

from tensemem.eval.hosted import hosted_secret_status, provider_from_name
from tensemem.eval.locomo import run_locomo
from tensemem.eval.longmem import run_longmem

T = TypeVar("T", bound=BaseModel)


class _Silent:
    model = "silent"

    def __init__(self) -> None:
        self.calls = 0

    def structured(
        self,
        messages: Sequence[Mapping[str, str]],
        schema: type[T],
        **kwargs: Any,
    ) -> T:
        del messages, kwargs
        self.calls += 1
        return schema.model_validate({"ops": []})


def test_provider_from_name_defaults_to_fake() -> None:
    assert provider_from_name(None) is None
    assert provider_from_name("fake") is None
    assert provider_from_name("  ") is None
    with pytest.raises(ValueError, match="llm must be"):
        provider_from_name("mystery")


def test_hosted_secret_status_reports_gemini_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    missing = hosted_secret_status("gemini")
    assert missing["GEMINI_API_KEY"] is False
    assert missing["ok"] is False
    assert missing["model"] == "gemini-3.6-flash"
    monkeypatch.setenv("GEMINI_API_KEY", "not-a-real-secret")
    present = hosted_secret_status("gemini")
    assert present["GEMINI_API_KEY"] is True


def test_provider_from_name_gemini_uses_rest_adapter() -> None:
    llm = provider_from_name("gemini")
    assert llm is not None
    assert llm.model == "gemini-3.6-flash"


def test_provider_from_name_openai_constructs() -> None:
    llm = provider_from_name("openai")
    assert llm is not None
    assert llm.model


def test_longmem_injected_llm_is_called() -> None:
    silent = _Silent()
    report = run_longmem(llm=silent)
    assert report.cases == 7
    assert silent.calls > 0


def test_locomo_injected_llm_is_called() -> None:
    silent = _Silent()
    report = run_locomo(llm=silent)
    assert report.cases == 5
    assert silent.calls > 0

"""LiteLLM structured-output adapter. Optional extra: ``tensemem[litellm]``."""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from tensemem.providers.llm.base import ProviderError, load_optional

T = TypeVar("T", bound=BaseModel)
_DEFAULT_TIMEOUT_SECONDS = 45.0


class LiteLLMProvider:
    def __init__(
        self,
        model: str = "openai/gpt-4o-mini",
        *,
        complete: object | None = None,
    ) -> None:
        self.model = model
        self.cache_namespace = "litellm"
        self._complete = complete

    def structured(
        self,
        messages: Sequence[Mapping[str, str]],
        schema: type[T],
        **kwargs: Any,
    ) -> T:
        complete = (
            self._complete
            if self._complete is not None
            else load_optional("litellm", "completion", "litellm")
        )
        if not callable(complete):
            raise ProviderError("litellm completion is not callable")
        timeout = kwargs.pop("timeout", _completion_timeout())
        extras: dict[str, object] = {}
        if self.model.startswith("gemini/") and "reasoning_effort" not in kwargs:
            extras["reasoning_effort"] = "low"
        seconds = timeout if isinstance(timeout, int | float) else _DEFAULT_TIMEOUT_SECONDS
        try:
            response = complete(
                model=self.model,
                messages=list(messages),
                response_format=_json_schema(schema),
                timeout=timeout,
                request_timeout=seconds,
                **extras,
                **kwargs,
            )
        except ProviderError:
            raise
        except Exception as extra:
            raise ProviderError(_litellm_error(self.model, extra)) from extra
        choices = getattr(response, "choices", None)
        message = getattr(choices[0], "message", None) if choices else None
        parsed = getattr(message, "parsed", None)
        if parsed is not None:
            return _validate(schema, parsed)
        content = getattr(message, "content", None)
        if content is None or content == "":
            raise ProviderError("litellm returned an empty structured response")
        return _validate(schema, content)


def _completion_timeout() -> float:
    return _DEFAULT_TIMEOUT_SECONDS


def _litellm_error(model: str, extra: Exception) -> str:
    gemini = bool(os.environ.get("GEMINI_API_KEY", "").strip())
    google = bool(os.environ.get("GOOGLE_API_KEY", "").strip())
    detail = str(extra) or type(extra).__name__
    return (
        f"{type(extra).__name__} model={model} "
        f"GEMINI_API_KEY={'set' if gemini else 'missing'} "
        f"GOOGLE_API_KEY={'set' if google else 'missing'}: {detail[:300]}"
    )


def _json_schema(schema: type[BaseModel]) -> dict[str, object]:
    return {
        "type": "json_schema",
        "json_schema": {
            "name": schema.__name__,
            "strict": True,
            "schema": schema.model_json_schema(),
        },
    }


def _validate(schema: type[T], payload: object) -> T:
    try:
        if isinstance(payload, BaseModel):
            return schema.model_validate(payload.model_dump())
        if isinstance(payload, Mapping):
            return schema.model_validate(payload)
        return schema.model_validate_json(payload if isinstance(payload, bytes) else str(payload))
    except (ValidationError, ValueError, TypeError) as exc:
        raise ProviderError("litellm returned an unusable structured response") from exc

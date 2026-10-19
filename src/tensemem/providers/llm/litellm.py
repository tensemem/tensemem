"""LiteLLM structured-output adapter. Optional extra: ``tensemem[litellm]``."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from tensemem.providers.llm.base import ProviderError, load_optional

T = TypeVar("T", bound=BaseModel)


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
        response = complete(
            model=self.model,
            messages=list(messages),
            response_format=_json_schema(schema),
            **kwargs,
        )
        choices = getattr(response, "choices", None)
        message = getattr(choices[0], "message", None) if choices else None
        parsed = getattr(message, "parsed", None)
        if parsed is not None:
            return _validate(schema, parsed)
        content = getattr(message, "content", None)
        if content is None or content == "":
            raise ProviderError("litellm returned an empty structured response")
        return _validate(schema, content)


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

"""OpenAI structured-output adapter. Optional extra: ``tensemem[openai]``."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, TypeVar

from pydantic import BaseModel

from tensemem.providers.llm.base import ProviderError, attr, load_optional

T = TypeVar("T", bound=BaseModel)


class OpenAIProvider:
    def __init__(
        self,
        model: str = "gpt-4o-mini",
        *,
        client: object | None = None,
        api_key: str | None = None,
    ) -> None:
        self.model = model
        self._client = client
        self._api_key = api_key

    def structured(
        self,
        messages: Sequence[Mapping[str, str]],
        schema: type[T],
        **kwargs: Any,
    ) -> T:
        client = self._client if self._client is not None else _client(self._api_key)
        parse = attr(client, "beta.chat.completions.parse") or attr(
            client, "chat.completions.parse"
        )
        if parse is None:
            raise ProviderError("openai client has no structured parse method")
        completion = parse(
            model=self.model,
            messages=list(messages),
            response_format=schema,
            **kwargs,
        )
        choices = getattr(completion, "choices", None)
        message = getattr(choices[0], "message", None) if choices else None
        parsed = getattr(message, "parsed", None)
        if parsed is None:
            raise ProviderError("openai returned an empty structured response")
        if isinstance(parsed, BaseModel):
            return schema.model_validate(parsed.model_dump())
        return schema.model_validate(parsed)


def _client(api_key: str | None) -> object:
    cls = load_optional("openai", "OpenAI", "openai")
    return cls(api_key=api_key) if api_key is not None else cls()

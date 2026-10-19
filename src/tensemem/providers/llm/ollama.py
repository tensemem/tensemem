"""Ollama structured-output adapter. Optional extra: ``tensemem[ollama]``."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from tensemem.providers.llm.base import ProviderError, attr, load_optional

T = TypeVar("T", bound=BaseModel)


class OllamaProvider:
    def __init__(
        self,
        model: str = "llama3.2",
        *,
        client: object | None = None,
        host: str | None = None,
    ) -> None:
        self.model = model
        self.cache_namespace = "ollama"
        self._client = client
        self._host = host

    def structured(
        self,
        messages: Sequence[Mapping[str, str]],
        schema: type[T],
        **kwargs: Any,
    ) -> T:
        client = self._client if self._client is not None else _client(self._host)
        chat = attr(client, "chat")
        if chat is None:
            raise ProviderError("ollama client has no chat method")
        response = chat(
            model=self.model,
            messages=list(messages),
            format=schema.model_json_schema(),
            **kwargs,
        )
        message = getattr(response, "message", None)
        content = getattr(message, "content", None)
        if content is None or content == "":
            raise ProviderError("ollama returned an empty structured response")
        return _validate(schema, content)


def _client(host: str | None) -> object:
    cls = load_optional("ollama", "Client", "ollama")
    return cls(host=host) if host is not None else cls()


def _validate(schema: type[T], payload: object) -> T:
    try:
        if isinstance(payload, BaseModel):
            return schema.model_validate(payload.model_dump())
        if isinstance(payload, Mapping):
            return schema.model_validate(payload)
        return schema.model_validate_json(payload if isinstance(payload, bytes) else str(payload))
    except (ValidationError, ValueError, TypeError) as exc:
        raise ProviderError("ollama returned an unusable structured response") from exc

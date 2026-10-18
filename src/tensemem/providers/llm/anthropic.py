"""Anthropic structured-output adapter. Optional extra: ``tensemem[anthropic]``."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, TypeVar

from pydantic import BaseModel

from tensemem.providers.llm.base import ProviderError, attr, load_optional

T = TypeVar("T", bound=BaseModel)


class AnthropicProvider:
    def __init__(
        self,
        model: str = "claude-haiku-5-5",
        *,
        client: object | None = None,
        api_key: str | None = None,
    ) -> None:
        self.model = model
        self.cache_namespace = "anthropic"
        self._client = client
        self._api_key = api_key

    def structured(
        self,
        messages: Sequence[Mapping[str, str]],
        schema: type[T],
        **kwargs: Any,
    ) -> T:
        client = self._client if self._client is not None else _client(self._api_key)
        parse = attr(client, "messages.parse")
        if parse is None:
            raise ProviderError("anthropic client has no structured parse method")
        system, rest = _split_system(messages)
        call: dict[str, Any] = {
            "model": self.model,
            "messages": rest,
            "max_tokens": kwargs.pop("max_tokens", 2048),
            "output_format": schema,
        }
        if system:
            call["system"] = system
        call.update(kwargs)
        message = parse(**call)
        parsed = getattr(message, "parsed_output", None)
        if parsed is None:
            raise ProviderError("anthropic returned an empty structured response")
        if isinstance(parsed, BaseModel):
            return schema.model_validate(parsed.model_dump())
        return schema.model_validate(parsed)


def _split_system(
    messages: Sequence[Mapping[str, str]],
) -> tuple[str, list[dict[str, str]]]:
    system_parts: list[str] = []
    rest: list[dict[str, str]] = []
    for message in messages:
        role = message.get("role", "")
        content = message.get("content", "")
        if role == "system":
            system_parts.append(content)
        elif role in {"user", "assistant"}:
            rest.append({"role": role, "content": content})
    return "\n".join(system_parts), rest


def _client(api_key: str | None) -> object:
    cls = load_optional("anthropic", "Anthropic", "anthropic")
    return cls(api_key=api_key) if api_key is not None else cls()

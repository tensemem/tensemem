"""LLM provider protocol: structured output, no extraction policy."""

from __future__ import annotations

import hashlib
import importlib
import json
from collections.abc import Mapping, Sequence
from typing import Any, Protocol, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class ProviderError(RuntimeError):
    """The provider package is missing or the model returned unusable output."""


class LLMProvider(Protocol):
    @property
    def model(self) -> str: ...

    def structured(
        self,
        messages: Sequence[Mapping[str, str]],
        schema: type[T],
        **kwargs: Any,
    ) -> T: ...


def last_user_text(messages: Sequence[Mapping[str, str]]) -> str:
    for message in reversed(messages):
        if message.get("role") == "user":
            return str(message.get("content", ""))
    return ""


def prompt_key(
    model: str,
    messages: Sequence[Mapping[str, str]],
    schema: type[BaseModel],
    extras: Mapping[str, object] | None = None,
    namespace: str = "",
) -> str:
    """Stable cache key for provider, model, messages, schema, and call args."""
    payload = {
        "namespace": namespace,
        "model": model,
        "messages": list(messages),
        "schema": schema.__name__,
        "schema_json": schema.model_json_schema(),
        "extras": extras or {},
    }
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(blob).hexdigest()


def attr(root: object, path: str) -> Any:
    current: Any = root
    for name in path.split("."):
        current = getattr(current, name, None)
        if current is None:
            return None
    return current


def load_optional(module_name: str, class_name: str, extra: str) -> Any:
    try:
        module = importlib.import_module(module_name)
    except ImportError as exc:
        raise ProviderError(f"{class_name} needs tensemem[{extra}]") from exc
    return getattr(module, class_name)

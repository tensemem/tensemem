"""Optional hosted extractors for long-session packs (ADR 0016)."""

from __future__ import annotations

from typing import cast

from tensemem.providers.llm.base import LLMProvider

_PROVIDERS = {
    "openai": ("tensemem.providers.llm.openai", "OpenAIProvider"),
    "anthropic": ("tensemem.providers.llm.anthropic", "AnthropicProvider"),
    "ollama": ("tensemem.providers.llm.ollama", "OllamaProvider"),
    "litellm": ("tensemem.providers.llm.litellm", "LiteLLMProvider"),
}


def provider_from_name(name: str | None) -> LLMProvider | None:
    """Build a named provider, or ``None`` so the pack keeps ``FakeExtractor``."""
    if name is None:
        return None
    key = name.strip().casefold()
    if not key or key == "fake":
        return None
    spec = _PROVIDERS.get(key)
    if spec is None:
        raise ValueError("llm must be openai, anthropic, ollama, litellm, or fake")
    module_name, class_name = spec
    module = __import__(module_name, fromlist=[class_name])
    cls = getattr(module, class_name)
    return cast(LLMProvider, cls())

"""Optional hosted extractors for long-session packs (ADR 0016)."""

from __future__ import annotations

import os
from typing import cast

from tensemem.providers.llm.base import LLMProvider

_PROVIDERS = {
    "openai": ("tensemem.providers.llm.openai", "OpenAIProvider"),
    "anthropic": ("tensemem.providers.llm.anthropic", "AnthropicProvider"),
    "ollama": ("tensemem.providers.llm.ollama", "OllamaProvider"),
    "litellm": ("tensemem.providers.llm.litellm", "LiteLLMProvider"),
}
_GEMINI_MODEL = "gemini-3.6-flash"
_GEMINI_FALLBACKS = ("gemini-3.6-flash", "gemini-3.5-flash-lite", "gemini-3.8-flash")
_LLM_NAMES = "openai, anthropic, ollama, litellm, gemini, or fake"


def hosted_secret_status(name: str) -> dict[str, object]:
    """Whether env secrets for ``name`` are set. Never returns the secret values."""
    key = name.strip().casefold()
    litellm_ok = _module_present("litellm")
    if key == "gemini":
        gemini = _env_set("GEMINI_API_KEY")
        google = _env_set("GOOGLE_API_KEY")
        return {
            "llm": "gemini",
            "model": (os.environ.get("TENSEMEM_LITELLM_MODEL") or _GEMINI_MODEL).strip()
            or _GEMINI_MODEL,
            "litellm_installed": litellm_ok,
            "GEMINI_API_KEY": gemini,
            "GOOGLE_API_KEY": google,
            "ok": gemini or google,
        }
    if key == "openai":
        present = _env_set("OPENAI_API_KEY")
        return {"llm": key, "OPENAI_API_KEY": present, "ok": present}
    if key == "anthropic":
        present = _env_set("ANTHROPIC_API_KEY")
        return {"llm": key, "ANTHROPIC_API_KEY": present, "ok": present}
    if key == "litellm":
        return {"llm": key, "litellm_installed": litellm_ok, "ok": litellm_ok}
    return {"llm": key or "fake", "ok": True}


def _env_set(name: str) -> bool:
    return bool(os.environ.get(name, "").strip())


def _module_present(name: str) -> bool:
    try:
        __import__(name)
    except ImportError:
        return False
    return True


def provider_from_name(name: str | None) -> LLMProvider | None:
    """Build a named provider, or ``None`` so the pack keeps ``FakeExtractor``."""
    if name is None:
        return None
    key = name.strip().casefold()
    if not key or key == "fake":
        return None
    if key == "gemini":
        from tensemem.providers.llm.gemini import GeminiProvider

        model = (os.environ.get("TENSEMEM_LITELLM_MODEL") or _GEMINI_MODEL).strip()
        return GeminiProvider(model=model or _GEMINI_MODEL, fallbacks=_GEMINI_FALLBACKS)
    spec = _PROVIDERS.get(key)
    if spec is None:
        raise ValueError(f"llm must be {_LLM_NAMES}")
    module_name, class_name = spec
    module = __import__(module_name, fromlist=[class_name])
    cls = getattr(module, class_name)
    return cast(LLMProvider, cls())

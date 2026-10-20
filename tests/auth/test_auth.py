import asyncio

import pytest

from tensemem.auth import (
    authorize,
    bind_warning,
    require_auth,
    resolve_token,
    wrap_bearer,
)


def test_resolve_token_prefers_cli_then_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TENSEMEM_TOKEN", raising=False)
    assert resolve_token(None) is None
    assert resolve_token("  ") is None
    assert resolve_token(" cli ") == "cli"
    monkeypatch.setenv("TENSEMEM_TOKEN", " from-env ")
    assert resolve_token(None) == "from-env"
    assert resolve_token("cli") == "cli"


def test_authorize_open_or_bearer() -> None:
    assert authorize(None, None) is True
    assert authorize("Bearer secret", None) is True
    assert authorize("Bearer secret", "secret") is True
    assert authorize("Bearer other", "secret") is False
    assert authorize("secret", "secret") is False
    assert authorize(None, "secret") is False
    assert authorize("Bearer ", "secret") is False
    assert authorize("Bearer café", "café") is True
    assert authorize("Bearer café", "cafè") is False


def test_require_auth_skips_health() -> None:
    assert require_auth("GET", "/health", None, "secret") is True
    assert require_auth("GET", "/health/", None, "secret") is True
    assert require_auth("POST", "/health", None, "secret") is False
    assert require_auth("GET", "/v1/state", None, "secret") is False
    assert require_auth("GET", "/v1/state", "Bearer secret", "secret") is True


def test_bind_warning_only_for_non_loopback() -> None:
    assert bind_warning("127.0.0.1", None) is None
    assert bind_warning("localhost", "secret") is None
    text = bind_warning("0.0.0.0", None)
    assert text is not None
    assert "no auth or TLS" in text
    tls = bind_warning("0.0.0.0", "secret")
    assert tls is not None
    assert "TLS is off" in tls
    assert "no auth" not in tls


def test_wrap_bearer_rejects_missing_header() -> None:
    asyncio.run(_wrap_bearer_case())


async def _wrap_bearer_case() -> None:
    seen: list[int] = []

    async def inner(scope: dict[str, object], receive: object, send: object) -> None:
        del scope, receive, send
        seen.append(1)

    app = wrap_bearer(inner, "secret")
    sent: list[dict[str, object]] = []

    async def send(message: dict[str, object]) -> None:
        sent.append(message)

    await app({"type": "http", "headers": []}, None, send)
    assert seen == []
    assert sent[0]["status"] == 401

    await app(
        {"type": "http", "headers": [(b"authorization", b"Bearer secret")]},
        None,
        send,
    )
    assert seen == [1]
    assert wrap_bearer(inner, None) is inner

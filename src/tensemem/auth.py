"""Optional bearer token for HTTP adapters (ADR 0015)."""

from __future__ import annotations

import os
import secrets
from typing import Any, cast

_UNAUTHORIZED = b'{"error":"unauthorized"}'
_LOOPBACK = frozenset({"127.0.0.1", "::1", "localhost"})


def resolve_token(cli: str | None = None) -> str | None:
    """Prefer ``--token``, then ``TENSEMEM_TOKEN``. Empty means auth is off."""
    for raw in (cli, os.environ.get("TENSEMEM_TOKEN")):
        text = (raw or "").strip()
        if text:
            return text
    return None


def authorize(authorization: str | None, token: str | None) -> bool:
    """True when no token is configured, or the header is ``Bearer <token>``."""
    expected = (token or "").strip()
    if not expected:
        return True
    header = (authorization or "").strip()
    prefix = "Bearer "
    if not header.startswith(prefix):
        return False
    got = header[len(prefix) :].strip()
    if len(got) != len(expected):
        secrets.compare_digest(expected, expected)
        return False
    return secrets.compare_digest(got, expected)


def health_path(path: str) -> bool:
    return (path.rstrip("/") or "/") == "/health"


def require_auth(
    method: str,
    path: str,
    authorization: str | None,
    token: str | None,
) -> bool:
    """``GET /health`` stays open so a probe does not need the token."""
    if method.upper() == "GET" and health_path(path):
        return True
    return authorize(authorization, token)


def is_loopback(host: str) -> bool:
    return host.strip().casefold() in _LOOPBACK


def bind_warning(host: str, token: str | None) -> str | None:
    """Stderr line for a non-loopback bind, or ``None`` on loopback."""
    if is_loopback(host):
        return None
    if (token or "").strip():
        return "TLS is off; put a TLS-terminating proxy in front of a non-loopback bind"
    return (
        "no auth or TLS; bind loopback, pass --token / TENSEMEM_TOKEN, "
        "or put a TLS-terminating, user-scoped proxy in front"
    )


def wrap_bearer(app: Any, token: str | None) -> Any:
    """ASGI wrapper that rejects unauthenticated HTTP when a token is set."""
    expected = (token or "").strip()
    if not expected:
        return app
    return _BearerASGI(app, expected)


class _BearerASGI:
    def __init__(self, app: Any, token: str) -> None:
        self.app = app
        self.token = token

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        headers = _headers(scope)
        if authorize(headers.get("authorization"), self.token):
            await self.app(scope, receive, send)
            return
        await send(
            {
                "type": "http.response.start",
                "status": 401,
                "headers": [(b"content-type", b"application/json")],
            }
        )
        await send({"type": "http.response.body", "body": _UNAUTHORIZED})


def _headers(scope: dict[str, Any]) -> dict[str, str]:
    raw: object = scope.get("headers", [])
    if not isinstance(raw, list):
        return {}
    out: dict[str, str] = {}
    for item in cast(list[object], raw):
        pair = _header_pair(item)
        if pair is None:
            continue
        key, value = pair
        out[key] = value
    return out


def _header_pair(item: object) -> tuple[str, str] | None:
    if not isinstance(item, tuple):
        return None
    pair = cast(tuple[object, ...], item)
    if len(pair) != 2:
        return None
    key, value = pair
    if not isinstance(key, bytes) or not isinstance(value, bytes):
        return None
    return key.decode("latin-1").casefold(), value.decode("latin-1")

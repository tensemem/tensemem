"""HTTP adapter: add, context, state, history, forget (ADR 0011)."""

from __future__ import annotations

import asyncio
import importlib
import json
import sys
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any, Final, cast

from tensemem.auth import bind_warning, require_auth
from tensemem.mcp import call_tool, seed_starter
from tensemem.memory import Memory
from tensemem.providers.llm.fake import FakeExtractor

_MISSING_EXTRA = "tensemem serve needs tensemem[server]"
_DEFAULT_HOST = "127.0.0.1"
_DEFAULT_PORT = 8080
MAX_BODY_BYTES = 65_536
ROUTES: Final[tuple[tuple[str, str], ...]] = (
    ("POST", "/v1/memories:add"),
    ("POST", "/v1/context"),
    ("GET", "/v1/state"),
    ("GET", "/v1/history"),
    ("DELETE", "/v1/scopes/{user_id}"),
    ("GET", "/health"),
)


def dispatch(
    mem: Memory,
    method: str,
    path: str,
    *,
    query: Mapping[str, object] | None = None,
    body: Mapping[str, object] | None = None,
    agent_id: str = "",
    namespace: str = "default",
) -> tuple[int, dict[str, object]]:
    """Map one HTTP call onto the same five operations as MCP."""
    verb = method.upper()
    route = path.rstrip("/") or "/"
    params = dict(query or {})
    payload = dict(body or {})
    try:
        if verb == "GET" and route == "/health":
            return 200, {"ok": True}
        if verb == "POST" and route == "/v1/memories:add":
            return 200, _tool(mem, "remember", payload, agent_id=agent_id, namespace=namespace)
        if verb == "POST" and route == "/v1/context":
            return 200, _tool(
                mem, "recall_context", payload, agent_id=agent_id, namespace=namespace
            )
        if verb == "GET" and route == "/v1/state":
            return 200, _tool(mem, "get_state", params, agent_id=agent_id, namespace=namespace)
        if verb == "GET" and route == "/v1/history":
            return 200, _tool(mem, "get_history", params, agent_id=agent_id, namespace=namespace)
        forgotten = _scope_user(verb, route)
        if forgotten is not None:
            return 200, _tool(
                mem,
                "forget",
                {"user_id": forgotten},
                agent_id=agent_id,
                namespace=namespace,
            )
    except ValueError as extra:
        return 400, {"error": str(extra)}
    return 404, {"error": "not found"}


def serve(
    path: str | Path = "tensemem.db",
    *,
    host: str = _DEFAULT_HOST,
    port: int = _DEFAULT_PORT,
    agent_id: str = "",
    namespace: str = "default",
    token: str | None = None,
) -> None:
    """Open ``path`` and serve the five routes until the process exits.

    The extract worker stays off so queued jobs from another process are not
    claimed by ``FakeExtractor``. ``POST /v1/memories:add`` still waits.
    """
    if port < 1 or port > 65535:
        raise ValueError("port must be between 1 and 65535")
    warning = bind_warning(host, token)
    if warning:
        print(f"tensemem serve: {warning}", file=sys.stderr)
    with Memory(path, llm=FakeExtractor(), start_worker=False) as mem:
        seed_starter(mem)
        run_http(
            mem,
            host=host,
            port=port,
            agent_id=agent_id,
            namespace=namespace,
            token=token,
        )


def create_app(
    mem: Memory,
    *,
    agent_id: str = "",
    namespace: str = "default",
    token: str | None = None,
) -> Any:
    """Build a FastAPI app. Import happens here so the extra stays optional."""
    fastapi = _load("fastapi", "FastAPI")
    json_response = _load("fastapi.responses", "JSONResponse")
    app = fastapi(title="TenseMem", version="0.0.1")

    async def handle(request: Any) -> Any:
        authorization = request.headers.get("authorization")
        if not require_auth(request.method, request.url.path, authorization, token):
            return json_response({"error": "unauthorized"}, status_code=401)
        body: Mapping[str, object] = {}
        if request.method in {"POST", "PUT", "PATCH"}:
            chunks: list[bytes] = []
            raw = b""
            async for chunk in request.stream():
                chunks.append(cast(bytes, chunk))
                try:
                    raw = limited_body(chunks)
                except ValueError as extra:
                    return json_response({"error": str(extra)}, status_code=413)
            if raw:
                try:
                    parsed = json.loads(raw)
                except json.JSONDecodeError:
                    return json_response({"error": "invalid JSON"}, status_code=400)
                if not isinstance(parsed, dict):
                    return json_response({"error": "JSON object required"}, status_code=400)
                body = cast(dict[str, object], parsed)
        query = dict(request.query_params)
        path = request.url.path
        method = request.method
        status, payload = await asyncio.to_thread(
            dispatch,
            mem,
            method,
            path,
            query=query,
            body=body,
            agent_id=agent_id,
            namespace=namespace,
        )
        return json_response(payload, status_code=status)

    for method, route in ROUTES:
        app.add_api_route(route, handle, methods=[method])
    return app


def run_http(
    mem: Memory,
    *,
    host: str,
    port: int,
    agent_id: str = "",
    namespace: str = "default",
    token: str | None = None,
) -> None:
    uvicorn = _load("uvicorn", "run")
    uvicorn(
        create_app(mem, agent_id=agent_id, namespace=namespace, token=token),
        host=host,
        port=port,
    )


def _tool(
    mem: Memory,
    name: str,
    arguments: Mapping[str, object],
    *,
    agent_id: str,
    namespace: str,
) -> dict[str, object]:
    raw = json.loads(call_tool(mem, name, arguments, agent_id=agent_id, namespace=namespace))
    if not isinstance(raw, dict):
        raise ValueError("tool returned a non-object")
    return cast(dict[str, object], raw)


def limited_body(
    chunks: Iterable[bytes],
    *,
    limit: int = MAX_BODY_BYTES,
) -> bytes:
    """Join ``chunks`` or raise if the total exceeds ``limit``."""
    parts: list[bytes] = []
    total = 0
    for chunk in chunks:
        total += len(chunk)
        if total > limit:
            raise ValueError("request body too large")
        parts.append(chunk)
    return b"".join(parts)


def _scope_user(method: str, path: str) -> str | None:
    prefix = "/v1/scopes/"
    if method != "DELETE" or not path.startswith(prefix):
        return None
    user_id = path.removeprefix(prefix)
    if not user_id or "/" in user_id:
        return None
    return user_id


def _load(module_name: str, attr: str) -> Any:
    try:
        module = importlib.import_module(module_name)
    except ImportError as exc:
        raise RuntimeError(_MISSING_EXTRA) from exc
    value = getattr(module, attr, None)
    if value is None:
        raise RuntimeError(_MISSING_EXTRA)
    return value

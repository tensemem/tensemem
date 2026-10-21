"""HTTP adapter: add, context, state, history, forget (ADR 0011)."""

from __future__ import annotations

import asyncio
import importlib
import json
import os
import sys
import time
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any, Final, cast

from tensemem.auth import bind_warning, health_path
from tensemem.core.errors import UnknownFactError, UnknownJobError
from tensemem.eval.hosted import hosted_secret_status
from tensemem.mcp import call_tool, seed_starter
from tensemem.memory import Memory
from tensemem.ops import allow_request, handle_ops, log_request, provider_settings, set_provider
from tensemem.providers.llm.fake import FakeExtractor
from tensemem.studio_http import handle_inspect

_MISSING_EXTRA = "tensemem serve needs tensemem[server]"
_DEFAULT_HOST = "127.0.0.1"
_DEFAULT_PORT = 8080
MAX_BODY_BYTES = 65_536
ROUTES: Final[tuple[tuple[str, str], ...]] = (
    ("POST", "/v1/memories:add"),
    ("POST", "/v1/context"),
    ("GET", "/v1/state"),
    ("GET", "/v1/history"),
    ("GET", "/v1/scopes"),
    ("GET", "/v1/stats"),
    ("GET", "/v1/jobs"),
    ("POST", "/v1/jobs:retry"),
    ("POST", "/v1/jobs:dismiss"),
    ("GET", "/v1/explain"),
    ("GET", "/v1/search"),
    ("GET", "/v1/graph"),
    ("POST", "/v1/facts:correct"),
    ("POST", "/v1/insights/compare"),
    ("POST", "/v1/insights/echo"),
    ("GET", "/v1/insights/act-risk"),
    ("POST", "/v1/studio/sample"),
    ("GET", "/v1/ops/keys"),
    ("POST", "/v1/ops/keys"),
    ("POST", "/v1/ops/keys:revoke"),
    ("GET", "/v1/ops/requests"),
    ("GET", "/v1/ops/provider"),
    ("PUT", "/v1/ops/provider"),
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
        ops = handle_ops(mem, verb, route, query=params, body=payload)
        if ops is not None:
            return ops
        inspected = handle_inspect(
            mem,
            verb,
            route,
            query=params,
            body=payload,
            agent_id=agent_id,
            namespace=namespace,
        )
        if inspected is not None:
            return inspected
        forgotten = _scope_user(verb, route)
        if forgotten is not None:
            return 200, _tool(
                mem,
                "forget",
                {"user_id": forgotten},
                agent_id=agent_id,
                namespace=namespace,
            )
    except (UnknownFactError, UnknownJobError) as extra:
        return 404, {"error": str(extra)}
    except TimeoutError as extra:
        llm = str(provider_settings(mem).get("llm") or "fake")
        credentials = hosted_secret_status(llm)
        print(f"tensemem serve: {extra}", file=sys.stderr)
        print(
            f"tensemem serve: llm={llm} key_ok={bool(credentials.get('ok'))}",
            file=sys.stderr,
        )
        return 504, {"error": str(extra), "credentials": credentials}
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
        settings = provider_settings(mem)
        llm = (os.environ.get("TENSEMEM_LLM") or "").strip() or str(settings["llm"])
        if llm != "fake" or str(settings["embedder"]) != "none":
            set_provider(mem, llm=llm, embedder=str(settings["embedder"]))
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
    request_type = _load("fastapi", "Request")
    app = fastapi(title="TenseMem", version="0.0.1")

    async def handle(request: Any) -> Any:
        authorization = request.headers.get("authorization")
        path = request.url.path
        method = request.method
        if not health_path(path) and not await asyncio.to_thread(
            allow_request, mem, authorization, token
        ):
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
        started = time.monotonic()
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
        if str(path).startswith("/v1/"):
            await asyncio.to_thread(
                log_request,
                mem,
                method=method,
                path=str(path),
                status=status,
                latency_ms=int((time.monotonic() - started) * 1000),
                authorization=authorization,
                bootstrap=token,
            )
        return json_response(payload, status_code=status)

    # from __future__ import annotations stores "Any"; FastAPI needs the Request class.
    handle.__annotations__["request"] = request_type
    for method, route in ROUTES:
        app.add_api_route(route, handle, methods=[method])
    app.add_api_route("/v1/{rest:path}", handle, methods=["GET", "POST", "PUT", "DELETE"])
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

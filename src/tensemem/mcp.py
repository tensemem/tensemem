"""MCP server: stdio or Streamable HTTP (ADR 0010 / 0015)."""

from __future__ import annotations

import importlib
import json
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Final

from tensemem.auth import bind_warning, wrap_bearer
from tensemem.core.models import Cardinality, Freshness, PredicateSpec
from tensemem.core.ontology import Ontology
from tensemem.memory import Memory
from tensemem.providers.llm.fake import FakeExtractor

_DEFAULT_HTTP_HOST = "127.0.0.1"
_DEFAULT_HTTP_PORT = 8081

TOOL_NAMES: Final[tuple[str, ...]] = (
    "remember",
    "recall_context",
    "get_state",
    "get_history",
    "forget",
)

_MISSING_EXTRA = "tensemem mcp needs tensemem[mcp]"

_STARTER = Ontology(
    predicates=(
        PredicateSpec(name="lives_in", cardinality=Cardinality.ONE),
        PredicateSpec(name="uses_language", cardinality=Cardinality.MANY),
        PredicateSpec(name="diet", cardinality=Cardinality.ONE),
        PredicateSpec(name="works_at", cardinality=Cardinality.ONE),
        PredicateSpec(name="job_title", cardinality=Cardinality.ONE),
        PredicateSpec(name="uses_tool", cardinality=Cardinality.MANY),
        PredicateSpec(name="allergic_to", cardinality=Cardinality.MANY),
        PredicateSpec(name="prefers", cardinality=Cardinality.MANY),
        PredicateSpec(name="name", cardinality=Cardinality.ONE),
        PredicateSpec(name="timezone", cardinality=Cardinality.ONE),
        PredicateSpec(name="pet", cardinality=Cardinality.MANY),
    )
)


def call_tool(
    mem: Memory,
    name: str,
    arguments: Mapping[str, object] | None = None,
    *,
    default_user: str = "",
    agent_id: str = "",
    namespace: str = "default",
) -> str:
    """Run one MCP tool against an open ``Memory`` and return JSON text."""
    payload = arguments or {}
    if name == "remember":
        result = _remember(
            mem, payload, default_user=default_user, agent_id=agent_id, namespace=namespace
        )
    elif name == "recall_context":
        result = _recall(
            mem, payload, default_user=default_user, agent_id=agent_id, namespace=namespace
        )
    elif name == "get_state":
        result = _state(
            mem, payload, default_user=default_user, agent_id=agent_id, namespace=namespace
        )
    elif name == "get_history":
        result = _history(
            mem, payload, default_user=default_user, agent_id=agent_id, namespace=namespace
        )
    elif name == "forget":
        result = _forget(
            mem, payload, default_user=default_user, agent_id=agent_id, namespace=namespace
        )
    else:
        raise ValueError(f"unknown tool: {name}")
    return json.dumps(result, default=str)


def serve(
    path: str | Path = "tensemem.db",
    *,
    default_user: str = "",
    agent_id: str = "",
    namespace: str = "default",
    http: bool = False,
    host: str = _DEFAULT_HTTP_HOST,
    port: int = _DEFAULT_HTTP_PORT,
    token: str | None = None,
) -> None:
    """Open ``path`` and serve the five tools until the host exits.

    Default transport is stdio. ``http=True`` is Streamable HTTP on ``host:port``.
    The extract worker stays off so queued jobs from another process are not
    claimed by ``FakeExtractor``. ``remember`` still waits in the tool call.
    """
    if http and (port < 1 or port > 65535):
        raise ValueError("port must be between 1 and 65535")
    warning = bind_warning(host, token) if http else None
    if warning:
        print(f"tensemem mcp --http: {warning}", file=sys.stderr)
    with Memory(path, llm=FakeExtractor(), start_worker=False) as mem:
        seed_starter(mem)
        if http:
            run_http(
                mem,
                host=host,
                port=port,
                default_user=default_user,
                agent_id=agent_id,
                namespace=namespace,
                token=token,
            )
            return
        run_stdio(mem, default_user=default_user, agent_id=agent_id, namespace=namespace)


def seed_starter(mem: Memory) -> None:
    """Register FakeExtractor predicates so remember works on a fresh file."""
    mem.seed(_STARTER)


def run_stdio(
    mem: Memory,
    *,
    default_user: str = "",
    agent_id: str = "",
    namespace: str = "default",
) -> None:
    app = bind_server(mem, default_user=default_user, agent_id=agent_id, namespace=namespace)
    app.run()


def run_http(
    mem: Memory,
    *,
    host: str,
    port: int,
    default_user: str = "",
    agent_id: str = "",
    namespace: str = "default",
    token: str | None = None,
) -> None:
    uvicorn = _load_uvicorn()
    app = bind_http_app(
        mem,
        host=host,
        port=port,
        default_user=default_user,
        agent_id=agent_id,
        namespace=namespace,
        token=token,
    )
    uvicorn(app, host=host, port=port)


def bind_http_app(
    mem: Memory,
    *,
    host: str = _DEFAULT_HTTP_HOST,
    port: int = _DEFAULT_HTTP_PORT,
    default_user: str = "",
    agent_id: str = "",
    namespace: str = "default",
    token: str | None = None,
) -> Any:
    """Streamable HTTP ASGI app. Optional bearer wrap; SDK import stays here."""
    server = bind_server(
        mem,
        default_user=default_user,
        agent_id=agent_id,
        namespace=namespace,
        host=host,
        port=port,
    )
    builder = getattr(server, "streamable_http_app", None)
    if builder is None:
        raise RuntimeError(_MISSING_EXTRA)
    return wrap_bearer(builder(), token)


def bind_server(
    mem: Memory,
    *,
    default_user: str = "",
    agent_id: str = "",
    namespace: str = "default",
    host: str = _DEFAULT_HTTP_HOST,
    port: int = _DEFAULT_HTTP_PORT,
) -> Any:
    """Register tools on an SDK server. Import happens here so the extra stays optional."""
    app = _new_server(host=host, port=port)

    def invoke(name: str, arguments: Mapping[str, object]) -> str:
        return call_tool(
            mem,
            name,
            arguments,
            default_user=default_user,
            agent_id=agent_id,
            namespace=namespace,
        )

    @app.tool()
    def remember(text: str, user_id: str = "") -> str:
        """Ingest a user message. The engine extracts facts; this tool does not edit slots."""
        return invoke("remember", {"text": text, "user_id": user_id})

    @app.tool()
    def recall_context(query: str = "", user_id: str = "", max_tokens: int = 300) -> str:
        """Packed, fenced context for this user, with freshness on the snapshot."""
        return invoke(
            "recall_context",
            {"query": query, "user_id": user_id, "max_tokens": max_tokens},
        )

    @app.tool()
    def get_state(user_id: str = "") -> str:
        """ACTIVE facts and freshness for this user."""
        return invoke("get_state", {"user_id": user_id})

    @app.tool()
    def get_history(user_id: str = "", predicate: str = "") -> str:
        """ACTIVE, SUPERSEDED, and RETRACTED facts; pass predicate to narrow the chain."""
        return invoke("get_history", {"user_id": user_id, "predicate": predicate})

    @app.tool()
    def forget(user_id: str = "") -> str:
        """Permanently delete this user's scope (facts, episodes, jobs)."""
        return invoke("forget", {"user_id": user_id})

    return app


def _new_server(*, host: str = _DEFAULT_HTTP_HOST, port: int = _DEFAULT_HTTP_PORT) -> Any:
    for module_name, class_name in (
        ("mcp.server.fastmcp", "FastMCP"),
        ("mcp.server", "MCPServer"),
    ):
        try:
            module = importlib.import_module(module_name)
        except ImportError:
            continue
        cls = getattr(module, class_name, None)
        if cls is None:
            continue
        try:
            return cls("tensemem", host=host, port=port)
        except TypeError:
            return cls("tensemem")
    raise RuntimeError(_MISSING_EXTRA)


def _load_uvicorn() -> Any:
    try:
        module = importlib.import_module("uvicorn")
    except ImportError as exc:
        raise RuntimeError(_MISSING_EXTRA) from exc
    run = getattr(module, "run", None)
    if run is None:
        raise RuntimeError(_MISSING_EXTRA)
    return run


def _remember(
    mem: Memory,
    arguments: Mapping[str, object],
    *,
    default_user: str,
    agent_id: str,
    namespace: str,
) -> dict[str, object]:
    user_id = _user(arguments, default_user)
    text = str(arguments.get("text") or "").strip()
    if not text:
        raise ValueError("text is required")
    added = mem.add(
        user_id,
        text,
        wait=mem.has_provider(),
        agent_id=agent_id,
        namespace=namespace,
    )
    state = mem.state(user_id, agent_id=agent_id, namespace=namespace)
    return {
        "seq": added.seq,
        "episode_ids": list(added.episode_ids),
        "job_id": added.job_id,
        "values": _values(state.values),
        "freshness": _freshness(state.freshness),
    }


def _recall(
    mem: Memory,
    arguments: Mapping[str, object],
    *,
    default_user: str,
    agent_id: str,
    namespace: str,
) -> dict[str, object]:
    user_id = _user(arguments, default_user)
    query = str(arguments.get("query") or "")
    packed = mem.context(
        user_id,
        query,
        max_tokens=_int(arguments, "max_tokens", 300),
        agent_id=agent_id,
        namespace=namespace,
    )
    return {
        "text": packed.text,
        "facts_used": list(packed.facts_used),
        "token_count": packed.token_count,
        "freshness": _freshness(packed.freshness),
    }


def _state(
    mem: Memory,
    arguments: Mapping[str, object],
    *,
    default_user: str,
    agent_id: str,
    namespace: str,
) -> dict[str, object]:
    user_id = _user(arguments, default_user)
    state = mem.state(user_id, agent_id=agent_id, namespace=namespace)
    return {
        "values": _values(state.values),
        "facts": [fact.model_dump(mode="json") for fact in state.facts],
        "freshness": _freshness(state.freshness),
    }


def _history(
    mem: Memory,
    arguments: Mapping[str, object],
    *,
    default_user: str,
    agent_id: str,
    namespace: str,
) -> dict[str, object]:
    user_id = _user(arguments, default_user)
    predicate = str(arguments.get("predicate") or "").strip() or None
    history = mem.history(user_id, predicate, agent_id=agent_id, namespace=namespace)
    return {
        "facts": [fact.model_dump(mode="json") for fact in history.facts],
        "freshness": _freshness(history.freshness),
    }


def _forget(
    mem: Memory,
    arguments: Mapping[str, object],
    *,
    default_user: str,
    agent_id: str,
    namespace: str,
) -> dict[str, object]:
    user_id = _user(arguments, default_user)
    mem.forget(user_id, agent_id=agent_id, namespace=namespace)
    return {"forgotten": user_id}


def _user(arguments: Mapping[str, object], default_user: str) -> str:
    user_id = str(arguments.get("user_id") or default_user).strip()
    if not user_id:
        raise ValueError("user_id is required")
    return user_id


def _int(arguments: Mapping[str, object], key: str, default: int) -> int:
    raw = arguments.get(key, default)
    if raw is None or raw == "":
        return default
    if isinstance(raw, bool) or not isinstance(raw, int | float | str):
        raise ValueError(f"{key} must be an integer")
    return int(raw)


def _freshness(fresh: Freshness) -> dict[str, object]:
    data: dict[str, object] = dict(fresh.model_dump(mode="json"))
    data["is_current"] = fresh.is_current
    return data


def _values(values: Mapping[str, str | tuple[str, ...]]) -> dict[str, object]:
    out: dict[str, object] = {}
    for key, value in values.items():
        out[key] = list(value) if isinstance(value, tuple) else value
    return out

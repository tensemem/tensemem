"""Inspect and insight HTTP handlers for Studio (ADR 0018)."""

from __future__ import annotations

from collections.abc import Mapping

from tensemem.core.errors import UnknownFactError, UnknownJobError
from tensemem.core.models import Freshness
from tensemem.insights import act_risk, compare, echo, seed_sample
from tensemem.memory import Memory


def handle_inspect(
    mem: Memory,
    method: str,
    path: str,
    *,
    query: Mapping[str, object],
    body: Mapping[str, object],
    agent_id: str,
    namespace: str,
) -> tuple[int, dict[str, object]] | None:
    """Handle Studio inspect/insight routes, or return None if unmatched."""
    verb = method.upper()
    route = path.rstrip("/") or "/"
    params = dict(query)
    payload = dict(body)
    agent = str(payload.get("agent_id") or params.get("agent_id") or agent_id)
    ns = str(payload.get("namespace") or params.get("namespace") or namespace)
    try:
        if verb == "GET" and route == "/v1/scopes":
            return 200, {
                "scopes": [
                    {
                        "user_id": scope.key.user_id,
                        "agent_id": scope.key.agent_id,
                        "namespace": scope.key.namespace,
                        "applied_seq": scope.applied_seq,
                    }
                    for scope in mem.scopes(namespace=ns)
                ]
            }
        if verb == "GET" and route == "/v1/stats":
            user = str(params.get("user_id") or "").strip() or None
            stats = mem.stats(user, agent_id=agent, namespace=ns)
            return 200, stats.model_dump(mode="json")
        if verb == "GET" and route == "/v1/jobs":
            user = str(params.get("user_id") or "").strip() or None
            jobs = mem.jobs(user, agent_id=agent, namespace=ns)
            return 200, {"jobs": [job.model_dump(mode="json") for job in jobs]}
        if verb == "POST" and route == "/v1/jobs:retry":
            job = mem.retry_job(_id(payload, "id", "job_id"))
            return 200, job.model_dump(mode="json")
        if verb == "POST" and route == "/v1/jobs:dismiss":
            job = mem.dismiss_job(_id(payload, "id", "job_id"))
            return 200, job.model_dump(mode="json")
        if verb == "GET" and route == "/v1/explain":
            result = mem.explain(_id(params, "fact_id", "id"))
            return 200, result.model_dump(mode="json")
        if verb == "GET" and route == "/v1/search":
            user = _user(params, "")
            found = mem.search(
                user,
                str(params.get("query") or ""),
                limit=_int(params, "limit", 10),
                agent_id=agent,
                namespace=ns,
            )
            return 200, {
                "hits": [hit.model_dump(mode="json") for hit in found.hits],
                "freshness": _freshness(found.freshness),
                "debug": [item.model_dump(mode="json") for item in found.debug],
            }
        if verb == "GET" and route == "/v1/graph":
            user = _user(params, "")
            return 200, mem.graph(user, agent_id=agent, namespace=ns)
        if verb == "POST" and route == "/v1/facts:correct":
            result = mem.correct(
                _id(payload, "fact_id", "id"),
                replacement=_opt(payload, "replacement"),
                note=_opt(payload, "note"),
            )
            return 200, result.model_dump(mode="json")
        if verb == "POST" and route == "/v1/insights/compare":
            user = _user(payload, "")
            return 200, compare(
                mem,
                user,
                str(payload.get("query") or ""),
                agent_id=agent,
                namespace=ns,
                include_history=_flag(payload, "include_history"),
            )
        if verb == "POST" and route == "/v1/insights/echo":
            user = _user(payload, "")
            return 200, echo(
                mem,
                user,
                turns=_int(payload, "turns", 8),
                query=str(payload.get("query") or ""),
                agent_id=agent,
                namespace=ns,
            )
        if verb == "GET" and route == "/v1/insights/act-risk":
            user = _user(params, "")
            return 200, act_risk(mem, user, agent_id=agent, namespace=ns)
        if verb == "POST" and route == "/v1/studio/sample":
            user = str(payload.get("user_id") or "studio-demo").strip() or "studio-demo"
            return 200, seed_sample(mem, user_id=user)
    except (UnknownFactError, UnknownJobError) as extra:
        return 404, {"error": str(extra)}
    except ValueError as extra:
        return 400, {"error": str(extra)}
    return None


def _id(payload: Mapping[str, object], *keys: str) -> str:
    for key in keys:
        value = str(payload.get(key) or "").strip()
        if value:
            return value
    raise ValueError("id is required")


def _opt(payload: Mapping[str, object], key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _flag(payload: Mapping[str, object], key: str) -> bool:
    raw = payload.get(key, False)
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, str):
        return raw.strip().casefold() in {"1", "true", "yes"}
    return bool(raw)


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

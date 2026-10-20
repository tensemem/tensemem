"""LangGraph-facing store: put/search map to add/context (ADR 0014)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from pydantic import BaseModel, ConfigDict

from tensemem.core.models import Freshness
from tensemem.memory import Memory

CONTEXT_KEY = "context"
STATE_KEY = "state"
SCOPE_KEY = "scope"
_TEXT_FIELDS = ("text", "content", "memory")


class StoreItem(BaseModel):
    """One store row. Compatible with LangGraph ``Item`` field names."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    namespace: tuple[str, ...]
    key: str
    value: dict[str, Any]


class TenseMemStore:
    """Thin store over one ``Memory``. ``put`` ingests text; it does not SET slots."""

    def __init__(
        self,
        mem: Memory,
        *,
        namespace: str = "default",
        wait: bool = True,
    ) -> None:
        self.mem = mem
        self.namespace = namespace
        self.wait = wait

    def put(
        self,
        namespace: Sequence[str],
        key: str,
        value: Mapping[str, object],
        **_: object,
    ) -> None:
        del key
        user_id, agent_id = _user_agent(namespace)
        self.mem.add(
            user_id,
            _text(value),
            wait=self.wait and self.mem.has_provider(),
            agent_id=agent_id,
            namespace=self.namespace,
        )

    def search(
        self,
        namespace: Sequence[str],
        /,
        *,
        query: str | None = None,
        limit: int = 10,
        offset: int = 0,
        **_: object,
    ) -> list[StoreItem]:
        user_id, agent_id = _user_agent(namespace)
        packed = self.mem.context(
            user_id,
            query or "",
            agent_id=agent_id,
            namespace=self.namespace,
        )
        item = StoreItem(
            namespace=tuple(namespace),
            key=CONTEXT_KEY,
            value={
                "text": packed.text,
                "facts_used": list(packed.facts_used),
                "token_count": packed.token_count,
                "freshness": _freshness(packed.freshness),
            },
        )
        return [item][offset : offset + max(limit, 0)]

    def get(self, namespace: Sequence[str], key: str, **_: object) -> StoreItem | None:
        user_id, agent_id = _user_agent(namespace)
        if key == CONTEXT_KEY:
            hits = self.search(namespace)
            return hits[0] if hits else None
        if key != STATE_KEY:
            return None
        state = self.mem.state(user_id, agent_id=agent_id, namespace=self.namespace)
        return StoreItem(
            namespace=tuple(namespace),
            key=STATE_KEY,
            value={
                "values": _values(state.values),
                "freshness": _freshness(state.freshness),
            },
        )

    def delete(self, namespace: Sequence[str], key: str, **_: object) -> None:
        if key != SCOPE_KEY:
            raise ValueError("delete only accepts key 'scope'")
        user_id, agent_id = _user_agent(namespace)
        self.mem.forget(user_id, agent_id=agent_id, namespace=self.namespace)


def _user_agent(namespace: Sequence[str]) -> tuple[str, str]:
    if not namespace:
        raise ValueError("namespace[0] is user_id")
    user_id = str(namespace[0]).strip()
    if not user_id:
        raise ValueError("namespace[0] is user_id")
    agent_id = str(namespace[1]).strip() if len(namespace) > 1 else ""
    return user_id, agent_id


def _text(value: Mapping[str, object]) -> str:
    for field in _TEXT_FIELDS:
        raw = value.get(field)
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
    raise ValueError("value.text (or content/memory) is required")


def _freshness(fresh: Freshness) -> dict[str, object]:
    data: dict[str, object] = dict(fresh.model_dump(mode="json"))
    data["is_current"] = fresh.is_current
    return data


def _values(values: Mapping[str, str | tuple[str, ...]]) -> dict[str, object]:
    out: dict[str, object] = {}
    for key, value in values.items():
        out[key] = list(value) if isinstance(value, tuple) else value
    return out

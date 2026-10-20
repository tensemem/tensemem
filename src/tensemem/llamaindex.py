"""LlamaIndex-facing chat memory: put/get map to add/context (ADR 0017)."""

from __future__ import annotations

import asyncio

from tensemem.core.models import ContextResult
from tensemem.memory import Memory


class TenseMemChatMemory:
    """Thin chat memory over one ``Memory``. ``put`` ingests text; it does not SET slots.

    Sync and async verbs are for direct calls. This class does not subclass a
    framework memory ABC.
    """

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

    def put(self, user_id: str, text: str, *, agent_id: str = "") -> None:
        content = text.strip()
        if not content:
            raise ValueError("text is required")
        if not user_id.strip():
            raise ValueError("user_id is required")
        self.mem.add(
            user_id.strip(),
            content,
            wait=self.wait and self.mem.has_provider(),
            agent_id=agent_id,
            namespace=self.namespace,
        )

    def get(self, user_id: str, query: str = "", *, agent_id: str = "") -> ContextResult:
        if not user_id.strip():
            raise ValueError("user_id is required")
        return self.mem.context(
            user_id.strip(),
            query,
            agent_id=agent_id,
            namespace=self.namespace,
        )

    async def aput(self, user_id: str, text: str, *, agent_id: str = "") -> None:
        await asyncio.to_thread(self.put, user_id, text, agent_id=agent_id)

    async def aget(self, user_id: str, query: str = "", *, agent_id: str = "") -> ContextResult:
        return await asyncio.to_thread(self.get, user_id, query, agent_id=agent_id)

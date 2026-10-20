import asyncio

import pytest

from tensemem import FakeExtractor, Memory
from tensemem.llamaindex import TenseMemChatMemory
from tensemem.mcp import seed_starter


def test_put_get_and_async() -> None:
    with Memory(":memory:", llm=FakeExtractor(), start_worker=False) as mem:
        seed_starter(mem)
        chat = TenseMemChatMemory(mem)
        chat.put("u1", "I live in Pune")
        ctx = chat.get("u1", "where do I live")
        assert "Pune" in ctx.text
        assert ctx.freshness.is_current is True
        asyncio.run(_async_put_get(chat))


async def _async_put_get(chat: TenseMemChatMemory) -> None:
    await chat.aput("u2", "I live in London")
    ctx = await chat.aget("u2", "where do I live")
    assert "London" in ctx.text


def test_put_rejects_empty() -> None:
    with Memory(":memory:", llm=FakeExtractor(), start_worker=False) as mem:
        seed_starter(mem)
        chat = TenseMemChatMemory(mem)
        with pytest.raises(ValueError, match="text"):
            chat.put("u1", "  ")
        with pytest.raises(ValueError, match="user_id"):
            chat.put("  ", "I live in Pune")

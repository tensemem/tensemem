import asyncio
from datetime import UTC, datetime

from tensemem import AsyncMemory, FakeExtractor
from tensemem.core.clock import FrozenClock


def test_async_add_wait_and_context() -> None:
    asyncio.run(_run())


async def _run() -> None:
    clock = FrozenClock(datetime(2026, 10, 18, 11, 0, 0, tzinfo=UTC))
    async with AsyncMemory(":memory:", clock=clock, llm=FakeExtractor()) as mem:
        await mem.register_predicate("lives_in")
        added = await mem.add("u1", "I live in Delhi")
        ctx = await mem.context("u1", min_seq=added.seq, wait=2.0)
        state = await mem.state("u1")
        assert state.values == {"lives_in": "Delhi"}
        assert "Delhi" in ctx.text
        assert ctx.freshness.is_current

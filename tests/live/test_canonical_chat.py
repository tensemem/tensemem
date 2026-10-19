"""End-to-end extract on a real model. Default pytest skips this module."""

from __future__ import annotations

import os

import pytest

from tensemem import Memory
from tensemem.core.models import Cardinality, FactStatus, JobStatus
from tensemem.providers.llm import OpenAIProvider

pytestmark = pytest.mark.live

_TIMEOUT = 90.0


def test_delhi_then_bangalore_and_rust() -> None:
    provider = _live_openai()
    with Memory(":memory:", llm=provider) as mem:
        mem.register_predicate("lives_in")
        mem.register_predicate("uses_language", cardinality=Cardinality.MANY)

        mem.add("u1", "I live in Delhi", wait=True, timeout=_TIMEOUT)
        assert mem.state("u1").values == {"lives_in": "Delhi"}

        mem.add(
            "u1",
            "I moved to Bangalore last week and now only write Rust.",
            wait=True,
            timeout=_TIMEOUT,
        )
        assert mem.state("u1").values == {
            "lives_in": "Bangalore",
            "uses_language": ("Rust",),
        }

        history = mem.history("u1", predicate="lives_in")
        assert [fact.object for fact in history.facts] == ["Delhi", "Bangalore"]
        assert [fact.status for fact in history.facts] == [
            FactStatus.SUPERSEDED,
            FactStatus.ACTIVE,
        ]
        assert all(job.status is JobStatus.DONE for job in mem.jobs("u1"))


def _live_openai() -> OpenAIProvider:
    if os.environ.get("TENSEMEM_LIVE") != "1":
        pytest.skip("set TENSEMEM_LIVE=1 to call a real model")
    if not os.environ.get("OPENAI_API_KEY", "").strip():
        pytest.skip("OPENAI_API_KEY is not set")
    return OpenAIProvider()

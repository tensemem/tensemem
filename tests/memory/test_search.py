from datetime import UTC, datetime

from tensemem import FakeEmbedder, FakeExtractor, Memory
from tensemem.core.clock import FrozenClock
from tensemem.core.models import Cardinality, ContextFormat, FactStatus


def test_search_and_context_prefer_the_matching_slot() -> None:
    with _memory() as mem:
        mem.register_predicate("lives_in")
        mem.register_predicate("diet")
        mem.set(user_id="u1", predicate="lives_in", value="Delhi")
        mem.set(user_id="u1", predicate="diet", value="vegetarian")
        mem.set(user_id="u1", predicate="lives_in", value="Bangalore")

        found = mem.search("u1", "where did I live")
        assert found.hits
        assert found.hits[0].predicate == "lives_in"
        assert "Bangalore" in found.hits[0].text

        ctx = mem.context("u1", "where did I live")
        assert "Bangalore" in ctx.text
        diet_before_city = ctx.text.find("vegetarian") < ctx.text.find("Bangalore")
        assert diet_before_city is False
        assert ctx.debug
        assert any(item.reason == "match" for item in ctx.debug)


def test_temporal_query_and_include_history_show_previous_city() -> None:
    with _memory() as mem:
        mem.register_predicate("lives_in")
        mem.set(user_id="u1", predicate="lives_in", value="Delhi")
        mem.set(user_id="u1", predicate="lives_in", value="Bangalore")

        current = mem.context("u1", "where did I live")
        assert "Bangalore" in current.text
        assert "previously" not in current.text

        past = mem.context("u1", "where did I live before")
        assert "Bangalore" in past.text
        assert "Delhi" in past.text
        assert "previously" in past.text

        flagged = mem.context("u1", include_history=True)
        assert "Delhi" in flagged.text
        hits = mem.search("u1", "live").hits
        superseded = [hit for hit in hits if hit.status is FactStatus.SUPERSEDED]
        assert any(hit.text.endswith("Delhi") for hit in superseded)


def test_episodic_fallback_and_json_xml_debug() -> None:
    with _memory() as mem:
        mem.register_predicate("note")
        mem.set(user_id="u1", predicate="note", value="likes spicy food")
        mem.add("u1", "We picked the Koramangala place for the team dinner", wait=True)
        ctx = mem.context("u1", "what did I say about dinner", fence=False)
        assert "Possibly relevant past conversation" in ctx.text
        assert "Koramangala" in ctx.text
        assert any(item.kind == "episode" for item in ctx.debug)

        as_json = mem.context("u1", "spicy", fmt=ContextFormat.JSON, fence=False)
        assert '"predicate": "note"' in as_json.text
        as_xml = mem.context("u1", "spicy", fmt="xml", fence=False)
        assert "<fact " in as_xml.text
        assert "spicy food" in as_xml.text


def test_search_omits_unrelated_facts() -> None:
    with _memory() as mem:
        mem.register_predicate("lives_in")
        mem.set(user_id="u1", predicate="lives_in", value="Bangalore")
        found = mem.search("u1", "pizza")
        assert found.hits == ()


def test_embedder_failure_falls_back_to_fts() -> None:
    with _memory(embedder=_BoomEmbedder()) as mem:
        mem.register_predicate("lives_in")
        mem.set(user_id="u1", predicate="lives_in", value="Bangalore")
        ctx = mem.context("u1", "where did I live")
        assert "Bangalore" in ctx.text
        found = mem.search("u1", "live")
        assert found.hits
        assert found.hits[0].predicate == "lives_in"


def test_embedder_writes_vectors_and_boosts_search() -> None:
    with _memory(embedder=FakeEmbedder()) as mem:
        mem.register_predicate("lives_in")
        mem.register_predicate("uses_language", cardinality=Cardinality.MANY)
        mem.set(user_id="u1", predicate="lives_in", value="Bangalore")
        mem.add_value(user_id="u1", predicate="uses_language", value="Rust")
        mem.flush()

        found = mem.search("u1", "lives in Bangalore")
        assert found.hits[0].predicate == "lives_in"
        embed_jobs = [job for job in mem.jobs("u1") if job.kind.value == "embed"]
        assert embed_jobs
        assert all(job.status.value == "DONE" for job in embed_jobs)
        assert all(job.owner_kind == "fact" for job in embed_jobs)


def test_fact_embed_jobs_scrub_secrets() -> None:
    key = "sk-" + "Xi8tcNiHV9awbCcvilTe" + "T3BlbkFJ" + "3UDnpdEwNNm6wVBpYM0o"
    with _memory(embedder=FakeEmbedder()) as mem:
        mem.register_predicate("api_token")
        mem.set(user_id="u1", predicate="api_token", value=key)
        embed = next(job for job in mem.jobs("u1") if job.kind.value == "embed")
        assert key not in (embed.embed_text or "")
        assert "[REDACTED]" in (embed.embed_text or "")


class _BoomEmbedder:
    model = "boom"
    dim = 1

    def embed(self, texts: object) -> list[list[float]]:
        del texts
        raise RuntimeError("down")


def _memory(*, embedder: FakeEmbedder | _BoomEmbedder | None = None) -> Memory:
    clock = FrozenClock(datetime(2026, 10, 18, 11, 0, 0, tzinfo=UTC))
    return Memory(":memory:", clock=clock, llm=FakeExtractor(), embedder=embedder)

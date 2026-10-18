from tensemem.core.models import Cardinality, ExtractionResult
from tensemem.pipeline import (
    PROMPT_VERSION,
    CompactFact,
    ExtractSnapshot,
    RegistryEntry,
    extract,
    render_messages,
)
from tensemem.providers.llm import FakeExtractor


def test_render_includes_registry_facts_and_time() -> None:
    snapshot = ExtractSnapshot(
        reference_time="2026-10-18",
        registry=(
            RegistryEntry(
                name="lives_in",
                cardinality=Cardinality.ONE,
                description="city of residence",
            ),
        ),
        facts=(CompactFact(subject="user", predicate="lives_in", object="Delhi"),),
    )
    messages = render_messages(
        snapshot,
        [{"role": "user", "content": "I moved to Bangalore last week."}],
    )
    assert messages[0]["role"] == "system"
    system = messages[0]["content"]
    assert "2026-10-18" in system
    assert "lives_in (ONE): city of residence" in system
    assert "user lives_in Delhi" in system
    assert messages[-1]["content"] == "I moved to Bangalore last week."
    assert PROMPT_VERSION == "extract_v1"


def test_extract_uses_provider_on_rendered_prompt() -> None:
    snapshot = ExtractSnapshot(reference_time="2026-10-18")
    fake = FakeExtractor()
    result = extract(
        fake,
        snapshot,
        [{"role": "user", "content": "I moved to Bangalore and now only write Rust."}],
    )
    assert isinstance(result, ExtractionResult)
    assert [op.predicate for op in result.ops] == ["lives_in", "uses_language"]
    assert fake.calls[0][0]["role"] == "system"
    assert "REGISTRY" in fake.calls[0][0]["content"]

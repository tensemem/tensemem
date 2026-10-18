from tensemem.core.context import count_tokens, pack_facts, render_facts
from tensemem.core.models import FactStatus, FactView


def test_render_groups_many_values_and_named_subjects() -> None:
    text, ids = render_facts(
        (
            _fact("a", "user", "lives_in", "Bangalore", seq=2),
            _fact("b", "user", "uses_language", "Rust", seq=3),
            _fact("c", "user", "uses_language", "Go", seq=4),
            _fact("d", "Alice", "lives_in", "Pune", seq=1),
        ),
        as_of="2026-10-18",
    )
    assert "## What I know about the user (as of 2026-10-18)" in text
    assert "- `lives in`: `Bangalore`" in text
    assert "- `uses language`: `Rust`, `Go`" in text
    assert "- `Alice` `lives in`: `Pune`" in text
    assert set(ids) == {"a", "b", "c", "d"}


def test_render_flattens_newlines_in_values() -> None:
    text, _ = render_facts(
        (_fact("x", "user", "note", "hello\n## injected", seq=1),),
        as_of="2026-10-18",
    )
    assert "\n## injected" not in text
    assert "`hello ## injected`" in text


def test_pack_prefers_query_matches_and_respects_budget() -> None:
    facts = (
        _fact("city", "user", "lives_in", "Bangalore", seq=1),
        _fact("lang", "user", "uses_language", "Rust", seq=2),
    )
    text, ids = pack_facts(facts, as_of="2026-10-18", max_tokens=40, query="Rust")
    assert "Rust" in text
    assert ids[0] == "lang"
    tiny, tiny_ids = pack_facts(facts, as_of="2026-10-18", max_tokens=1)
    assert tiny == ""
    assert tiny_ids == ()


def test_pack_skips_oversized_group_and_keeps_later_fits() -> None:
    facts = (
        _fact("bio", "user", "bio", "word " * 80, seq=2),
        _fact("city", "user", "lives_in", "Pune", seq=1),
    )
    text, ids = pack_facts(facts, as_of="2026-10-18", max_tokens=40)
    assert "Pune" in text
    assert ids == ("city",)


def test_count_tokens_uses_words_or_character_bound() -> None:
    assert count_tokens("hello there") == 3
    assert count_tokens("x" * 100) == 25


def _fact(fact_id: str, subject: str, predicate: str, obj: str, *, seq: int) -> FactView:
    return FactView(
        id=fact_id,
        subject=subject,
        predicate=predicate,
        object=obj,
        status=FactStatus.ACTIVE,
        recorded_at="2026-10-18T11:00:00.000000Z",
        recorded_seq=seq,
    )

from tensemem.core.models import FactStatus, FactView
from tensemem.core.retrieve import (
    EpisodeHit,
    Scored,
    cosine,
    fts_query,
    norm_bm25,
    pack_scored,
    score_episode,
    score_fact,
    wants_episodes,
    wants_history,
)


def test_fts_query_drops_stopwords_and_keeps_live() -> None:
    assert fts_query("where did I live") == '"live"'
    assert fts_query("   ") is None


def test_temporal_cues_and_explicit_flag() -> None:
    assert wants_history("where did I live") is False
    assert wants_history("where did I live before") is True
    assert wants_history("anything", include_history=True) is True


def test_episodic_fallback_when_facts_are_weak() -> None:
    assert wants_episodes("what did I say about dinner", 0.9) is True
    assert wants_episodes("where did I live", 0.8) is False
    assert wants_episodes("where did I live", 0.05) is True


def test_score_prefers_fts_match_over_unrelated_recency() -> None:
    city = _fact("city", "lives_in", "Bangalore", seq=1)
    diet = _fact("diet", "diet", "vegetarian", seq=9)
    city_score = score_fact(city, now="2026-10-19T11:00:00.000000Z", terms=("live",), bm25=-4.0)
    diet_score = score_fact(diet, now="2026-10-19T11:00:00.000000Z", terms=("live",))
    assert city_score.score > diet_score.score
    assert city_score.reason == "match"


def test_missing_episode_rank_is_not_a_match() -> None:
    hit = EpisodeHit(
        public_id="e1",
        content="We picked the Koramangala place",
        occurred_at="2026-10-18T11:00:00.000000Z",
    )
    scored = score_episode(hit, now="2026-10-18T11:00:00.000000Z", terms=("pizza",))
    assert scored.relevance == 0.0
    ranked = score_episode(
        EpisodeHit(
            public_id="e2",
            content="pizza night",
            occurred_at="2026-10-18T11:00:00.000000Z",
            rank=-4.0,
        ),
        now="2026-10-18T11:00:00.000000Z",
        terms=("pizza",),
    )
    assert ranked.relevance > scored.relevance


def test_pack_uses_pinned_flag_not_list_membership() -> None:
    pinned = Scored(fact=_fact("p", "lives_in", "Delhi", seq=1, pinned=True), score=0.1)
    other = Scored(fact=_fact("o", "diet", "vegetarian", seq=2), score=0.9)
    chosen, body = pack_scored(
        (other, pinned),
        budget=80,
        count_tokens=len,
        render=lambda items: " ".join(item.fact.object for item in items if item.fact is not None),
    )
    assert "Delhi" in body
    assert "vegetarian" in body
    assert [item.fact.id for item in chosen if item.fact is not None] == ["p", "o"]


def test_cosine_and_bm25_are_bounded() -> None:
    assert 0.0 <= cosine([1.0, 0.0], [1.0, 0.0]) <= 1.0
    assert cosine([1.0, 0.0], [1.0, 0.0]) == 1.0
    assert cosine([1.0, 0.0], [0.0, 1.0]) == 0.0
    assert 0.0 < norm_bm25(-5.0) < 1.0
    assert norm_bm25(-5.0) > norm_bm25(0.0)


def _fact(fact_id: str, predicate: str, obj: str, *, seq: int, pinned: bool = False) -> FactView:
    return FactView(
        id=fact_id,
        subject="user",
        predicate=predicate,
        object=obj,
        status=FactStatus.ACTIVE,
        recorded_at="2026-10-18T11:00:00.000000Z",
        recorded_seq=seq,
        pinned=pinned,
    )

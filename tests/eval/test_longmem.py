import json
from importlib.resources import files
from pathlib import Path

from tensemem.eval.longmem import (
    default_items_path,
    format_report,
    load_items,
    run_longmem,
)


def test_packaged_pilot_covers_every_published_type() -> None:
    items = load_items()
    assert len(items) == 7
    assert {item.question_id for item in items} == {
        "lme-gst-state",
        "lme-hotel-confirm",
        "lme-meal-pref",
        "lme-gst-update",
        "lme-gst-before",
        "lme-inbox-sessions",
        "lme-no-bali_abs",
    }
    assert {item.question_type for item in items} >= {
        "single-session-user",
        "single-session-assistant",
        "single-session-preference",
        "temporal-reasoning",
        "knowledge-update",
        "multi-session",
    }
    assert any(item.abstention for item in items)
    blob = " ".join(
        turn.content for item in items for session in item.haystack_sessions for turn in session
    )
    assert "Delhi" not in blob
    assert "Bangalore" not in blob
    packed = files("tensemem.eval").joinpath("longmem_pilot.json")
    assert packed.is_file()
    assert default_items_path().name == "longmem_pilot.json"


def test_pilot_meets_category_slos() -> None:
    report = run_longmem()
    assert report.cases == 7
    assert report.accuracy == 1.0
    for name in (
        "single-session-user",
        "single-session-assistant",
        "single-session-preference",
        "temporal-reasoning",
        "knowledge-update",
        "multi-session",
        "abstention",
    ):
        score = report.by_type[name]
        assert score.n >= 1
        assert score.accuracy == 1.0
    text = format_report(report)
    assert "LongMemEval adapter" in text
    assert "knowledge-update:" in text
    assert "abstention:" in text


def test_load_jsonl_and_empty_answer(tmp_path: Path) -> None:
    path = tmp_path / "one.jsonl"
    path.write_text(
        json.dumps(
            {
                "question_id": "empty",
                "question_type": "single-session-user",
                "question": "what is filed",
                "answer": "",
                "haystack_sessions": [[{"role": "user", "content": "thanks"}]],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    items = load_items(path)
    assert len(items) == 1
    assert items[0].answer == ""
    report = run_longmem(path)
    assert report.ok == 0
    assert report.cases == 1

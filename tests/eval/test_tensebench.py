import json
from importlib.resources import files
from pathlib import Path

from tensemem.eval.tensebench import (
    default_scenarios_path,
    format_report,
    load_scenarios,
    run_suite,
)


def test_packaged_set_has_labeled_scenarios() -> None:
    cases = load_scenarios()
    assert len(cases) == 82
    assert len({case.id for case in cases}) == 82
    assert {case.category for case in cases} >= {
        "relocation",
        "language",
        "alias",
        "third_party",
        "hypothetical",
        "backfill",
        "correction",
        "echo",
        "freshness",
        "history",
        "paragraph",
    }
    packed = files("tensemem.eval").joinpath("tensebench_v1.jsonl")
    assert packed.is_file()
    path = default_scenarios_path()
    assert path.is_file()
    assert path.name == "tensebench_v1.jsonl"


def test_tensemem_meets_slo() -> None:
    report = run_suite()
    score = report.systems["tensemem"]
    assert report.cases == 82
    assert score.current_state_accuracy is not None
    assert score.stale_fact_leak_rate is not None
    assert score.freshness_honesty is not None
    assert score.contamination_rate is not None
    assert score.correction_durability is not None
    assert score.history_accuracy is not None
    assert score.current_state_accuracy >= 0.95
    assert score.stale_fact_leak_rate == 0.0
    assert score.freshness_honesty == 1.0
    assert score.contamination_rate == 0.0
    assert score.correction_durability == 1.0
    assert score.history_accuracy == 1.0
    assert score.honest_n >= 5
    assert score.echo_n >= 5
    assert score.durable_n >= 5
    assert score.leak_n >= 20


def test_paragraph_cases_are_natural_multi_predicate() -> None:
    cases = [case for case in load_scenarios() if case.category == "paragraph"]
    assert len(cases) == 12
    banned = ("Delhi", "Bangalore", "I live in", "I write Python")
    for case in cases:
        assert len(case.predicates) >= 2
        blob = " ".join(turn.text for turn in case.turns)
        assert all(token not in blob for token in banned)
        assert all(len(turn.text) >= 60 for turn in case.turns)
        assert all(turn.ops is not None for turn in case.turns)


def test_concat_leaks_stale_cities() -> None:
    report = run_suite(systems=("concat",))
    score = report.systems["concat"]
    assert score.stale_fact_leak_rate is not None
    assert score.current_state_accuracy is not None
    assert score.stale_fact_leak_rate > 0.0
    assert score.current_state_accuracy < 1.0
    assert score.freshness_honesty == 0.0
    assert score.contamination_rate is None
    assert score.correction_durability is None
    text = format_report(report)
    assert "n/a" in text


def test_concat_history_is_per_predicate(tmp_path: Path) -> None:
    path = tmp_path / "interleaved.jsonl"
    path.write_text(
        json.dumps(
            {
                "id": "interleaved",
                "category": "history",
                "predicates": [
                    {"name": "lives_in"},
                    {"name": "uses_language", "cardinality": "MANY"},
                ],
                "turns": [
                    {"text": "I live in Delhi"},
                    {"text": "I write Python"},
                    {"text": "I moved to Bangalore"},
                    {"text": "I write Go"},
                ],
                "query": "what do I know",
                "history": {
                    "lives_in": ["Delhi", "Bangalore"],
                    "uses_language": ["Python", "Go"],
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    score = run_suite(path, systems=("concat",)).systems["concat"]
    assert score.history_n == 1
    assert score.history_ok == 1

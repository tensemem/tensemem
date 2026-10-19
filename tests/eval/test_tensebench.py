from importlib.resources import files

from tensemem.eval.tensebench import (
    default_scenarios_path,
    format_report,
    load_scenarios,
    run_suite,
)


def test_pilot_has_thirty_labeled_scenarios() -> None:
    cases = load_scenarios()
    assert len(cases) == 30
    assert {case.category for case in cases} >= {
        "relocation",
        "language",
        "alias",
        "third_party",
        "hypothetical",
        "correction",
        "echo",
        "freshness",
        "history",
    }
    packed = files("tensemem.eval").joinpath("tensebench_v1.jsonl")
    assert packed.is_file()
    path = default_scenarios_path()
    assert path.is_file()
    assert path.name == "tensebench_v1.jsonl"


def test_tensemem_meets_pilot_slos() -> None:
    report = run_suite()
    score = report.systems["tensemem"]
    assert report.cases == 30
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
    assert score.honest_n >= 3
    assert score.echo_n >= 3
    assert score.durable_n >= 3
    assert score.leak_n >= 10


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

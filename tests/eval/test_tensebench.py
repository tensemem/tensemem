from pathlib import Path

from tensemem.eval.tensebench import default_scenarios_path, load_scenarios, run_suite

_V1 = Path(__file__).resolve().parents[2] / "benchmarks" / "tensebench" / "v1.jsonl"


def test_pilot_has_thirty_labeled_scenarios() -> None:
    cases = load_scenarios(_V1)
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
    assert default_scenarios_path() == _V1


def test_tensemem_meets_pilot_slos() -> None:
    report = run_suite(_V1)
    score = report.systems["tensemem"]
    assert report.cases == 30
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
    report = run_suite(_V1, systems=("concat",))
    score = report.systems["concat"]
    assert score.stale_fact_leak_rate > 0.0
    assert score.current_state_accuracy < 1.0
    assert score.freshness_honesty == 0.0

from tensemem.eval.latency import CI_FACTS, CI_P99_MS, format_report, run_latency


def test_context_latency_stays_under_ci_gate() -> None:
    report = run_latency(facts=CI_FACTS, rounds=20, warmup=4)
    assert report.facts == CI_FACTS
    assert report.rounds == 20
    assert report.p50_ms <= report.p99_ms <= report.max_ms
    assert report.p99_ms < CI_P99_MS


def test_latency_report_text_includes_targets() -> None:
    report = run_latency(facts=8, rounds=5, warmup=1)
    text = format_report(report)
    assert "p50_ms:" in text
    assert "target 2.0" in text
    assert "target 10.0" in text

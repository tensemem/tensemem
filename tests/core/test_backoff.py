from tensemem.core.backoff import backoff_seconds


def test_backoff_doubles_then_caps() -> None:
    assert backoff_seconds(1, jitter=1.0) == 1.0
    assert backoff_seconds(2, jitter=1.0) == 2.0
    assert backoff_seconds(3, jitter=1.0) == 4.0
    assert backoff_seconds(10, jitter=1.0) == 60.0
    assert backoff_seconds(3, jitter=0.5) == 2.0

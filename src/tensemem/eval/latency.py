"""Measure ``context()`` read latency with no query embedding (design §6.2)."""

from __future__ import annotations

import math
import time
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field

from tensemem.core.clock import FrozenClock
from tensemem.core.models import Cardinality
from tensemem.memory import Memory

TARGET_P50_MS = 2.0
TARGET_P99_MS = 10.0
CI_FACTS = 500
CI_P99_MS = 50.0
DEFAULT_FACTS = 5000
DEFAULT_ROUNDS = 80
_WARMUP = 8
_USER = "latency"


class LatencyReport(BaseModel):
    """Percentiles for empty-query ``context()`` over a seeded scope."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    facts: int = Field(ge=1)
    rounds: int = Field(ge=1)
    p50_ms: float = Field(ge=0.0)
    p99_ms: float = Field(ge=0.0)
    max_ms: float = Field(ge=0.0)
    target_p50_ms: float = TARGET_P50_MS
    target_p99_ms: float = TARGET_P99_MS


def run_latency(
    *,
    facts: int = DEFAULT_FACTS,
    rounds: int = DEFAULT_ROUNDS,
    warmup: int = _WARMUP,
) -> LatencyReport:
    """Seed ``facts`` ACTIVE values and time empty-query ``context()``."""
    if facts < 1 or rounds < 1:
        msg = "facts and rounds must be at least 1"
        raise ValueError(msg)
    clock = FrozenClock(datetime(2026, 10, 19, 12, 0, 0, tzinfo=UTC))
    samples: list[float] = []
    with Memory(":memory:", clock=clock, start_worker=False) as mem:
        mem.register_predicate("tag", cardinality=Cardinality.MANY)
        values = tuple(f"t{index:04d}" for index in range(facts))
        mem.replace_values(_USER, "tag", values)
        for _ in range(max(0, warmup)):
            mem.context(_USER)
        for _ in range(rounds):
            started = time.perf_counter()
            mem.context(_USER)
            samples.append((time.perf_counter() - started) * 1000.0)
    return LatencyReport(
        facts=facts,
        rounds=rounds,
        p50_ms=_percentile(samples, 0.50),
        p99_ms=_percentile(samples, 0.99),
        max_ms=max(samples),
    )


def format_report(report: LatencyReport) -> str:
    return "\n".join(
        (
            f"context() latency  facts: {report.facts}  rounds: {report.rounds}",
            f"  p50_ms: {report.p50_ms:.3f}  (target {report.target_p50_ms:.1f})",
            f"  p99_ms: {report.p99_ms:.3f}  (target {report.target_p99_ms:.1f})",
            f"  max_ms: {report.max_ms:.3f}",
        )
    )


def _percentile(samples: list[float], quantile: float) -> float:
    ordered = sorted(samples)
    rank = (len(ordered) - 1) * quantile
    low = math.floor(rank)
    high = math.ceil(rank)
    if low == high:
        return ordered[low]
    weight = rank - low
    return ordered[low] * (1.0 - weight) + ordered[high] * weight

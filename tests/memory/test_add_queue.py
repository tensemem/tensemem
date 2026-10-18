from datetime import UTC, datetime

from tensemem import Memory
from tensemem.core.clock import FrozenClock
from tensemem.core.models import Cardinality, JobStatus


def test_add_enqueues_and_reads_are_not_current() -> None:
    with _memory() as mem:
        result = mem.add("u1", "I live in Delhi")
        assert result.job_id is not None
        assert result.seq >= 1
        freshness = mem.state("u1").freshness
        assert freshness.pending == 1
        assert freshness.failed == 0
        assert freshness.is_current is False
        assert freshness.as_of_seq == 0
        assert freshness.latest_seq == result.seq
        jobs = mem.jobs("u1")
        assert len(jobs) == 1
        assert jobs[0].id == result.job_id
        assert jobs[0].status is JobStatus.QUEUED
        assert jobs[0].episode_id == result.seq


def test_scopes_do_not_share_jobs() -> None:
    with _memory() as mem:
        mem.add("u1", "one")
        mem.add("u2", "two")
        assert len(mem.jobs("u1")) == 1
        assert len(mem.jobs("u2")) == 1


def test_set_does_not_jump_watermark_past_pending_add() -> None:
    with _memory() as mem:
        mem.register_predicate("lives_in", cardinality=Cardinality.ONE)
        mem.add("u1", "I live in Delhi")
        mem.set(user_id="u1", predicate="lives_in", value="Bangalore")
        freshness = mem.state("u1").freshness
        assert freshness.pending == 1
        assert freshness.as_of_seq == 0
        assert freshness.is_current is False


def _memory() -> Memory:
    return Memory(":memory:", clock=FrozenClock(datetime(2026, 10, 18, 11, 0, 0, tzinfo=UTC)))

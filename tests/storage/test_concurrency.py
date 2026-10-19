from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

from tensemem import Memory
from tensemem.core.clock import FrozenClock
from tensemem.core.models import Cardinality, FactStatus


def test_eight_threads_two_handles_keep_one_active_slot(tmp_path: Path) -> None:
    path = tmp_path / "stress.db"
    clock = FrozenClock(datetime(2026, 10, 18, 11, 0, 0, tzinfo=UTC))
    with Memory(path, clock=clock) as setup:
        setup.register_predicate("lives_in")
        setup.register_predicate("uses_language", cardinality=Cardinality.MANY)

    mems = [Memory(path, clock=clock), Memory(path, clock=clock)]
    errors: list[BaseException] = []

    def work(index: int) -> None:
        try:
            handle = mems[index % 2]
            handle.set(user_id="u1", predicate="lives_in", value=f"City{index}")
            handle.add_value(user_id="u1", predicate="uses_language", value=f"Lang{index}")
        except BaseException as extra:
            errors.append(extra)

    try:
        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(work, range(24)))
        assert errors == []
        state = mems[0].state(user_id="u1")
        lives = [fact for fact in state.facts if fact.predicate == "lives_in"]
        langs = [fact for fact in state.facts if fact.predicate == "uses_language"]
        assert len(lives) == 1
        assert lives[0].status is FactStatus.ACTIVE
        assert len(langs) == 24
        history = mems[0].history(user_id="u1", predicate="lives_in")
        active = [fact for fact in history.facts if fact.status is FactStatus.ACTIVE]
        assert len(active) == 1
    finally:
        for mem in mems:
            mem.close()

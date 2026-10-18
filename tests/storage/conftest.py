from collections.abc import Iterator
from datetime import UTC, datetime

import pytest

from tensemem.core.clock import FrozenClock
from tensemem.storage.sqlite import SqliteDatabase


@pytest.fixture
def db() -> Iterator[SqliteDatabase]:
    clock = FrozenClock(datetime(2026, 10, 18, 9, 0, 0, tzinfo=UTC))
    with SqliteDatabase(":memory:", clock=clock, read_pool_size=1) as database:
        yield database

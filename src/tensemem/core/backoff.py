"""Retry delay for the durable job queue.

Full jitter: the next run is a random fraction of ``min(cap, base * 2^(attempt-1))``.
Tests pass a fixed ``jitter`` so times stay deterministic.
"""

from __future__ import annotations

MAX_ATTEMPTS = 6
BASE_SECONDS = 1.0
CAP_SECONDS = 60.0
LEASE_SECONDS = 60.0


def backoff_seconds(attempt: int, *, jitter: float = 1.0) -> float:
    """Seconds to wait after ``attempt`` failures (1-based)."""
    step = max(attempt, 1)
    window = min(CAP_SECONDS, BASE_SECONDS * (2 ** (step - 1)))
    return window * min(max(jitter, 0.0), 1.0)

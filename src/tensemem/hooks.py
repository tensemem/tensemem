"""App-facing event hooks. Failures in a hook never fail the engine call."""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping, Sequence

log = logging.getLogger("tensemem")

Hook = Callable[[str, Mapping[str, object]], None]
_LOG_SKIP = frozenset({"user_id", "error"})


def emit(
    hooks: Sequence[Hook],
    name: str,
    payload: Mapping[str, object],
) -> None:
    """Log ``name`` then call each hook. Hook exceptions are logged and ignored."""
    detail = " ".join(f"{key}={value}" for key, value in payload.items() if key not in _LOG_SKIP)
    log.info("event=%s %s", name, detail)
    for hook in hooks:
        try:
            hook(name, payload)
        except Exception:
            log.exception("hook failed event=%s", name)

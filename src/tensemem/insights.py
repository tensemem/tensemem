"""Studio insights: compare, echo, act-risk, sample workspace (ADR 0018)."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence

from tensemem.core.models import FactSet, FactStatus, Freshness, JobStatus
from tensemem.mcp import seed_starter
from tensemem.memory import Memory

_WORD = re.compile(r"[a-z0-9]+")

SAMPLE_USER = "studio-demo"

_SAMPLE = (
    (
        "For this GST cycle we file GSTR-1 from Maharashtra and the books are in Tally.",
        (("files_return", "GSTR-1"), ("gst_state", "Maharashtra"), ("uses_software", "Tally")),
    ),
    (
        "This month we file GSTR-3B from Maharashtra. Books stay in Tally.",
        (("files_return", "GSTR-3B"), ("gst_state", "Maharashtra"), ("uses_software", "Tally")),
    ),
    (
        "For the Singapore trip: hotel is Marina Bay, and I need vegetarian meals on the flights.",
        (
            ("trip_destination", "Singapore"),
            ("hotel", "Marina Bay"),
            ("meal_preference", "vegetarian"),
        ),
    ),
    (
        "Meal request changed to vegan. Hotel is still Marina Bay.",
        (
            ("trip_destination", "Singapore"),
            ("hotel", "Marina Bay"),
            ("meal_preference", "vegan"),
        ),
    ),
    (
        "On the Contoso PO: payment is net-30, bill in USD, ship to the Rotterdam warehouse.",
        (
            ("payment_terms", "net-30"),
            ("invoice_currency", "USD"),
            ("ship_to", "Rotterdam warehouse"),
        ),
    ),
    (
        "Contoso now wants EUR on the invoice. Terms stay net-30.",
        (
            ("payment_terms", "net-30"),
            ("invoice_currency", "EUR"),
            ("ship_to", "Rotterdam warehouse"),
        ),
    ),
)


def seed_sample(mem: Memory, *, user_id: str = SAMPLE_USER) -> dict[str, object]:
    """Load GST / itinerary / invoice turns. Does not run on serve start."""
    seed_starter(mem)
    for name in (
        "files_return",
        "gst_state",
        "uses_software",
        "trip_destination",
        "hotel",
        "meal_preference",
        "payment_terms",
        "invoice_currency",
        "ship_to",
    ):
        mem.register_predicate(name)
    for text, facts in _SAMPLE:
        mem.add(user_id, text, wait=mem.has_provider())
        for predicate, value in facts:
            mem.set(user_id, predicate, value)
    state = mem.state(user_id)
    return {
        "user_id": user_id,
        "values": _values(state.values),
        "freshness": _freshness(state.freshness),
    }


def compare(
    mem: Memory,
    user_id: str,
    query: str,
    *,
    agent_id: str = "",
    namespace: str = "default",
    include_history: bool = False,
) -> dict[str, object]:
    """Same query through context(), concat, and token-overlap."""
    packed = mem.context(
        user_id,
        query,
        include_history=include_history,
        agent_id=agent_id,
        namespace=namespace,
    )
    turns = mem.episode_texts(user_id, agent_id=agent_id, namespace=namespace)
    concat = "\n".join(turns)
    overlap = _similar(turns, query)
    history = mem.history(user_id, agent_id=agent_id, namespace=namespace)
    stale = [
        fact.object
        for fact in history.facts
        if fact.status is FactStatus.SUPERSEDED and fact.subject == "user"
    ]
    current = {
        fact.object
        for fact in history.facts
        if fact.status is FactStatus.ACTIVE and fact.subject == "user"
    }
    return {
        "query": query,
        "tensemem": {
            "text": packed.text,
            "facts_used": list(packed.facts_used),
            "token_count": packed.token_count,
            "freshness": _freshness(packed.freshness),
            "debug": [item.model_dump(mode="json") for item in packed.debug],
            "stale_present": [value for value in stale if _mentions(packed.text, value)],
        },
        "concat": {
            "text": concat,
            "stale_present": [value for value in stale if _mentions(concat, value)],
        },
        "similarity": {
            "text": overlap,
            "stale_present": [value for value in stale if _mentions(overlap, value)],
        },
        "stale": stale,
        "current": sorted(current),
    }


def echo(
    mem: Memory,
    user_id: str,
    *,
    turns: int = 8,
    query: str = "",
    agent_id: str = "",
    namespace: str = "default",
) -> dict[str, object]:
    """Feed context() back into add() and record fact count / confidence."""
    if turns < 1 or turns > 32:
        raise ValueError("turns must be between 1 and 32")
    series: list[dict[str, object]] = []
    state = mem.state(user_id, agent_id=agent_id, namespace=namespace)
    series.append(_echo_point(state, 0))
    packed = mem.context(user_id, query, agent_id=agent_id, namespace=namespace)
    for index in range(1, turns + 1):
        mem.add(
            user_id,
            packed.text,
            wait=mem.has_provider(),
            agent_id=agent_id,
            namespace=namespace,
        )
        state = mem.state(user_id, agent_id=agent_id, namespace=namespace)
        series.append(_echo_point(state, index))
    first = series[0]
    last = series[-1]
    return {
        "turns": turns,
        "series": series,
        "flat": first["facts"] == last["facts"] and first["confidence"] == last["confidence"],
    }


def act_risk(
    mem: Memory,
    user_id: str,
    *,
    agent_id: str = "",
    namespace: str = "default",
) -> dict[str, object]:
    """Safe-to-act verdict from freshness, jobs, hedges, and corrections."""
    state = mem.state(user_id, agent_id=agent_id, namespace=namespace)
    stats = mem.stats(user_id, agent_id=agent_id, namespace=namespace)
    jobs = mem.jobs(user_id, agent_id=agent_id, namespace=namespace)
    dead = sum(1 for job in jobs if job.status is JobStatus.DEAD)
    hedges = stats.facts_by_status.get("CANDIDATE", 0)
    pending = state.freshness.pending
    failed = state.freshness.failed
    if failed or dead:
        verdict = "do_not_act"
    elif pending or not state.freshness.is_current:
        verdict = "wait"
    else:
        verdict = "act"
    return {
        "user_id": user_id,
        "verdict": verdict,
        "freshness": _freshness(state.freshness),
        "stats": stats.model_dump(mode="json"),
        "dead_jobs": dead,
        "hedges": hedges,
        "rejected_claims": stats.rejected_claims,
        "values": _values(state.values),
    }


def _echo_point(state: FactSet, index: int) -> dict[str, object]:
    facts = state.facts
    conf = 0.0
    if facts:
        conf = sum(fact.confidence for fact in facts) / len(facts)
    return {"turn": index, "facts": len(facts), "confidence": round(conf, 4)}


def _mentions(text: str, value: str) -> bool:
    return re.search(rf"(?<!\w){re.escape(value)}(?!\w)", text, re.IGNORECASE) is not None


def _similar(turns: Sequence[str], query: str, *, k: int = 2) -> str:
    if not turns:
        return ""
    if not query.strip():
        return "\n".join(turns[-k:])
    ranked = sorted(turns, key=lambda text: _overlap(text, query), reverse=True)
    return "\n".join(ranked[:k])


def _overlap(text: str, query: str) -> int:
    left = set(_WORD.findall(text.casefold()))
    right = set(_WORD.findall(query.casefold()))
    return len(left & right)


def _freshness(fresh: Freshness) -> dict[str, object]:
    data: dict[str, object] = dict(fresh.model_dump(mode="json"))
    data["is_current"] = fresh.is_current
    return data


def _values(values: Mapping[str, str | tuple[str, ...]]) -> dict[str, object]:
    out: dict[str, object] = {}
    for key, value in values.items():
        out[key] = list(value) if isinstance(value, tuple) else value
    return out

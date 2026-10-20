from typing import cast

from tensemem import FakeExtractor, Memory
from tensemem.insights import seed_sample
from tensemem.mcp import seed_starter
from tensemem.server import ROUTES, dispatch


def test_inspect_and_insight_routes() -> None:
    with Memory(":memory:", llm=FakeExtractor(), start_worker=False) as mem:
        seed_starter(mem)
        status, seeded = dispatch(mem, "POST", "/v1/studio/sample", body={})
        assert status == 200
        assert seeded["user_id"] == "studio-demo"

        status, scopes = dispatch(mem, "GET", "/v1/scopes")
        assert status == 200
        users = {str(row["user_id"]) for row in _rows(scopes, "scopes")}
        assert "studio-demo" in users

        status, stats = dispatch(mem, "GET", "/v1/stats", query={"user_id": "studio-demo"})
        assert status == 200
        assert int(str(stats["facts"])) > 0

        status, jobs = dispatch(mem, "GET", "/v1/jobs", query={"user_id": "studio-demo"})
        assert status == 200
        assert isinstance(jobs["jobs"], list)

        status, history = dispatch(
            mem, "GET", "/v1/history", query={"user_id": "studio-demo", "predicate": "files_return"}
        )
        assert status == 200
        fact_id = str(_rows(history, "facts")[0]["id"])
        status, explained = dispatch(mem, "GET", "/v1/explain", query={"fact_id": fact_id})
        assert status == 200
        assert _map(explained, "fact")["predicate"] == "files_return"

        status, searched = dispatch(
            mem,
            "GET",
            "/v1/search",
            query={"user_id": "studio-demo", "query": "GST"},
        )
        assert status == 200
        assert searched["hits"]

        status, graph = dispatch(mem, "GET", "/v1/graph", query={"user_id": "studio-demo"})
        assert status == 200
        assert graph["nodes"]
        kinds = {str(edge["kind"]) for edge in _rows(graph, "edges")}
        assert "SUPERSEDES" in kinds or "files_return" in kinds

        status, ctx = dispatch(
            mem,
            "POST",
            "/v1/context",
            body={"user_id": "studio-demo", "query": "GST", "include_history": True},
        )
        assert status == 200
        assert "debug" in ctx

        status, compared = dispatch(
            mem,
            "POST",
            "/v1/insights/compare",
            body={"user_id": "studio-demo", "query": "which GST return"},
        )
        assert status == 200
        assert compared["stale"]

        status, risk = dispatch(
            mem, "GET", "/v1/insights/act-risk", query={"user_id": "studio-demo"}
        )
        assert status == 200
        assert risk["verdict"] == "act"

        status, echoed = dispatch(
            mem,
            "POST",
            "/v1/insights/echo",
            body={"user_id": "studio-demo", "turns": 2},
        )
        assert status == 200
        assert echoed["flat"] is True

        status, _missing = dispatch(mem, "GET", "/v1/explain", query={"fact_id": "nope"})
        assert status == 404
        status, missing_job = dispatch(mem, "POST", "/v1/jobs:retry", body={"id": "999999"})
        assert status == 404
        assert "error" in missing_job
        status, _missing_dismiss = dispatch(mem, "POST", "/v1/jobs:dismiss", body={"id": "999999"})
        assert status == 404

    assert ("POST", "/v1/studio/sample") in ROUTES
    assert ("GET", "/v1/insights/act-risk") in ROUTES


def test_correct_via_http() -> None:
    with Memory(":memory:", llm=FakeExtractor(), start_worker=False) as mem:
        seed_starter(mem)
        seed_sample(mem)
        status, history = dispatch(
            mem,
            "GET",
            "/v1/history",
            query={"user_id": "studio-demo", "predicate": "invoice_currency"},
        )
        assert status == 200
        active = next(row for row in _rows(history, "facts") if row["status"] == "ACTIVE")
        status, _corrected = dispatch(
            mem,
            "POST",
            "/v1/facts:correct",
            body={"fact_id": str(active["id"])},
        )
        assert status == 200
        status, state = dispatch(mem, "GET", "/v1/state", query={"user_id": "studio-demo"})
        assert status == 200
        assert _map(state, "values")["invoice_currency"] == "USD"


def _map(payload: dict[str, object], key: str) -> dict[str, object]:
    value = payload[key]
    assert isinstance(value, dict)
    return cast(dict[str, object], value)


def _rows(payload: dict[str, object], key: str) -> list[dict[str, object]]:
    value = payload[key]
    assert isinstance(value, list)
    return cast(list[dict[str, object]], value)

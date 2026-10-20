from pathlib import Path
from typing import cast

import pytest

from tensemem import FakeExtractor, Memory
from tensemem.core.models import JobStatus
from tensemem.mcp import seed_starter
from tensemem.server import MAX_BODY_BYTES, ROUTES, create_app, dispatch, limited_body, serve


def test_dispatch_add_context_state_history_forget() -> None:
    with Memory(":memory:", llm=FakeExtractor(), start_worker=False) as mem:
        seed_starter(mem)
        status, added = dispatch(
            mem,
            "POST",
            "/v1/memories:add",
            body={"user_id": "u1", "text": "I live in Delhi"},
        )
        assert status == 200
        assert _map(added, "values")["lives_in"] == "Delhi"
        assert _map(added, "freshness")["is_current"] is True

        dispatch(
            mem,
            "POST",
            "/v1/memories:add",
            body={"user_id": "u1", "text": "I moved to Bangalore"},
        )
        status, state = dispatch(mem, "GET", "/v1/state", query={"user_id": "u1"})
        assert status == 200
        assert _map(state, "values")["lives_in"] == "Bangalore"

        status, recalled = dispatch(
            mem,
            "POST",
            "/v1/context",
            body={"user_id": "u1", "query": "where do I live"},
        )
        assert status == 200
        assert "Bangalore" in str(recalled["text"])

        status, history = dispatch(
            mem,
            "GET",
            "/v1/history",
            query={"user_id": "u1", "predicate": "lives_in"},
        )
        assert status == 200
        facts = history["facts"]
        assert isinstance(facts, list)
        rows = cast(list[dict[str, object]], facts)
        objects = {str(row["object"]) for row in rows}
        assert objects == {"Delhi", "Bangalore"}

        status, forgotten = dispatch(mem, "DELETE", "/v1/scopes/u1")
        assert status == 200
        assert forgotten == {"forgotten": "u1"}
        status, empty = dispatch(mem, "GET", "/v1/state", query={"user_id": "u1"})
        assert status == 200
        assert empty["values"] == {}


def test_dispatch_health_errors_and_routes() -> None:
    with Memory(":memory:", llm=FakeExtractor(), start_worker=False) as mem:
        seed_starter(mem)
        assert dispatch(mem, "GET", "/health") == (200, {"ok": True})
        status, payload = dispatch(mem, "GET", "/v1/nope")
        assert status == 404
        assert payload["error"] == "not found"
        status, payload = dispatch(
            mem, "POST", "/v1/memories:add", body={"text": "I live in Delhi"}
        )
        assert status == 400
        assert "user_id" in str(payload["error"])
        status, payload = dispatch(mem, "DELETE", "/v1/scopes/u1/extra")
        assert status == 404
    assert ("POST", "/v1/memories:add") in ROUTES
    assert ("DELETE", "/v1/scopes/{user_id}") in ROUTES


def test_create_app_needs_extra(monkeypatch: pytest.MonkeyPatch) -> None:
    import tensemem.server as server_mod

    real = server_mod.importlib.import_module

    def missing(name: str, package: str | None = None) -> object:
        if name == "fastapi" or name.startswith("fastapi.") or name == "uvicorn":
            raise ImportError("no extra")
        if package is None:
            return real(name)
        return real(name, package)

    monkeypatch.setattr(server_mod.importlib, "import_module", missing)
    with Memory(":memory:") as mem, pytest.raises(RuntimeError, match=r"tensemem\[server\]"):
        create_app(mem)


def test_serve_leaves_existing_jobs_queued(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db = tmp_path / "rest.db"
    with Memory(db, start_worker=False) as mem:
        mem.register_predicate("lives_in")
        mem.add("u1", "I live in Delhi")
        job_id = mem.jobs("u1")[0].id

    seen: dict[str, object] = {}

    def fake_http(
        mem: Memory,
        *,
        host: str,
        port: int,
        agent_id: str = "",
        namespace: str = "default",
    ) -> None:
        del mem, host, port, agent_id, namespace
        seen["ran"] = True

    monkeypatch.setattr("tensemem.server.run_http", fake_http)
    serve(db, port=8090)
    assert seen["ran"] is True
    with Memory(db, start_worker=False) as mem:
        assert mem.jobs("u1")[0].id == job_id
        assert mem.jobs("u1")[0].status is JobStatus.QUEUED


def test_serve_rejects_bad_port(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="port"):
        serve(tmp_path / "t.db", port=0)


def test_limited_body_rejects_oversize() -> None:
    assert limited_body([b"ok"]) == b"ok"
    assert limited_body([b"x" * MAX_BODY_BYTES]) == b"x" * MAX_BODY_BYTES
    with pytest.raises(ValueError, match="too large"):
        limited_body([b"x" * (MAX_BODY_BYTES + 1)])
    with pytest.raises(ValueError, match="too large"):
        limited_body([b"x" * 40_000, b"y" * 40_000])


def test_serve_warns_when_host_is_not_loopback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def fake_http(
        mem: Memory,
        *,
        host: str,
        port: int,
        agent_id: str = "",
        namespace: str = "default",
    ) -> None:
        del mem, host, port, agent_id, namespace

    monkeypatch.setattr("tensemem.server.run_http", fake_http)
    serve(tmp_path / "t.db", host="0.0.0.0", port=8080)
    assert "no auth or TLS" in capsys.readouterr().err
    serve(tmp_path / "loop.db", host="127.0.0.1", port=8080)
    assert capsys.readouterr().err == ""


def _map(payload: dict[str, object], key: str) -> dict[str, object]:
    value = payload[key]
    assert isinstance(value, dict)
    return cast(dict[str, object], value)

import json
from pathlib import Path

import pytest

from tensemem import FakeExtractor, Memory
from tensemem.core.models import JobStatus
from tensemem.mcp import TOOL_NAMES, bind_http_app, bind_server, call_tool, seed_starter, serve


def test_remember_recall_state_history_forget() -> None:
    with Memory(":memory:", llm=FakeExtractor()) as mem:
        seed_starter(mem)
        remembered = json.loads(
            call_tool(mem, "remember", {"user_id": "u1", "text": "I live in Delhi"})
        )
        assert remembered["seq"] == 1
        assert remembered["values"]["lives_in"] == "Delhi"
        assert remembered["freshness"]["is_current"] is True

        json.loads(call_tool(mem, "remember", {"user_id": "u1", "text": "I moved to Bangalore"}))
        state = json.loads(call_tool(mem, "get_state", {"user_id": "u1"}))
        assert state["values"]["lives_in"] == "Bangalore"
        assert state["freshness"]["is_current"] is True

        recalled = json.loads(
            call_tool(mem, "recall_context", {"user_id": "u1", "query": "where do I live"})
        )
        assert "Bangalore" in recalled["text"]
        assert recalled["freshness"]["is_current"] is True

        history = json.loads(
            call_tool(mem, "get_history", {"user_id": "u1", "predicate": "lives_in"})
        )
        objects = {fact["object"] for fact in history["facts"]}
        assert objects == {"Delhi", "Bangalore"}

        forgotten = json.loads(call_tool(mem, "forget", {"user_id": "u1"}))
        assert forgotten == {"forgotten": "u1"}
        empty = json.loads(call_tool(mem, "get_state", {"user_id": "u1"}))
        assert empty["values"] == {}
        assert empty["facts"] == []


def test_default_user_and_unknown_tool() -> None:
    with Memory(":memory:", llm=FakeExtractor()) as mem:
        seed_starter(mem)
        payload = json.loads(
            call_tool(
                mem,
                "remember",
                {"text": "I live in Pune"},
                default_user="u1",
            )
        )
        assert payload["values"]["lives_in"] == "Pune"
        with pytest.raises(ValueError, match="user_id"):
            call_tool(mem, "get_state", {})
        with pytest.raises(ValueError, match="unknown tool"):
            call_tool(mem, "set_slot", {"user_id": "u1"})
        with pytest.raises(ValueError, match="text is required"):
            call_tool(mem, "remember", {"user_id": "u1", "text": "  "})


def test_tool_names_match_design() -> None:
    assert TOOL_NAMES == (
        "remember",
        "recall_context",
        "get_state",
        "get_history",
        "forget",
    )


def test_bind_server_needs_extra(monkeypatch: pytest.MonkeyPatch) -> None:
    import tensemem.mcp as mcp_mod

    real = mcp_mod.importlib.import_module

    def missing(name: str, package: str | None = None) -> object:
        if name.startswith("mcp"):
            raise ImportError("no mcp")
        if package is None:
            return real(name)
        return real(name, package)

    monkeypatch.setattr(mcp_mod.importlib, "import_module", missing)
    with Memory(":memory:") as mem, pytest.raises(RuntimeError, match=r"tensemem\[mcp\]"):
        bind_server(mem)
    with Memory(":memory:") as mem, pytest.raises(RuntimeError, match=r"tensemem\[mcp\]"):
        bind_http_app(mem)


def test_serve_opens_database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, object] = {}

    def fake_run(
        mem: Memory,
        *,
        default_user: str = "",
        agent_id: str = "",
        namespace: str = "default",
    ) -> None:
        del mem, default_user, agent_id, namespace
        seen["ran"] = True

    monkeypatch.setattr("tensemem.mcp.run_stdio", fake_run)
    db = tmp_path / "mcp.db"
    serve(db, default_user="u1")
    assert db.exists()
    assert seen["ran"] is True
    with Memory(db, start_worker=False) as mem:
        mem.set(user_id="u1", predicate="lives_in", value="Goa")
        assert mem.state("u1").values == {"lives_in": "Goa"}


def test_serve_leaves_existing_jobs_queued(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db = tmp_path / "mcp.db"
    with Memory(db, start_worker=False) as mem:
        mem.register_predicate("lives_in")
        mem.add("u1", "I live in Delhi")
        job_id = mem.jobs("u1")[0].id
        assert mem.jobs("u1")[0].status is JobStatus.QUEUED

    seen: dict[str, object] = {}

    def during_serve(
        mem: Memory,
        *,
        default_user: str = "",
        agent_id: str = "",
        namespace: str = "default",
    ) -> None:
        del default_user, agent_id, namespace
        queued = mem.jobs("u1")
        assert queued[0].id == job_id
        assert queued[0].status is JobStatus.QUEUED
        payload = json.loads(
            call_tool(mem, "remember", {"user_id": "u2", "text": "I live in Pune"})
        )
        assert payload["values"]["lives_in"] == "Pune"
        still = mem.jobs("u1")
        assert still[0].id == job_id
        assert still[0].status is JobStatus.QUEUED
        seen["ok"] = True

    monkeypatch.setattr("tensemem.mcp.run_stdio", during_serve)
    serve(db)
    assert seen["ok"] is True
    with Memory(db, start_worker=False) as mem:
        assert mem.jobs("u1")[0].status is JobStatus.QUEUED
        assert mem.state("u2").values == {"lives_in": "Pune"}


def test_serve_http_uses_streamable_transport(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    seen: dict[str, object] = {}

    def fake_http(
        mem: Memory,
        *,
        host: str,
        port: int,
        default_user: str = "",
        agent_id: str = "",
        namespace: str = "default",
        token: str | None = None,
    ) -> None:
        del mem
        seen["host"] = host
        seen["port"] = port
        seen["user"] = default_user
        seen["token"] = token

    monkeypatch.setattr("tensemem.mcp.run_http", fake_http)
    db = tmp_path / "mcp-http.db"
    serve(db, default_user="u1", http=True, host="0.0.0.0", port=8081, token="secret")
    assert db.exists()
    assert seen == {
        "host": "0.0.0.0",
        "port": 8081,
        "user": "u1",
        "token": "secret",
    }
    assert "TLS is off" in capsys.readouterr().err
    with pytest.raises(ValueError, match="port"):
        serve(tmp_path / "bad.db", http=True, port=0)

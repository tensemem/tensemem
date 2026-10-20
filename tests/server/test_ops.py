from typing import cast

from tensemem import FakeExtractor, Memory
from tensemem.mcp import seed_starter
from tensemem.ops import allow_request, log_request
from tensemem.server import ROUTES, dispatch


def test_ops_keys_provider_and_auth() -> None:
    with Memory(":memory:", llm=FakeExtractor(), start_worker=False) as mem:
        seed_starter(mem)
        assert allow_request(mem, None, None) is True
        status, created = dispatch(mem, "POST", "/v1/ops/keys", body={"label": "dev"})
        assert status == 200
        token = str(created["token"])
        assert token.startswith("tm_")
        assert allow_request(mem, None, None) is False
        assert allow_request(mem, f"Bearer {token}", None) is True
        assert allow_request(mem, "Bearer admin", "admin") is True
        status, listed = dispatch(mem, "GET", "/v1/ops/keys")
        assert status == 200
        keys = _rows(listed, "keys")
        assert keys[0]["label"] == "dev"
        status, revoked = dispatch(mem, "POST", "/v1/ops/keys:revoke", body={"id": created["id"]})
        assert status == 200
        assert revoked["revoked"] is True
        assert allow_request(mem, None, None) is True
        status, second = dispatch(mem, "POST", "/v1/ops/keys", body={"label": "next"})
        assert status == 200
        assert allow_request(mem, f"Bearer {token}", None) is False
        assert allow_request(mem, f"Bearer {second['token']}", None) is True
        status, provider = dispatch(mem, "GET", "/v1/ops/provider")
        assert status == 200
        assert provider["llm"] == "fake"
        status, saved = dispatch(
            mem, "PUT", "/v1/ops/provider", body={"llm": "fake", "embedder": "none"}
        )
        assert status == 200
        assert saved["llm"] == "fake"
        log_request(
            mem,
            method="GET",
            path="/v1/state",
            status=200,
            latency_ms=4,
            authorization=f"Bearer {token}",
        )
        status, logs = dispatch(mem, "GET", "/v1/ops/requests")
        assert status == 200
        rows = _rows(logs, "requests")
        assert any(row["path"] == "/v1/state" for row in rows)
        assert any(row["key_prefix"] == token[:10] for row in rows)
    assert ("POST", "/v1/ops/keys") in ROUTES


def _rows(payload: dict[str, object], key: str) -> list[dict[str, object]]:
    value = payload[key]
    assert isinstance(value, list)
    return cast(list[dict[str, object]], value)

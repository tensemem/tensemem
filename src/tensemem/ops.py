"""Studio ops chrome: API keys, request log, provider settings (ADR 0019)."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import sqlite3
import sys
from collections.abc import Mapping
from typing import cast

from tensemem.auth import authorize
from tensemem.core.ids import new_ulid
from tensemem.eval.hosted import hosted_secret_status, provider_from_name
from tensemem.memory import Memory
from tensemem.providers.embed.base import Embedder
from tensemem.providers.llm.fake import FakeExtractor

_PBKDF_ROUNDS = 200_000


def issue_key(mem: Memory, *, label: str = "") -> dict[str, str]:
    token = "tm_" + secrets.token_urlsafe(24)
    prefix = token[:10]
    salt = secrets.token_bytes(16)
    digest = _digest(token, salt)
    key_id = new_ulid()
    now = mem.store().now()

    def write(conn: sqlite3.Connection) -> None:
        conn.execute(
            """
            INSERT INTO api_keys(id, prefix, secret_hash, label, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (key_id, prefix, f"{salt.hex()}:{digest}", label.strip(), now),
        )

    mem.store().transaction(write)
    return {"id": key_id, "prefix": prefix, "label": label.strip(), "token": token}


def list_keys(mem: Memory) -> list[dict[str, object]]:
    def load(conn: sqlite3.Connection) -> list[dict[str, object]]:
        rows = conn.execute(
            "SELECT id, prefix, label, created_at, revoked_at "
            "FROM api_keys ORDER BY created_at DESC"
        ).fetchall()
        return [
            {
                "id": str(row["id"]),
                "prefix": str(row["prefix"]),
                "label": str(row["label"]),
                "created_at": str(row["created_at"]),
                "revoked_at": row["revoked_at"],
            }
            for row in rows
        ]

    return mem.store().read(load)


def revoke_key(mem: Memory, key_id: str) -> dict[str, object]:
    now = mem.store().now()

    def write(conn: sqlite3.Connection) -> int:
        cur = conn.execute(
            "UPDATE api_keys SET revoked_at = ? WHERE id = ? AND revoked_at IS NULL",
            (now, key_id),
        )
        return cur.rowcount

    if mem.store().transaction(write) < 1:
        raise ValueError("unknown or revoked key")
    return {"id": key_id, "revoked": True}


def has_live_keys(mem: Memory) -> bool:
    def load(conn: sqlite3.Connection) -> bool:
        row = conn.execute("SELECT 1 FROM api_keys WHERE revoked_at IS NULL LIMIT 1").fetchone()
        return row is not None

    try:
        return mem.store().read(load)
    except sqlite3.OperationalError:
        return False


def header_matches_key(mem: Memory, authorization: str | None) -> bool:
    header = (authorization or "").strip()
    prefix = "Bearer "
    if not header.startswith(prefix):
        return False
    token = header[len(prefix) :].strip()
    if not token:
        return False

    def load(conn: sqlite3.Connection) -> list[str]:
        rows = conn.execute("SELECT secret_hash FROM api_keys WHERE revoked_at IS NULL").fetchall()
        return [str(row["secret_hash"]) for row in rows]

    try:
        hashes = mem.store().read(load)
    except sqlite3.OperationalError:
        return False
    return any(_verify(token, stored) for stored in hashes)


def allow_request(mem: Memory, authorization: str | None, bootstrap: str | None) -> bool:
    """True when no auth is configured, or the bearer matches bootstrap or a live key."""
    bootstrap_set = bool((bootstrap or "").strip())
    live = has_live_keys(mem)
    if not bootstrap_set and not live:
        return True
    if bootstrap_set and authorize(authorization, bootstrap):
        return True
    return header_matches_key(mem, authorization)


def log_request(
    mem: Memory,
    *,
    method: str,
    path: str,
    status: int,
    latency_ms: int,
    authorization: str | None,
) -> None:
    now = mem.store().now()
    prefix = _bearer_prefix(authorization)

    def write(conn: sqlite3.Connection) -> None:
        conn.execute(
            """
            INSERT INTO request_logs(at, method, path, status, latency_ms, key_prefix)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (now, method, path, status, latency_ms, prefix),
        )

    try:
        mem.store().transaction(write)
    except sqlite3.OperationalError:
        return


def list_requests(mem: Memory, *, limit: int = 50) -> list[dict[str, object]]:
    cap = max(1, min(limit, 200))

    def load(conn: sqlite3.Connection) -> list[dict[str, object]]:
        rows = conn.execute(
            """
            SELECT at, method, path, status, latency_ms, key_prefix
            FROM request_logs ORDER BY id DESC LIMIT ?
            """,
            (cap,),
        ).fetchall()
        return [
            {
                "at": str(row["at"]),
                "method": str(row["method"]),
                "path": str(row["path"]),
                "status": int(row["status"]),
                "latency_ms": int(row["latency_ms"]),
                "key_prefix": row["key_prefix"],
            }
            for row in rows
        ]

    try:
        return mem.store().read(load)
    except sqlite3.OperationalError:
        return []


def provider_settings(mem: Memory) -> dict[str, object]:
    llm = get_setting(mem, "llm", "fake")
    return {
        "llm": llm,
        "embedder": get_setting(mem, "embedder", "none"),
        "credentials": hosted_secret_status(llm),
    }


def set_provider(mem: Memory, *, llm: str, embedder: str) -> dict[str, object]:
    name = llm.strip().casefold() or "fake"
    embed = embedder.strip().casefold() or "none"
    if name not in {"fake", "openai", "anthropic", "ollama", "litellm", "gemini"}:
        raise ValueError("llm must be fake, openai, anthropic, ollama, litellm, or gemini")
    if embed not in {"none", "openai", "fastembed"}:
        raise ValueError("embedder must be none, openai, or fastembed")
    set_setting(mem, "llm", name)
    set_setting(mem, "embedder", embed)
    extractor = FakeExtractor() if name == "fake" else provider_from_name(name)
    mem.apply_extractor(extractor if extractor is not None else FakeExtractor())
    mem.apply_embedder(_embedder_from_name(embed))
    if name != "fake" or embed != "none":
        mem.start_extract_worker()
    credentials = hosted_secret_status(name)
    print(f"tensemem serve: provider={name} credentials={credentials}", file=sys.stderr)
    if name != "fake" and not bool(credentials.get("ok")):
        print(
            "tensemem serve: hosted extract will fail until the env key is set "
            "in this serve process and the provider extra is installed",
            file=sys.stderr,
        )
    return {"llm": name, "embedder": embed, "credentials": credentials}


def get_setting(mem: Memory, key: str, default: str) -> str:
    def load(conn: sqlite3.Connection) -> str:
        row = conn.execute("SELECT value FROM app_settings WHERE key = ?", (key,)).fetchone()
        return default if row is None else str(row["value"])

    try:
        return mem.store().read(load)
    except sqlite3.OperationalError:
        return default


def set_setting(mem: Memory, key: str, value: str) -> None:
    def write(conn: sqlite3.Connection) -> None:
        conn.execute(
            """
            INSERT INTO app_settings(key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (key, value),
        )

    mem.store().transaction(write)


def handle_ops(
    mem: Memory,
    method: str,
    path: str,
    *,
    query: Mapping[str, object],
    body: Mapping[str, object],
) -> tuple[int, dict[str, object]] | None:
    verb = method.upper()
    route = path.rstrip("/") or "/"
    payload = dict(body)
    params = dict(query)
    try:
        if verb == "GET" and route == "/v1/ops/keys":
            return 200, {"keys": list_keys(mem)}
        if verb == "POST" and route == "/v1/ops/keys":
            issued = issue_key(mem, label=str(payload.get("label") or ""))
            return 200, cast(dict[str, object], issued)
        if verb == "POST" and route == "/v1/ops/keys:revoke":
            return 200, revoke_key(mem, str(payload.get("id") or "").strip())
        if verb == "GET" and route == "/v1/ops/requests":
            raw_limit = params.get("limit", 50)
            if isinstance(raw_limit, bool) or not isinstance(raw_limit, int | float | str):
                raise ValueError("limit must be an integer")
            return 200, {"requests": list_requests(mem, limit=int(raw_limit or 50))}
        if verb == "GET" and route == "/v1/ops/provider":
            return 200, provider_settings(mem)
        if verb == "PUT" and route == "/v1/ops/provider":
            return 200, set_provider(
                mem,
                llm=str(payload.get("llm") or "fake"),
                embedder=str(payload.get("embedder") or "none"),
            )
    except ValueError as extra:
        return 400, {"error": str(extra)}
    return None


def _digest(token: str, salt: bytes) -> str:
    return hashlib.pbkdf2_hmac("sha256", token.encode("utf-8"), salt, _PBKDF_ROUNDS).hex()


def _verify(token: str, stored: str) -> bool:
    salt_hex, _, digest = stored.partition(":")
    if not salt_hex or not digest:
        return False
    try:
        salt = bytes.fromhex(salt_hex)
    except ValueError:
        return False
    got = _digest(token, salt)
    return hmac.compare_digest(got, digest)


def _embedder_from_name(name: str) -> Embedder | None:
    key = name.strip().casefold()
    if not key or key == "none":
        return None
    if key == "openai":
        from tensemem.providers.embed.openai import OpenAIEmbedder

        return OpenAIEmbedder()
    if key == "fastembed":
        from tensemem.providers.embed.fastembed import FastEmbedProvider

        return FastEmbedProvider()
    raise ValueError("embedder must be none, openai, or fastembed")


def _bearer_prefix(authorization: str | None) -> str | None:
    header = (authorization or "").strip()
    if not header.startswith("Bearer "):
        return None
    token = header[7:].strip()
    return token[:10] if token else None

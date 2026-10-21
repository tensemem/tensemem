# 0011. REST is an HTTP adapter over the same engine

- Status: Accepted
- Date: 2026-10-19

## Context

MCP covers a local stdio host. Non-Python clients and several processes that must share one writer need HTTP. ADR 0003 already points heavy multi-process ingest at a server. The five operations already exist as MCP tools (`remember`, `recall_context`, `get_state`, `get_history`, `forget`).

## Decision

1. **`tensemem serve` is an HTTP server** on the same SQLite file as the CLI (`--db`, default `tensemem.db`). Default bind is `127.0.0.1:8080`. The process does not authenticate callers or terminate TLS. Streamable HTTP MCP and in-process auth stay later slices.
2. **Five routes, mapped onto the MCP tools:** `POST /v1/memories:add`, `POST /v1/context`, `GET /v1/state`, `GET /v1/history`, `DELETE /v1/scopes/{user_id}`. `GET /health` is a liveness probe. Bodies and query strings use the same JSON fields as the tools, including `freshness.is_current`.
3. **The agent does not decide SET/UPDATE.** Add only ingests user text. Extraction and `resolve()` still apply typed ops (ADR 0002 / 0010).
4. **FastAPI and uvicorn are an optional extra** (`tensemem[server]`). Route dispatch is independent of that import so CI can score the mapping without the extra.
5. **Default extractor is `FakeExtractor`.** The background worker stays off so jobs already queued in a shared file are not claimed at startup. HTTP `POST /v1/memories:add` returns when the extract job is queued; pass `"wait": true` to drain extract in that request. MCP `remember` still waits unless `wait` is set. The starter registry is the same as MCP.

## Alternatives considered

- **stdio MCP only.** Fine for a local host, but it does not help a second language or several workers on one file.
- **Homemade HTTP.** Avoids the extra, but OpenAPI and a battle-tested server are the point of this slice.
- **Routes that SET/ADD/REMOVE slots.** Same rejection as ADR 0010.

## Consequences

- One SQLite writer per `tensemem serve` process. Other processes on the same file serialize on `BEGIN IMMEDIATE`.
- Forget is irreversible from the API; `user_id` is in the path.
- A non-loopback bind is a trusted-network choice: operators must put authenticated, user-scoped access control and TLS in front.
- Hosted extractors stay out of this process. Swap `llm=` later without changing the paths.

## Revisit when

We add Streamable HTTP MCP, auth, or a real-model extractor in the server process.

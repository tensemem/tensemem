# REST

`tensemem serve` exposes the engine over HTTP so clients that cannot embed Python can remember and recall. Same SQLite file as the [CLI](cli.md) and [MCP](mcp.md). Needs `tensemem[server]`.

```bash
pip install "tensemem[server]"
tensemem --db /absolute/path/tensemem.db serve --port 8080
export TENSEMEM_TOKEN=replace-me
tensemem --db /absolute/path/tensemem.db serve --port 8080
```

Default bind is `127.0.0.1:8080`. `--db`, `--agent`, and `--namespace` are root flags (before `serve`).

When `--token` or `TENSEMEM_TOKEN` is set, or any Studio key has been issued, every route except `GET /health` needs `Authorization: Bearer`. Issued keys and the bootstrap token both work. This process does not configure TLS. Keep it on loopback. If `--host` exposes it beyond loopback, put a TLS-terminating reverse proxy in front that also authorizes the `user_id` callers send.

## Routes

| Method | Path | Engine call |
|---|---|---|
| `POST` | `/v1/memories:add` | `add()` |
| `POST` | `/v1/context` | `context()` |
| `GET` | `/v1/state` | `state()` — query `user_id` |
| `GET` | `/v1/history` | `history()` — query `user_id`, optional `predicate` |
| `DELETE` | `/v1/scopes/{user_id}` | `forget()` |
| `GET` | `/health` | `{ "ok": true }` |
| `GET` | `/v1/scopes` | stored users |
| `GET` | `/v1/stats` | `stats()` |
| `GET` | `/v1/jobs` | outbox |
| `POST` | `/v1/jobs:retry` | `retry_job()` |
| `POST` | `/v1/jobs:dismiss` | `dismiss_job()` |
| `GET` | `/v1/explain` | `explain(fact_id)` |
| `GET` | `/v1/search` | `search()` |
| `GET` | `/v1/graph` | fact graph |
| `POST` | `/v1/facts:correct` | `correct()` |
| `POST` | `/v1/insights/compare` | TenseMem vs concat vs overlap |
| `POST` | `/v1/insights/echo` | feed context back in |
| `GET` | `/v1/insights/act-risk` | safe-to-act verdict |
| `POST` | `/v1/studio/sample` | GST / itinerary sample |
| `GET/POST` | `/v1/ops/keys` | issue / list hashed keys |
| `POST` | `/v1/ops/keys:revoke` | revoke a key by `id` |
| `GET` | `/v1/ops/requests` | request log |
| `GET/PUT` | `/v1/ops/provider` | llm / embedder names |

Studio (`docs/studio.md`) is a Next.js client for these routes.

`POST /v1/memories:add`:

```json
{"user_id": "u1", "text": "I live in Delhi"}
```

`POST /v1/context`:

```json
{"user_id": "u1", "query": "where do I live", "max_tokens": 300}
```

`query` and `max_tokens` are optional on context (`query` defaults to empty, `max_tokens` to 300).

Reads include freshness (`as_of_seq`, `pending`, `is_current`). `POST /v1/memories:add` returns when the extract job is queued. Pass `"wait": true` to drain extract in that request. POST bodies larger than 64 KiB are rejected.

This process does not start MCP. For a second process on the same file, see [Operations](ops.md).

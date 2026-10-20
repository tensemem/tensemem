# REST

`tensemem serve` exposes the engine over HTTP so clients that cannot embed Python can remember and recall. Same SQLite file as the [CLI](cli.md) and [MCP](mcp.md). Needs `tensemem[server]`.

```bash
pip install "tensemem[server]"
tensemem --db /absolute/path/tensemem.db serve --port 8080
```

Default bind is `127.0.0.1:8080`. `--db`, `--agent`, and `--namespace` are root flags (before `serve`).

This process has no authentication and does not configure TLS. Keep it on loopback. If `--host` exposes it beyond loopback, put a TLS-terminating reverse proxy in front that authenticates callers and authorizes the `user_id` they send.

## Routes

| Method | Path | Engine call |
|---|---|---|
| `POST` | `/v1/memories:add` | `add()` |
| `POST` | `/v1/context` | `context()` |
| `GET` | `/v1/state` | `state()` — query `user_id` |
| `GET` | `/v1/history` | `history()` — query `user_id`, optional `predicate` |
| `DELETE` | `/v1/scopes/{user_id}` | `forget()` |
| `GET` | `/health` | `{ "ok": true }` |

`POST /v1/memories:add`:

```json
{"user_id": "u1", "text": "I live in Delhi"}
```

`POST /v1/context`:

```json
{"user_id": "u1", "query": "where do I live", "max_tokens": 300}
```

`query` and `max_tokens` are optional on context (`query` defaults to empty, `max_tokens` to 300).

Reads include freshness (`as_of_seq`, `pending`, `is_current`). Add waits in the request (no background worker), so jobs already queued for other scopes stay queued. POST bodies larger than 64 KiB are rejected.

This process does not start MCP. For a second process on the same file, see [Operations](ops.md).

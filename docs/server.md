# REST

`tensemem serve` exposes the engine over HTTP so clients that cannot embed Python can remember and recall. Same SQLite file as the [CLI](cli.md) and [MCP](mcp.md). Needs `tensemem[server]`.

```bash
pip install "tensemem[server]"
tensemem --db /absolute/path/tensemem.db serve --port 8080
```

Default bind is `127.0.0.1:8080`. `--db`, `--agent`, and `--namespace` are root flags (before `serve`).

## Routes

| Method | Path | Engine call |
|---|---|---|
| `POST` | `/v1/memories:add` | `add()` — JSON `{ "user_id", "text" }` |
| `POST` | `/v1/context` | `context()` — JSON `{ "user_id", "query"?, "max_tokens"? }` |
| `GET` | `/v1/state` | `state()` — query `user_id` |
| `GET` | `/v1/history` | `history()` — query `user_id`, optional `predicate` |
| `DELETE` | `/v1/scopes/{user_id}` | `forget()` |
| `GET` | `/health` | `{ "ok": true }` |

Reads include freshness (`as_of_seq`, `pending`, `is_current`). Add waits in the request (no background worker), so jobs already queued for other scopes stay queued.

This process does not start MCP. For a second process on the same file, see [Operations](ops.md).

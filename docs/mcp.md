# MCP

`tensemem mcp` exposes the engine on stdio so an MCP host can remember and recall without embedding Python. Same SQLite file as the [CLI](cli.md). Needs `tensemem[mcp]`.

```bash
pip install "tensemem[mcp]"
tensemem mcp --db /absolute/path/tensemem.db --user u1
```

Host config (stdio):

```json
{
  "mcpServers": {
    "tensemem": {
      "command": "tensemem",
      "args": ["mcp", "--db", "/absolute/path/tensemem.db", "--user", "u1"]
    }
  }
}
```

`--user` is the default `user_id` when a tool omits it. `--agent` and `--namespace` are the process-wide scope, same as the CLI.

A fresh file is seeded with the FakeExtractor predicates (`lives_in`, `uses_language`, and the rest of that set) so `remember` can extract without a Python app calling `register_predicate` first. Re-opening the file is a no-op for those names.

## Tools

| Tool | Engine call | Notes |
|---|---|---|
| `remember` | `add()` | Ingests user text. The engine extracts; this tool does not edit slots. Waits when an extractor is present (default: `FakeExtractor`). |
| `recall_context` | `context()` | Fenced prompt block plus `freshness.is_current`. Optional `query`, `max_tokens`. |
| `get_state` | `state()` | ACTIVE values and facts. |
| `get_history` | `history()` | Optional `predicate` for the version chain. |
| `forget` | `forget()` | Deletes that user's scope. |

Reads include freshness (`as_of_seq`, `pending`, `is_current`). Recalled text is fenced so a later `remember` of the same conversation does not learn from the model's own echo.

This process does not start REST or HTTP MCP. For a second process on the same file, see [Operations](ops.md).

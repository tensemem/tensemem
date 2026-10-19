# What

- Add `tensemem mcp`: stdio MCP server with `remember`, `recall_context`, `get_state`, `get_history`, and `forget`, on the same SQLite file as the CLI.
- Optional extra `tensemem[mcp]` (official SDK). Tool dispatch does not import it, so tests cover the mapping without the extra.
- Default extractor is `FakeExtractor`; `remember` waits in the tool call. The background worker stays off so jobs already queued in a shared file are not claimed at startup.

# Why

Desktop MCP hosts need a one-process adapter. The tools ingest text and read state; they do not let the model SET/UPDATE slots. Extraction and resolve() stay on the engine.

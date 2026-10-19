# What

- Add `tensemem mcp`: stdio MCP server with `remember`, `recall_context`, `get_state`, `get_history`, and `forget`, on the same SQLite file as the CLI.
- Optional extra `tensemem[mcp]` (official SDK). Tool dispatch does not import it, so tests cover the mapping without the extra.
- Default extractor is `FakeExtractor`; `remember` waits so the next recall can be current.

# Why

Desktop MCP hosts need a one-process adapter. The tools ingest text and read state; they do not let the model SET/UPDATE slots. Extraction and resolve() stay on the engine.

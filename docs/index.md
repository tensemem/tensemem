# TenseMem

**Memory that knows its tenses.** Embedded, deterministic memory that AI agents can safely act on.

**0.1.0 alpha.** One SQLite file. The model proposes typed facts; the engine decides what is current. Recalled context is fenced so the engine does not learn from its own output. Corrections restore displaced values and survive a rebuild.

## Start here

- [Quickstart](quickstart.md) — three lines to a fenced `context()` block
- [Concepts](concepts.md) — episodes, facts, freshness, fences, corrections
- [Architecture](architecture.md) — surfaces, write / extract / read paths, and where to change things
- [Python API](api.md) — `Memory` and `AsyncMemory`
- [CLI](cli.md) — inspect, history, explain, search, jobs, bench, longmem, locomo, latency, mcp, serve
- [MCP](mcp.md) — stdio or Streamable HTTP tools for remember / recall / state / history / forget
- [REST](server.md) — HTTP routes for add / context / state / history / forget / inspect
- [Studio](studio.md) — Next.js inspector: safe-to-act, playground, compare, echo
- [LangGraph store](langgraph.md) — `put` / `search` over `add()` and `context()`
- [LlamaIndex chat memory](llamaindex.md) — `put` / `get` over `add()` and `context()`
- [TenseBench](tensebench.md) — safe-to-act-on metrics
- [Long-session eval](longmem.md) — LongMemEval-shaped packs scored through `context()`
- [LoCoMo eval](locomo.md) — LoCoMo-shaped conversations scored through `context()`
- [Golden extract](golden.md) — labeled utterances for precision and recall
- [Context latency](latency.md) — empty-query `context()` percentiles
- [Operations](ops.md) — backup, JSONL export, Litestream, migrations

Local preview (optional): `uvx mkdocs serve`.
